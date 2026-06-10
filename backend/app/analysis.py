from backend.app.models import (
    BlastRadius,
    Evidence,
    IncidentAnalysis,
    IncidentEvent,
    IncidentSummary,
    InvestigationPlan,
    PostmortemDraft,
    RecommendedAction,
    RootCauseHypothesis,
    TimelineItem,
)


def build_incident_analysis(
    incident: IncidentSummary,
    events: list[IncidentEvent],
) -> IncidentAnalysis:
    ordered_events = sorted(events, key=lambda event: event.timestamp)
    evidence_by_id = {event.evidence.id: event.evidence for event in ordered_events}
    timeline = build_timeline(ordered_events)
    hypotheses = rank_hypotheses(evidence_by_id)
    blast_radius = summarize_blast_radius(ordered_events)
    actions = recommend_actions(evidence_by_id)
    postmortem = draft_postmortem(incident, timeline, hypotheses[0], blast_radius, actions)

    return IncidentAnalysis(
        incident=incident,
        investigation_plan=build_investigation_plan(incident),
        timeline=timeline,
        hypotheses=hypotheses,
        blast_radius=blast_radius,
        recommended_actions=actions,
        postmortem=postmortem,
    )


def build_investigation_plan(incident: IncidentSummary) -> InvestigationPlan:
    return InvestigationPlan(
        objective=f"Reconstruct {incident.title} from Splunk evidence.",
        steps=[
            "Establish checkout baseline before the detected start time.",
            "Correlate deploy markers with latency, retry, and error anomalies.",
            "Compare impacted dependencies against healthy peer services.",
            "Confirm customer-facing impact and recovery after mitigation.",
        ],
        splunk_queries=[
            "index=ops_demo sourcetype=deploy earliest=14:00 latest=14:45",
            "index=ops_demo service IN (checkout-service,payment-service) earliest=14:00 latest=14:45",
            "index=ops_demo metric=checkout_success_rate earliest=14:00 latest=14:45 by region",
        ],
    )


def build_timeline(events: list[IncidentEvent]) -> list[TimelineItem]:
    return [
        TimelineItem(
            timestamp=event.timestamp,
            service=event.service,
            event_type=event.event_type,
            severity=event.severity,
            title=event.title,
            description=event.description,
            evidence=event.evidence,
        )
        for event in events
    ]


def rank_hypotheses(evidence_by_id: dict[str, Evidence]) -> list[RootCauseHypothesis]:
    payment_deploy_evidence = [
        evidence_by_id["ev-payment-deploy"],
        evidence_by_id["ev-payment-retries"],
        evidence_by_id["ev-http-errors"],
        evidence_by_id["ev-customer-impact"],
        evidence_by_id["ev-rollback"],
        evidence_by_id["ev-recovery"],
    ]

    return [
        RootCauseHypothesis(
            id="hyp-payment-deploy-regression",
            title="payment-service v2.18.0 introduced checkout dependency failures",
            confidence=0.91,
            reasoning=(
                "The payment-service deploy preceded checkout latency by four minutes, retries and "
                "502/504s concentrated on the payment dependency, and rollback was followed by recovery."
            ),
            supporting_evidence=payment_deploy_evidence,
        ),
        RootCauseHypothesis(
            id="hyp-regional-checkout-saturation",
            title="Regional checkout saturation amplified the outage",
            confidence=0.54,
            reasoning=(
                "Most early symptoms appeared in us-east before spreading to us-west, but the strongest "
                "correlation still points to payment-service behavior after deploy."
            ),
            supporting_evidence=[
                evidence_by_id["ev-latency-spike"],
                evidence_by_id["ev-customer-impact"],
            ],
        ),
        RootCauseHypothesis(
            id="hyp-auth-service-regression",
            title="Auth-service regression is unlikely",
            confidence=0.12,
            reasoning="Auth metrics stayed within baseline while checkout and payment degraded.",
            supporting_evidence=[evidence_by_id["ev-auth-healthy"]],
        ),
    ]


def summarize_blast_radius(events: list[IncidentEvent]) -> BlastRadius:
    impact_events = [
        event
        for event in events
        if event.severity == "critical" or event.event_type == "customer_impact"
    ]
    impacted_services = sorted({event.service for event in impact_events})
    impacted_regions = sorted(
        {
            region.strip()
            for event in impact_events
            for region in (event.region or "").split(",")
            if region.strip() and region.strip() != "global"
        }
    )

    return BlastRadius(
        summary=(
            "Checkout customers in us-east and us-west experienced elevated latency and failed "
            "orders while checkout calls waited on payment-service."
        ),
        impacted_services=impacted_services,
        impacted_regions=impacted_regions,
        customer_impact="Checkout success rate dropped to 81.4%, affecting about 1,260 orders.",
        key_metrics=[
            "checkout p95 latency: 220 ms to 1450 ms",
            "payment retry rate: 1.7/s to 18/s",
            "checkout success rate: 99.2% to 81.4%",
        ],
        evidence=[event.evidence for event in impact_events],
    )


def recommend_actions(evidence_by_id: dict[str, Evidence]) -> list[RecommendedAction]:
    return [
        RecommendedAction(
            priority="p0",
            title="Keep payment-service on v2.17.3 until retry regression is fixed",
            owner="payments-oncall",
            rationale="Rollback correlated with checkout recovery and isolates the likely bad deploy.",
            evidence=[evidence_by_id["ev-rollback"], evidence_by_id["ev-recovery"]],
        ),
        RecommendedAction(
            priority="p1",
            title="Add payment retry budget and checkout dependency circuit breaker",
            owner="platform-oncall",
            rationale="Retry amplification turned a payment regression into customer-facing checkout failures.",
            evidence=[evidence_by_id["ev-payment-retries"], evidence_by_id["ev-http-errors"]],
        ),
        RecommendedAction(
            priority="p1",
            title="Create a Splunk alert for deploy-correlated retry spikes",
            owner="observability",
            rationale="The earliest high-signal pattern was a retry surge shortly after a deploy marker.",
            evidence=[evidence_by_id["ev-payment-deploy"], evidence_by_id["ev-payment-retries"]],
        ),
    ]


def draft_postmortem(
    incident: IncidentSummary,
    timeline: list[TimelineItem],
    top_hypothesis: RootCauseHypothesis,
    blast_radius: BlastRadius,
    actions: list[RecommendedAction],
) -> PostmortemDraft:
    return PostmortemDraft(
        summary=(
            "Checkout degraded after payment-service v2.18.0 was deployed. Splunk evidence shows "
            "payment retries and gateway errors rising before customer checkout success dropped."
        ),
        root_cause=top_hypothesis.title,
        impact=blast_radius.customer_impact,
        resolution="payment-service was rolled back to v2.17.3 at 14:36 UTC and checkout recovered by 14:43 UTC.",
        timeline=[f"{item.timestamp.isoformat()} - {item.title}" for item in timeline],
        prevention_tasks=[action.title for action in actions],
        evidence_refs=[
            evidence.id
            for hypothesis in [top_hypothesis]
            for evidence in hypothesis.supporting_evidence
        ],
    )
