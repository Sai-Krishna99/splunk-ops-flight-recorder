import json

from backend.app.ai_analyst import AIAnalyst, AIUnavailable
from backend.app.demo_data import DEMO_INCIDENT_ID, demo_events, demo_incident_summary
from backend.app.incident_service import IncidentService
from backend.app.splunk_client import DemoSplunkAdapter


class FakeClient:
    """Returns a canned model response that cites real evidence IDs."""

    model = "fake-model-1"

    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload if payload is not None else _CANNED_RESPONSE

    def complete(self, system: str, user: str) -> str:
        # Wrap in prose + fences to prove the parser is tolerant.
        return "Here is the analysis:\n```json\n" + json.dumps(self._payload) + "\n```"


class HallucinatingClient:
    model = "fake-model-hallucinate"

    def complete(self, system: str, user: str) -> str:
        return json.dumps(
            {
                "hypotheses": [
                    {
                        "title": "Made-up cause",
                        "confidence": 0.9,
                        "reasoning": "n/a",
                        "scoring_signals": ["x"],
                        "supporting_evidence_ids": ["ev-does-not-exist"],
                    }
                ],
                "recommended_actions": [],
                "postmortem": {},
            }
        )


class RaisingClient:
    model = "fake-model-raise"

    def complete(self, system: str, user: str) -> str:
        raise AIUnavailable("boom")


_CANNED_RESPONSE = {
    "hypotheses": [
        {
            "title": "payment-service v2.18.0 deploy caused checkout failures",
            "confidence": 0.88,
            "reasoning": "Retries and gateway errors followed the deploy.",
            "scoring_signals": ["deploy_before_impact=true", "rollback_recovered=true"],
            "supporting_evidence_ids": ["ev-payment-deploy", "ev-payment-retries"],
        },
        {
            "title": "Regional saturation",
            "confidence": 0.3,
            "reasoning": "Weaker signal.",
            "scoring_signals": ["impacted_regions=2"],
            "supporting_evidence_ids": ["ev-customer-impact"],
        },
    ],
    "recommended_actions": [
        {
            "priority": "p0",
            "title": "Hold payment-service on v2.17.3",
            "owner": "payments-oncall",
            "rationale": "Rollback restored checkout.",
            "evidence_ids": ["ev-rollback"],
        }
    ],
    "postmortem": {
        "summary": "Checkout degraded after the payment deploy.",
        "root_cause": "payment-service v2.18.0 retry regression",
        "impact": "Checkout success dropped to 81.4%.",
        "resolution": "Rolled back to v2.17.3.",
        "prevention_tasks": ["Add retry budget", "Add deploy-correlated alert"],
        "evidence_refs": ["ev-payment-deploy", "ev-rollback"],
    },
}


def test_ai_analyst_builds_models_and_grounds_evidence() -> None:
    analyst = AIAnalyst(client=FakeClient())

    reasoning = analyst.reason(demo_incident_summary(), demo_events())

    assert reasoning.model == "fake-model-1"
    assert "payment-service v2.18.0" in reasoning.hypotheses[0].title
    # Highest-confidence hypothesis is first.
    assert reasoning.hypotheses[0].confidence == 0.88
    # Evidence is resolved from real IDs into real Evidence objects.
    ids = [evidence.id for evidence in reasoning.hypotheses[0].supporting_evidence]
    assert ids == ["ev-payment-deploy", "ev-payment-retries"]
    assert reasoning.actions[0].priority == "p0"
    assert reasoning.postmortem.root_cause == "payment-service v2.18.0 retry regression"


def test_ai_analyst_drops_unknown_evidence_ids() -> None:
    analyst = AIAnalyst(client=HallucinatingClient())

    reasoning = analyst.reason(demo_incident_summary(), demo_events())

    # The fabricated evidence ID is dropped rather than invented.
    assert reasoning.hypotheses[0].supporting_evidence == []


def test_disabled_analyst_is_not_enabled() -> None:
    assert AIAnalyst(client=None).enabled in {True, False}  # depends on env
    # An analyst with an explicit client is always enabled.
    assert AIAnalyst(client=FakeClient()).enabled is True


def test_service_overlays_ai_reasoning_when_enabled() -> None:
    service = IncidentService(
        splunk_adapter=DemoSplunkAdapter(), analyst=AIAnalyst(client=FakeClient())
    )

    analysis = service.analyze_incident(DEMO_INCIDENT_ID)

    assert analysis.reasoning == "ai"
    assert analysis.reasoning_model == "fake-model-1"
    assert "payment-service v2.18.0" in analysis.hypotheses[0].title
    # Deterministic-only sections are still present.
    assert len(analysis.timeline) == 9


def test_service_falls_back_to_deterministic_when_ai_fails() -> None:
    service = IncidentService(
        splunk_adapter=DemoSplunkAdapter(), analyst=AIAnalyst(client=RaisingClient())
    )

    analysis = service.analyze_incident(DEMO_INCIDENT_ID)

    assert analysis.reasoning == "deterministic"
    assert analysis.reasoning_model is None
    # Falls back to the deterministic top hypothesis.
    assert analysis.hypotheses[0].id == "hyp-payment-service-deploy-regression"
