from backend.app.analysis import build_incident_analysis
from backend.app.demo_data import demo_events, demo_incident_summary


def test_timeline_is_chronological_and_evidence_backed() -> None:
    analysis = build_incident_analysis(demo_incident_summary(), demo_events())

    timestamps = [item.timestamp for item in analysis.timeline]

    assert timestamps == sorted(timestamps)
    assert analysis.timeline[0].title == "Checkout baseline healthy"
    assert all(item.evidence.query.startswith("index=ops_demo") for item in analysis.timeline)


def test_payment_deploy_is_top_ranked_root_cause() -> None:
    analysis = build_incident_analysis(demo_incident_summary(), demo_events())

    top_hypothesis = analysis.hypotheses[0]

    assert "payment-service v2.18.0" in top_hypothesis.title
    assert top_hypothesis.confidence == 0.91
    assert len(top_hypothesis.supporting_evidence) >= 5
    assert top_hypothesis.supporting_evidence[0].id == "ev-payment-deploy"
    assert "related_symptoms=3" in top_hypothesis.scoring_signals


def test_blast_radius_and_actions_include_customer_impact() -> None:
    analysis = build_incident_analysis(demo_incident_summary(), demo_events())

    assert analysis.blast_radius.impacted_services == ["checkout-service", "payment-service"]
    assert analysis.blast_radius.impacted_regions == ["us-east", "us-west"]
    assert "1,260 orders" in analysis.blast_radius.customer_impact
    assert analysis.recommended_actions[0].priority == "p0"
    assert "v2.17.3" in analysis.recommended_actions[0].title
    assert "checkout-service p95 latency" in analysis.blast_radius.key_metrics[0]


def test_hypothesis_ranking_uses_event_correlation() -> None:
    events = demo_events()
    unrelated_deploy = events[1].model_copy(deep=True)
    unrelated_deploy.id = "evt-inventory-deploy"
    unrelated_deploy.service = "inventory-service"
    unrelated_deploy.title = "inventory-service v1.9.0 deployed"
    unrelated_deploy.evidence.id = "ev-inventory-deploy"
    unrelated_deploy.evidence.fields["version"] = "v1.9.0"

    analysis = build_incident_analysis(demo_incident_summary(), [unrelated_deploy, *events])

    assert analysis.hypotheses[0].id == "hyp-payment-service-deploy-regression"
    assert analysis.hypotheses[0].confidence > analysis.hypotheses[1].confidence


def test_postmortem_uses_top_hypothesis_and_evidence_refs() -> None:
    analysis = build_incident_analysis(demo_incident_summary(), demo_events())

    assert analysis.postmortem.root_cause == analysis.hypotheses[0].title
    assert "Checkout degraded" in analysis.postmortem.summary
    assert "ev-payment-deploy" in analysis.postmortem.evidence_refs
