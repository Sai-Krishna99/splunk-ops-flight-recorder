"""Client for the official Splunk MCP Server (Splunkbase app 7931).

Calls the Splunk MCP Server over the streamable HTTP transport at
``https://<host>:8089/services/mcp`` with a Bearer token, runs an SPL search
through the server's run-query tool, and returns the result rows as plain
dicts compatible with the existing REST row mapping.

The ``mcp`` SDK is imported lazily inside the call path so the rest of the app
(demo and REST modes, tests) does not require it unless MCP mode is used.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SplunkMcpConfig:
    url: str
    token: str | None
    index: str
    tool: str
    query_arg: str
    verify_ssl: bool
    timeout: float

    @classmethod
    def from_env(cls) -> "SplunkMcpConfig":
        base = os.getenv("SPLUNK_BASE_URL", "https://127.0.0.1:8089").rstrip("/")
        url = os.getenv("SPLUNK_MCP_URL") or f"{base}/services/mcp"
        return cls(
            url=url,
            token=os.getenv("SPLUNK_MCP_TOKEN") or os.getenv("SPLUNK_TOKEN"),
            index=os.getenv("SPLUNK_INDEX", "ops_demo"),
            # Cisco's README calls the tool run_splunk_query; the namespaced
            # platform name is splunk_run_query. Override with SPLUNK_MCP_TOOL.
            tool=os.getenv("SPLUNK_MCP_TOOL", "splunk_run_query"),
            query_arg=os.getenv("SPLUNK_MCP_QUERY_ARG", "query"),
            verify_ssl=os.getenv("SPLUNK_VERIFY_SSL", "false").lower()
            in {"1", "true", "yes"},
            timeout=float(os.getenv("SPLUNK_MCP_TIMEOUT", "60")),
        )

    @property
    def has_auth(self) -> bool:
        return bool(self.token)


def run_mcp_query(config: SplunkMcpConfig, spl: str) -> list[dict]:
    """Execute one SPL query via the Splunk MCP Server and return result rows."""
    try:
        return asyncio.run(_run_mcp_query(config, spl))
    except RuntimeError as exc:
        raise RuntimeError(f"Splunk MCP query failed: {exc}") from exc


async def _run_mcp_query(config: SplunkMcpConfig, spl: str) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {config.token}"} if config.token else {}
    client_kwargs: dict = {
        "headers": headers,
        "timeout": config.timeout,
        # Splunk's /services/mcp exposes POST only; skip the session-terminate DELETE.
        "terminate_on_close": False,
    }
    if not config.verify_ssl:
        # Local Splunk serves the management port with a self-signed cert.
        client_kwargs["httpx_client_factory"] = _insecure_http_client

    async with streamablehttp_client(config.url, **client_kwargs) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(config.tool, {config.query_arg: spl})

    if getattr(result, "isError", False):
        raise RuntimeError(
            f"Splunk MCP tool '{config.tool}' returned an error: {_result_text(result)}"
        )
    return rows_from_tool_result(result)


def _insecure_http_client(headers=None, timeout=None, auth=None, **_):
    import httpx

    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        auth=auth,
        verify=False,
        follow_redirects=True,
    )


def rows_from_tool_result(result) -> list[dict]:
    """Normalize an MCP CallToolResult into a list of row dicts."""
    structured = getattr(result, "structuredContent", None)
    if structured:
        rows = _rows_from_structured(structured)
        if rows:
            return rows
    texts = [
        content.text
        for content in getattr(result, "content", []) or []
        if getattr(content, "type", None) == "text"
    ]
    return _rows_from_text("\n".join(texts))


def _rows_from_structured(obj) -> list[dict]:
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)]
    if isinstance(obj, dict):
        for key in ("results", "rows", "records", "data"):
            value = obj.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        result = obj.get("result")
        if isinstance(result, dict):
            return [result]
    return []


def _rows_from_text(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    # 1) The whole payload is a JSON array or object.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        if rows:
            return rows
    elif parsed is not None:
        rows = _rows_from_structured(parsed)
        if rows:
            return rows
    # 2) Newline-delimited JSON (Splunk export style: {"result": {...}} per line).
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            inner = item.get("result")
            rows.append(inner if isinstance(inner, dict) else item)
    return [row for row in rows if isinstance(row, dict)]


def _result_text(result) -> str:
    texts = [
        content.text
        for content in getattr(result, "content", []) or []
        if getattr(content, "type", None) == "text"
    ]
    return " ".join(texts)[:300]
