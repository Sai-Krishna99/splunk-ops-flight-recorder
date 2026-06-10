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

## Splunk MCP Path

The current working integration uses Splunk REST search export through the local
Splunk management API. The backend keeps Splunk access behind an adapter so a
Splunk MCP Server implementation can replace the REST client while preserving
the same `IncidentEvent` and `Evidence` contract.

If a Splunk MCP Server tool is available to the runtime, use:

```powershell
$env:OPS_FLIGHT_RECORDER_ADAPTER="mcp"
```

The current repository includes the adapter slot and documented searches, while
the working local demo uses the REST fallback.

See [docs/architecture.md](docs/architecture.md) and
[docs/demo-script.md](docs/demo-script.md).
