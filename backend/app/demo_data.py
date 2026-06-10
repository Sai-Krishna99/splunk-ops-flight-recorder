from datetime import datetime, timezone

from backend.app.models import Evidence, IncidentEvent, IncidentSummary

DEMO_INCIDENT_ID = "inc-checkout-payment-2026-06-06"


def utc_time(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 6, hour, minute, tzinfo=timezone.utc)


def make_evidence(
    evidence_id: str,
    title: str,
    timestamp: datetime,
    sourcetype: str,
    query: str,
    fields: dict[str, str | int | float],
) -> Evidence:
    return Evidence(
        id=evidence_id,
        title=title,
        source="splunk_demo",
        query=query,
        sourcetype=sourcetype,
        timestamp=timestamp,
        fields=fields,
    )


def demo_incident_summary() -> IncidentSummary:
    return IncidentSummary(
        id=DEMO_INCIDENT_ID,
        title="Checkout degradation after payment-service deploy",
        service="checkout-service",
        severity="SEV-2",
        status="postmortem_ready",
        started_at=utc_time(14, 11),
        ended_at=utc_time(14, 43),
        confidence=0.91,
    )


def demo_events() -> list[IncidentEvent]:
    return [
        IncidentEvent(
            id="evt-baseline-checkout",
            timestamp=utc_time(14, 0),
            service="checkout-service",
            event_type="baseline",
            severity="info",
            title="Checkout baseline healthy",
            description="p95 latency was 220 ms and checkout success rate was 99.2%.",
            region="global",
            evidence=make_evidence(
                "ev-baseline-checkout",
                "Checkout service baseline metrics",
                utc_time(14, 0),
                "metrics",
                "index=ops_demo service=checkout-service metric IN (p95_latency_ms,success_rate) earliest=-15m latest=14:00",
                {"p95_latency_ms": 220, "success_rate": 99.2},
            ),
        ),
        IncidentEvent(
            id="evt-payment-deploy",
            timestamp=utc_time(14, 7),
            service="payment-service",
            event_type="deploy",
            severity="info",
            title="payment-service v2.18.0 deployed",
            description="Deploy marker shows payment-service v2.18.0 rollout completed in us-east and us-west.",
            region="us-east,us-west",
            evidence=make_evidence(
                "ev-payment-deploy",
                "Payment deploy marker",
                utc_time(14, 7),
                "deploy",
                "index=ops_demo sourcetype=deploy service=payment-service version=v2.18.0",
                {"version": "v2.18.0", "commit": "8f4c2ad", "regions": "us-east,us-west"},
            ),
        ),
        IncidentEvent(
            id="evt-latency-spike",
            timestamp=utc_time(14, 11),
            service="checkout-service",
            event_type="metric_anomaly",
            severity="warning",
            title="Checkout p95 latency spike",
            description="checkout-service p95 latency increased from 220 ms to 1450 ms.",
            region="us-east",
            evidence=make_evidence(
                "ev-latency-spike",
                "Checkout latency anomaly",
                utc_time(14, 11),
                "metrics",
                "index=ops_demo service=checkout-service metric=p95_latency_ms earliest=14:00 latest=14:15",
                {"baseline_p95_ms": 220, "observed_p95_ms": 1450, "region": "us-east"},
            ),
        ),
        IncidentEvent(
            id="evt-payment-retries",
            timestamp=utc_time(14, 14),
            service="payment-service",
            event_type="dependency",
            severity="critical",
            title="Payment retry rate increased",
            description="Payment retries rose to 18 retry attempts per second from a baseline below 2.",
            region="us-east",
            evidence=make_evidence(
                "ev-payment-retries",
                "Payment retry surge",
                utc_time(14, 14),
                "metrics",
                "index=ops_demo service=payment-service metric=retry_rate earliest=14:07 latest=14:20",
                {"baseline_retries_per_sec": 1.7, "observed_retries_per_sec": 18.0},
            ),
        ),
        IncidentEvent(
            id="evt-http-errors",
            timestamp=utc_time(14, 18),
            service="checkout-service",
            event_type="log_anomaly",
            severity="critical",
            title="HTTP 502/504 errors increased",
            description="Checkout logs show elevated 502 and 504 responses while waiting on payment-service.",
            region="us-east",
            evidence=make_evidence(
                "ev-http-errors",
                "Checkout gateway errors",
                utc_time(14, 18),
                "access_combined",
                "index=ops_demo service=checkout-service status IN (502,504) dependency=payment-service",
                {"status_502": 284, "status_504": 191, "dependency": "payment-service"},
            ),
        ),
        IncidentEvent(
            id="evt-customer-impact",
            timestamp=utc_time(14, 22),
            service="checkout-service",
            event_type="customer_impact",
            severity="critical",
            title="Checkout success rate dropped",
            description="Checkout success rate dropped to 81.4% for customers in us-east and us-west.",
            region="us-east,us-west",
            evidence=make_evidence(
                "ev-customer-impact",
                "Checkout success rate impact",
                utc_time(14, 22),
                "business_metric",
                "index=ops_demo metric=checkout_success_rate earliest=14:00 latest=14:25 by region",
                {"success_rate": 81.4, "affected_orders": 1260, "regions": "us-east,us-west"},
            ),
        ),
        IncidentEvent(
            id="evt-auth-healthy",
            timestamp=utc_time(14, 25),
            service="auth-service",
            event_type="baseline",
            severity="info",
            title="Auth remains healthy",
            description="Auth latency and error rate stayed inside baseline during the incident window.",
            region="global",
            evidence=make_evidence(
                "ev-auth-healthy",
                "Auth service comparison",
                utc_time(14, 25),
                "metrics",
                "index=ops_demo service=auth-service earliest=14:00 latest=14:30",
                {"p95_latency_ms": 95, "error_rate": 0.02},
            ),
        ),
        IncidentEvent(
            id="evt-rollback",
            timestamp=utc_time(14, 36),
            service="payment-service",
            event_type="rollback",
            severity="info",
            title="payment-service rolled back to v2.17.3",
            description="Rollback marker shows payment-service returned to v2.17.3.",
            region="us-east,us-west",
            evidence=make_evidence(
                "ev-rollback",
                "Payment rollback marker",
                utc_time(14, 36),
                "deploy",
                "index=ops_demo sourcetype=deploy service=payment-service action=rollback",
                {"from_version": "v2.18.0", "to_version": "v2.17.3"},
            ),
        ),
        IncidentEvent(
            id="evt-recovery",
            timestamp=utc_time(14, 43),
            service="checkout-service",
            event_type="recovery",
            severity="info",
            title="Checkout metrics recovered",
            description="Checkout p95 latency returned to 260 ms and success rate recovered to 98.9%.",
            region="global",
            evidence=make_evidence(
                "ev-recovery",
                "Checkout recovery metrics",
                utc_time(14, 43),
                "metrics",
                "index=ops_demo service=checkout-service metric IN (p95_latency_ms,success_rate) earliest=14:36 latest=14:45",
                {"p95_latency_ms": 260, "success_rate": 98.9},
            ),
        ),
    ]
