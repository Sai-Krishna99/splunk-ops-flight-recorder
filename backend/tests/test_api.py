from fastapi.testclient import TestClient

from backend.app.main import app


def test_api_returns_structured_demo_analysis() -> None:
    client = TestClient(app)

    response = client.get("/api/incidents/inc-checkout-payment-2026-06-06/analysis")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["timeline"]) == 9
    assert payload["hypotheses"][0]["id"] == "hyp-payment-deploy-regression"
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
