# Splunk MCP Server Integration

Ops Flight Recorder retrieves incident evidence through the **official Splunk MCP
Server** (Splunkbase app **7931**, `Splunk_MCP_Server` v1.2.0). In this mode the
backend acts as an MCP client: it runs the same SPL searches as the REST adapter,
but executes them through the MCP Server's `splunk_run_query` tool over streamable
HTTP, and tags evidence with source `splunk_mcp`.

This integration is verified end to end against a local Splunk Enterprise 10.4.0
with the MCP Server app installed.

## How It Connects

- **Transport:** streamable HTTP (the MCP Server runs inside Splunk).
- **Endpoint:** `https://<splunk-host>:8089/services/mcp` (POST only).
- **Auth:** `Authorization: Bearer <token>` — a Splunk-issued JWT (audience `mcp`)
  minted by the app's `/services/mcp_token` endpoint.
- **Tool:** `splunk_run_query` with args `query` (required), `earliest_time`,
  `latest_time`, `row_limit`. Tool results come back as `{"results": [...]}`.
- **SDK:** the official `mcp` Python package, imported lazily. The client uses
  `terminate_on_close=False` because Splunk exposes `/services/mcp` as POST-only.

## Setup

1. **Install the app**: download Splunk MCP Server from Splunkbase (app 7931), then:

   ```bash
   /Applications/Splunk/bin/splunk install app /path/to/splunk-mcp-server_120.tgz -auth admin:<pw>
   /Applications/Splunk/bin/splunk restart
   ```

   Confirm `/services/mcp` responds (HTTP 400 to an empty POST means it is live).

2. **Ingest the demo data** (see the README) so `index=ops_demo` has the nine
   `ops-flight-recorder` events.

3. **Mint a token** (the `admin` role already has `mcp_tool_admin` /
   `mcp_tool_execute`):

   ```bash
   curl -sk -u admin:<pw> \
     "https://127.0.0.1:8089/services/mcp_token?output_mode=json&username=admin&expires_on=%2B30d"
   # -> {"token": "<bearer token>"}
   ```

4. **Configure the environment** (macOS / Linux):

   ```bash
   export OPS_FLIGHT_RECORDER_ADAPTER="mcp"
   export SPLUNK_BASE_URL="https://127.0.0.1:8089"   # MCP URL derived as .../services/mcp
   export SPLUNK_MCP_TOKEN="<bearer token from step 3>"
   export SPLUNK_INDEX="ops_demo"
   export SPLUNK_VERIFY_SSL="false"
   # Defaults already match the app; override only if needed:
   # export SPLUNK_MCP_TOOL="splunk_run_query"
   # export SPLUNK_MCP_QUERY_ARG="query"
   ```

5. **Run and confirm** `source = splunk_mcp`:

   ```bash
   uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
   # GET http://127.0.0.1:8011/api/adapter/status  -> "source": "splunk_mcp"
   ```

## Searches Executed

The list and event searches strip the ingested `<epoch> {json}` prefix and use
`spath` so the JSON fields extract; see `incident_list_search` /
`incident_events_search` in `backend/app/splunk_client.py`. They are passed to the
MCP `splunk_run_query` tool as the `query` argument.

## Notes

- `require_encrypted_token = true` is the app default, but Splunk-issued JWTs
  (what `/services/mcp_token` returns) are accepted directly — no client-side RSA
  encryption needed.
- The SAIA AI Assistant tools (`generate_spl`, `ask_splunk_question`, ...) appear
  once the Splunk AI Assistant app (Splunkbase 7245) is installed.
- Token lifetime here is 30 days; re-mint with the step-3 command when it expires.

## Why The Adapter Boundary Matters

Splunk access stays behind the `SplunkAdapter` protocol, so demo mode stays
deterministic, REST mode works against local Splunk, and MCP mode swaps only the
query-execution layer. All three return the same normalized models, so the
analysis engine, the AI reasoning layer, the API, and the UI are unchanged.
