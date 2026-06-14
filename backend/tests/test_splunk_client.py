import json

from backend.app.splunk_client import (
    RealSplunkAdapter,
    SplunkMcpAdapter,
    SplunkConfig,
    parse_export_rows,
    row_to_incident_event,
    row_to_incident_summary,
)


class FakeSplunkClient:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.searches: list[str] = []

    def export_search(self, search: str) -> list[dict[str, str]]:
        self.searches.append(search)
        return self.rows


def test_parse_export_rows_reads_splunk_result_lines() -> None:
    payload = "\n".join(
        [
            json.dumps({"preview": False, "result": {"event_id": "evt-1"}}),
            json.dumps({"preview": False, "result": {"event_id": "evt-2"}}),
        ]
    )

    assert parse_export_rows(payload) == [
        {"event_id": "evt-1"},
        {"event_id": "evt-2"},
    ]


def test_row_to_incident_event_maps_splunk_fields() -> None:
    event = row_to_incident_event(
        {
            "event_epoch": "1780754820.0",
            "_time": "1780754820.0",
            "time": "2026-06-06T14:07:00+00:00",
            "event_id": "evt-payment-deploy",
            "evidence_id": "ev-payment-deploy",
            "service": "payment-service",
            "event_type": "deploy",
            "severity": "info",
            "title": "payment-service v2.18.0 deployed",
            "description": "Deploy marker found in Splunk.",
            "region": "us-east,us-west",
            "query": "index=ops_demo service=payment-service",
            "sourcetype": "deploy",
            "version": "v2.18.0",
        },
        default_index="ops_demo",
    )

    assert event.id == "evt-payment-deploy"
    assert event.event_type == "deploy"
    assert event.evidence.source == "splunk_search"
    assert event.evidence.fields["version"] == "v2.18.0"


def test_real_adapter_uses_splunk_search_rows() -> None:
    config = SplunkConfig(
        base_url="https://127.0.0.1:8089",
        index="ops_demo",
        username="admin",
        password="changed",
        token=None,
        verify_ssl=False,
    )
    client = FakeSplunkClient(
        [
            {
                "_time": "1780754820.0",
                "event_epoch": "1780754820.0",
                "time": "2026-06-06T14:07:00+00:00",
                "event_id": "evt-payment-deploy",
                "evidence_id": "ev-payment-deploy",
                "service": "payment-service",
                "event_type": "deploy",
                "severity": "info",
                "title": "payment-service v2.18.0 deployed",
                "description": "Deploy marker found in Splunk.",
                "region": "us-east,us-west",
                "query": "index=ops_demo service=payment-service",
                "sourcetype": "deploy",
                "version": "v2.18.0",
            }
        ]
    )

    adapter = RealSplunkAdapter(config=config, client=client)
    events = adapter.fetch_incident_events("inc-checkout-payment-2026-06-06")

    assert events[0].service == "payment-service"
    assert 'incident_id="inc-checkout-payment-2026-06-06"' in client.searches[0]


def test_incident_summary_prefers_checkout_service() -> None:
    summary = row_to_incident_summary(
        {
            "incident_id": "inc-checkout-payment-2026-06-06",
            "services": "auth-service\ncheckout-service\npayment-service",
            "severities": "info\ncritical",
            "started_at": "2026-06-06T14:00:00+00:00",
            "ended_at": "2026-06-06T14:43:00+00:00",
        }
    )

    assert summary.service == "checkout-service"
    assert summary.title == "Checkout degradation after payment-service deploy"


def test_incident_summary_handles_splunk_multivalue_lists() -> None:
    summary = row_to_incident_summary(
        {
            "incident_id": "inc-checkout-payment-2026-06-06",
            "services": ["auth-service", "checkout-service", "payment-service"],
            "severities": ["info", "critical"],
            "started_at": "2026-06-06T14:00:00+00:00",
            "ended_at": "2026-06-06T14:43:00+00:00",
        }
    )

    assert summary.service == "checkout-service"


def test_mcp_adapter_reports_unconfigured_without_token(monkeypatch) -> None:
    monkeypatch.delenv("SPLUNK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)

    status = SplunkMcpAdapter(query_executor=lambda spl: []).status()

    assert status.source == "splunk_mcp"
    assert "not configured" in status.description
