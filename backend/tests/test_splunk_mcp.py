import pytest

from backend.app.splunk_client import SplunkMcpAdapter
from backend.app.splunk_mcp_client import (
    SplunkMcpConfig,
    _rows_from_text,
    rows_from_tool_result,
)


def make_config(token: str | None = "test-token") -> SplunkMcpConfig:
    return SplunkMcpConfig(
        url="https://splunk.example:8089/services/mcp",
        token=token,
        index="ops_demo",
        tool="splunk_run_query",
        query_arg="query",
        verify_ssl=False,
        timeout=60.0,
    )


SUMMARY_ROW = {
    "incident_id": "inc-checkout-payment-2026-06-06",
    "services": "checkout-service,payment-service",
    "severities": "SEV-2",
    "started_at": "1717682460",
    "ended_at": "1717684980",
}

EVENT_ROW = {
    "incident_id": "inc-checkout-payment-2026-06-06",
    "event_id": "evt-payment-deploy",
    "evidence_id": "ev-payment-deploy",
    "time": "1717682820",
    "service": "payment-service",
    "event_type": "deploy",
    "severity": "info",
    "title": "payment-service v2.18.0 deployed",
    "description": "Deploy marker shows payment-service v2.18.0 rollout completed.",
    "region": "us-east,us-west",
    "sourcetype": "deploy",
    "index": "ops_demo",
    "version": "v2.18.0",
}


def fake_executor(spl: str) -> list[dict]:
    return [SUMMARY_ROW] if "stats" in spl else [EVENT_ROW]


# --------------------------------------------------------------------------- #
# Adapter behavior (no live MCP server; query execution is injected)
# --------------------------------------------------------------------------- #


def test_mcp_adapter_lists_incidents() -> None:
    adapter = SplunkMcpAdapter(config=make_config(), query_executor=fake_executor)

    incidents = adapter.list_incidents()

    assert len(incidents) == 1
    assert incidents[0].id == "inc-checkout-payment-2026-06-06"
    assert incidents[0].service == "checkout-service"


def test_mcp_adapter_tags_evidence_source_as_mcp() -> None:
    adapter = SplunkMcpAdapter(config=make_config(), query_executor=fake_executor)

    events = adapter.fetch_incident_events("inc-checkout-payment-2026-06-06")

    assert len(events) == 1
    assert events[0].evidence.source == "splunk_mcp"
    assert events[0].evidence.id == "ev-payment-deploy"
    assert events[0].evidence.fields["version"] == "v2.18.0"


def test_mcp_adapter_raises_keyerror_for_empty_result() -> None:
    adapter = SplunkMcpAdapter(config=make_config(), query_executor=lambda spl: [])

    with pytest.raises(KeyError):
        adapter.fetch_incident_events("does-not-exist")


def test_mcp_adapter_status_reports_configuration() -> None:
    configured = SplunkMcpAdapter(config=make_config(token="abc"), query_executor=fake_executor)
    unconfigured = SplunkMcpAdapter(config=make_config(token=None), query_executor=fake_executor)

    assert configured.status().source == "splunk_mcp"
    assert "configured for" in configured.status().description
    assert "not configured" in unconfigured.status().description


# --------------------------------------------------------------------------- #
# Tool-result parsing (covers the shapes the MCP run-query tool may return)
# --------------------------------------------------------------------------- #


class _FakeText:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResult:
    def __init__(self, content=None, structured=None, is_error=False) -> None:
        self.content = content or []
        self.structuredContent = structured
        self.isError = is_error


def test_rows_from_structured_results_key() -> None:
    result = _FakeResult(structured={"results": [{"a": "1"}, {"b": "2"}]})
    assert rows_from_tool_result(result) == [{"a": "1"}, {"b": "2"}]


def test_rows_from_text_json_array() -> None:
    result = _FakeResult(content=[_FakeText('[{"a": "1"}, {"b": "2"}]')])
    assert rows_from_tool_result(result) == [{"a": "1"}, {"b": "2"}]


def test_rows_from_text_ndjson_export_style() -> None:
    payload = '{"preview": false, "result": {"x": "1"}}\n{"result": {"y": "2"}}'
    assert _rows_from_text(payload) == [{"x": "1"}, {"y": "2"}]


def test_rows_from_text_empty() -> None:
    assert _rows_from_text("") == []
