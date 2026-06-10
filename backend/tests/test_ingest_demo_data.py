from io import BytesIO
from urllib.error import HTTPError

from backend.app.demo_data import demo_events
from scripts.ingest_demo_data import (
    build_management_event,
    ensure_index,
    format_stream_event,
)


def test_management_event_contains_searchable_incident_fields() -> None:
    event = demo_events()[1]

    payload = build_management_event(event)

    assert payload["incident_id"] == "inc-checkout-payment-2026-06-06"
    assert payload["event_id"] == "evt-payment-deploy"
    assert payload["evidence_id"] == "ev-payment-deploy"
    assert payload["service"] == "payment-service"
    assert payload["event_type"] == "deploy"
    assert payload["version"] == "v2.18.0"


def test_ensure_index_ignores_existing_index(monkeypatch) -> None:
    def fake_urlopen(*args, **kwargs):
        raise HTTPError(
            url="https://127.0.0.1:8089/services/data/indexes",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=BytesIO(b"already exists"),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    ensure_index("https://127.0.0.1:8089", "admin", "password", "ops_demo")


def test_format_stream_event_prefixes_epoch_for_splunk_timestamp() -> None:
    payload = {"event_id": "evt-payment-deploy"}

    formatted = format_stream_event(payload, 1780754820.0)

    assert formatted.startswith('1780754820.0 {"event_id":"evt-payment-deploy"}')
    assert formatted.endswith("\n")
