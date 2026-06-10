# Demo Script

Target length: under 3 minutes.

## 1. Open The Workspace

Open:

```text
http://127.0.0.1:8011
```

Show that the sidebar reports:

```text
REAL via splunk_search
```

Explain that the evidence is being read back from local Splunk.

## 2. Establish The Incident

Point to the incident header:

- Checkout degradation after payment-service deploy
- `checkout-service`
- critical
- investigating
- incident window from 14:00 UTC to 14:43 UTC

## 3. Walk The Timeline

Show the sequence:

1. Checkout baseline healthy
2. `payment-service v2.18.0` deployed
3. Checkout p95 latency spikes
4. Payment retries increase
5. 502/504 errors increase
6. Checkout success rate drops
7. Auth remains healthy
8. Payment rollback
9. Checkout recovery

Click an evidence chip and show that the Evidence Explorer highlights the
matching Splunk-backed evidence record.

## 4. Explain Root Cause

Show the top hypothesis:

```text
payment-service v2.18.0 introduced checkout dependency failures
```

Point to:

- confidence score
- scoring signals
- supporting evidence chips

## 5. Show Blast Radius And Actions

Show impacted services and regions:

- checkout-service
- payment-service
- us-east
- us-west

Show recommended actions:

- keep payment-service on stable version
- add retry budget and circuit breaker
- add deploy-correlated retry alert

## 6. Finish With Postmortem

Show the generated postmortem draft:

- summary
- root cause
- impact and resolution
- prevention tasks

Close by saying that Splunk remains the source of truth; Ops Flight Recorder
turns Splunk evidence into an incident reconstruction workspace.
