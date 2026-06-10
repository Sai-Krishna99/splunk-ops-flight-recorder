from fastapi.testclient import TestClient

from backend.app.main import app


def test_api_returns_structured_demo_analysis() -> None:
    client = TestClient(app)

    response = client.get("/api/incidents/inc-checkout-payment-2026-06-06/analysis")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["timeline"]) == 9
    assert payload["hypotheses"][0]["id"] == "hyp-payment-service-deploy-regression"
    assert "scoring_signals" in payload["hypotheses"][0]
    assert payload["blast_radius"]["impacted_services"] == [
        "checkout-service",
        "payment-service",
    ]
    assert payload["recommended_actions"][0]["priority"] == "p0"
    assert payload["postmortem"]["root_cause"] == payload["hypotheses"][0]["title"]


def test_workspace_html_is_served() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Incident Command Workspace" in response.text


def test_api_returns_raw_events_and_evidence() -> None:
    client = TestClient(app)

    events_response = client.get("/api/incidents/inc-checkout-payment-2026-06-06/events")
    evidence_response = client.get("/api/incidents/inc-checkout-payment-2026-06-06/evidence")

    assert events_response.status_code == 200
    assert evidence_response.status_code == 200
    assert len(events_response.json()) == 9
    assert evidence_response.json()[0]["query"].startswith("index=ops_demo")


def test_adapter_status_explains_demo_mode() -> None:
    client = TestClient(app)

    response = client.get("/api/adapter/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "demo"
    assert payload["source"] == "splunk_demo"
    assert any("synthetic checkout incident" in step for step in payload["next_steps"])
