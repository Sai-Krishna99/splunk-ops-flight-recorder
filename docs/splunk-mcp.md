# Splunk MCP Integration Plan

## Current State

Ops Flight Recorder currently has a working local Splunk integration through
Splunk REST search export on the management API:

```text
https://127.0.0.1:8089/services/search/jobs/export
```

This is enough for the demo to show real Splunk-backed evidence with source:

```text
splunk_search
```

## MCP Target

The MCP target is to replace the REST search execution in `RealSplunkAdapter`
with Splunk MCP Server tool calls while preserving the rest of the app.

The MCP adapter should return the same normalized models:

- `IncidentSummary`
- `IncidentEvent`
- `Evidence`

Evidence from MCP should use:

```text
source = "splunk_mcp"
```

## Required MCP Searches

Incident list:

```spl
search index=ops_demo source=ops-flight-recorder incident_id=*
| spath
| stats min(time) as started_at max(time) as ended_at
        values(service) as services values(severity) as severities
        by incident_id
| sort - started_at
```

Incident events:

```spl
search index=ops_demo source=ops-flight-recorder
      incident_id="inc-checkout-payment-2026-06-06"
| spath
| sort 0 time
```

## Why The Adapter Boundary Matters

The app deliberately keeps Splunk access behind `SplunkAdapter`. That means:

- demo mode stays deterministic,
- REST mode works against local Splunk today,
- MCP can be added by swapping only the query execution layer,
- analysis and UI stay unchanged.

## Implementation Steps

1. Add a `SplunkMcpAdapter`.
2. Configure `OPS_FLIGHT_RECORDER_ADAPTER=mcp`.
3. Execute the two required searches through Splunk MCP Server.
4. Convert MCP result rows with the same row mapping used by REST.
5. Set `Evidence.source` to `splunk_mcp`.
6. Re-run the demo and confirm evidence source changes from `splunk_search` to
   `splunk_mcp`.
