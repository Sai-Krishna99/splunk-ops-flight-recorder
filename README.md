# Ops Flight Recorder

Ops Flight Recorder is an incident reconstruction workspace for Splunk. It turns
logs, metrics, deploy markers, and business impact events into an evidence-backed
timeline, ranked root-cause hypotheses, blast-radius summary, recommended
actions, and a postmortem draft.

The current demo focuses on one checkout incident:

- `payment-service` deploys `v2.18.0`
- `checkout-service` latency and payment retries spike
- 502/504 errors increase
- checkout success rate drops across regions
- rollback restores the system

## Run Locally

Install dependencies and run tests:

```powershell
uv run pytest
```

Run in deterministic demo mode:

```powershell
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
```

Open:

```text
http://127.0.0.1:8011
```

## Run With Local Splunk

Prerequisites:

- Splunk Enterprise is installed and running locally.
- You can log in to Splunk Web.
- The Splunk management API is reachable on port `8089`.
- `uv` is installed for Python environment management.

Splunk Web usually runs on:

```text
http://127.0.0.1:8000
```

The Splunk management API usually runs on:

```text
https://127.0.0.1:8089
```

The app uses the management API for both search and demo ingestion. HTTP Event
Collector is not required for the default local demo path.

Set local environment variables:

```powershell
$env:OPS_FLIGHT_RECORDER_ADAPTER="real"
$env:SPLUNK_USERNAME="admin"
$env:SPLUNK_PASSWORD="<local Splunk password>"
$env:SPLUNK_BASE_URL="https://127.0.0.1:8089"
$env:SPLUNK_INDEX="ops_demo"
$env:SPLUNK_VERIFY_SSL="false"
```

macOS / Linux (zsh/bash) — same variables with `export`:

```bash
export OPS_FLIGHT_RECORDER_ADAPTER="real"
export SPLUNK_USERNAME="admin"
export SPLUNK_PASSWORD="<local Splunk password>"
export SPLUNK_BASE_URL="https://127.0.0.1:8089"
export SPLUNK_INDEX="ops_demo"
export SPLUNK_VERIFY_SSL="false"
```

Ingest the demo incident through the Splunk management API:

```powershell
uv run python scripts\ingest_demo_data.py --send-management
```

The ingest script creates the `ops_demo` index if it is missing, then writes the
nine deterministic incident events with source `ops-flight-recorder`.

Start the app:

```powershell
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
```

The UI should show `REAL via splunk_search` and evidence source
`splunk_search`.

## AI Reasoning (Splunk AI)

By default the analysis runs a deterministic, rule-based engine, which keeps the
demo reliable. To generate the ranked root-cause hypotheses, recommended
actions, and postmortem with a model instead, enable the AI analyst. The AI
layer is provider-agnostic and adds no extra dependencies. If the model is
unreachable or misconfigured it automatically falls back to the deterministic
engine, so the API never breaks during a demo.

The model may only cite evidence IDs returned from Splunk, so it cannot
fabricate evidence.

Splunk hosted models / any OpenAI-compatible endpoint (macOS / Linux):

```bash
export OPS_FLIGHT_RECORDER_AI="openai"
export OPENAI_BASE_URL="<hosted model endpoint, e.g. https://.../v1>"
export OPENAI_API_KEY="<token>"          # or SPLUNK_AI_API_KEY
export OPS_FLIGHT_RECORDER_AI_MODEL="<model name>"
```

Anthropic Claude:

```bash
export OPS_FLIGHT_RECORDER_AI="anthropic"
export ANTHROPIC_API_KEY="<key>"
export OPS_FLIGHT_RECORDER_AI_MODEL="claude-sonnet-4-6"
```

On Windows PowerShell use the `$env:NAME="value"` syntax instead of `export`.

When AI is active, `GET /api/incidents/{id}/analysis` returns `"reasoning":
"ai"` together with a `reasoning_model` field; otherwise it returns
`"reasoning": "deterministic"`.

## Troubleshooting

If Splunk Web does not open, confirm Splunk is running and use:

```text
http://127.0.0.1:8000
```

If the app does not open, use HTTP, not HTTPS:

```text
http://127.0.0.1:8011
```

If `/api/adapter/status` still reports `demo`, restart Uvicorn from the same
terminal where the `OPS_FLIGHT_RECORDER_ADAPTER` and `SPLUNK_*` environment
variables were set.

If ingest fails with an authentication error, confirm that the same
`SPLUNK_USERNAME` and `SPLUNK_PASSWORD` work in Splunk Web.

If port `8011` is already in use, choose another port and open that URL:

```powershell
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8012
```

## Verification

Useful checks:

```powershell
uv run pytest
uv run python scripts\ingest_demo_data.py
```

API checks:

```text
http://127.0.0.1:8011/api/adapter/status
http://127.0.0.1:8011/api/incidents
http://127.0.0.1:8011/api/incidents/inc-checkout-payment-2026-06-06/analysis
```

## Run With Splunk MCP Server

The backend can retrieve evidence through the official **Splunk MCP Server**
(Splunkbase app 7931) instead of the REST API. It connects over streamable HTTP
to `https://<host>:8089/services/mcp` with a Bearer token, runs the same SPL
searches through the MCP run-query tool, and tags evidence with source
`splunk_mcp`.

macOS / Linux:

```bash
# 1) Install the app (Splunkbase 7931), restart Splunk, then mint a token:
TOKEN=$(curl -sk -u admin:<pw> \
  "https://127.0.0.1:8089/services/mcp_token?output_mode=json&username=admin&expires_on=%2B30d" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2) Point the app at the MCP server:
export OPS_FLIGHT_RECORDER_ADAPTER="mcp"
export SPLUNK_BASE_URL="https://127.0.0.1:8089"
export SPLUNK_MCP_TOKEN="$TOKEN"
export SPLUNK_INDEX="ops_demo"
export SPLUNK_VERIFY_SSL="false"
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
```

The UI sidebar should then report evidence source `splunk_mcp`. The `mcp` Python
SDK (in `pyproject.toml`) is imported only in this mode. Full setup, tool
overrides, and the searches are documented in
[docs/splunk-mcp.md](docs/splunk-mcp.md).

See also [docs/architecture.md](docs/architecture.md) and
[docs/demo-script.md](docs/demo-script.md).
