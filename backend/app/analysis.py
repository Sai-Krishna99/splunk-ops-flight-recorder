from backend.app.models import (
    BlastRadius,
    IncidentAnalysis,
    IncidentEvent,
    IncidentSummary,
    InvestigationPlan,
    PostmortemDraft,
    RecommendedAction,
    RootCauseHypothesis,
    TimelineItem,
)


IMPACT_EVENT_TYPES = {"dependency", "log_anomaly", "customer_impact"}
SYMPTOM_EVENT_TYPES = {"metric_anomaly", "dependency", "log_anomaly", "customer_impact"}


def build_incident_analysis(
    incident: IncidentSummary,
    events: list[IncidentEvent],
) -> IncidentAnalysis:
    ordered_events = sorted(events, key=lambda event: event.timestamp)
    timeline = build_timeline(ordered_events)
    hypotheses = rank_hypotheses(incident, ordered_events)
    blast_radius = summarize_blast_radius(ordered_events)
    actions = recommend_actions(ordered_events, hypotheses[0])
    postmortem = draft_postmortem(
        incident,
        timeline,
        hypotheses[0],
        blast_radius,
        actions,
        ordered_events,
    )

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
            (
                "index=ops_demo service IN (checkout-service,payment-service) "
                "earliest=14:00 latest=14:45"
            ),
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


def rank_hypotheses(
    incident: IncidentSummary,
    events: list[IncidentEvent],
) -> list[RootCauseHypothesis]:
    deploy_hypotheses = [
        build_deploy_hypothesis(incident, deploy_event, events)
        for deploy_event in events
        if deploy_event.event_type == "deploy"
    ]
    regional_hypothesis = build_regional_hypothesis(events)
    healthy_hypothesis = build_healthy_peer_hypothesis(incident, events)

    return sorted(
        [*deploy_hypotheses, regional_hypothesis, healthy_hypothesis],
        key=lambda hypothesis: hypothesis.confidence,
        reverse=True,
    )


def build_deploy_hypothesis(
    incident: IncidentSummary,
    deploy_event: IncidentEvent,
    events: list[IncidentEvent],
) -> RootCauseHypothesis:
    deploy_service = deploy_event.service
    version = str(deploy_event.evidence.fields.get("version", "new version"))
    later_symptoms = [
        event
        for event in events
        if event.timestamp > deploy_event.timestamp
        and event.event_type in SYMPTOM_EVENT_TYPES
        and is_related_to_service(event, deploy_service)
    ]
    rollback_events = [
        event
        for event in events
        if event.timestamp > deploy_event.timestamp
        and event.event_type == "rollback"
        and event.service == deploy_service
    ]
    recovery_events = [
        event
        for event in events
        if rollback_events
        and event.timestamp > rollback_events[0].timestamp
        and event.event_type == "recovery"
    ]

    score = 0.26
    if later_symptoms:
        score += 0.25
    if any(event.event_type == "log_anomaly" for event in later_symptoms):
        score += 0.10
    if any(event.event_type == "customer_impact" for event in later_symptoms):
        score += 0.10
    if rollback_events:
        score += 0.10
    if recovery_events:
        score += 0.10

    supporting_events = [deploy_event, *later_symptoms, *rollback_events, *recovery_events]
    reasoning_parts = [
        f"{deploy_service} {version} was deployed before {incident.service} degraded",
        f"{len(later_symptoms)} related anomaly or impact events followed the deploy",
    ]
    if rollback_events and recovery_events:
        reasoning_parts.append("rollback was followed by recovery")

    scoring_signals = [
        f"deploy_before_impact={deploy_event.timestamp < incident.started_at}",
        f"related_symptoms={len(later_symptoms)}",
        f"rollback_seen={bool(rollback_events)}",
        f"recovery_after_rollback={bool(recovery_events)}",
    ]

    return RootCauseHypothesis(
        id=f"hyp-{slugify(deploy_service)}-deploy-regression",
        title=f"{deploy_service} {version} introduced checkout dependency failures",
        confidence=round(min(score, 0.96), 2),
        reasoning=". ".join(reasoning_parts) + ".",
        scoring_signals=scoring_signals,
        supporting_evidence=[event.evidence for event in supporting_events],
    )


def build_regional_hypothesis(events: list[IncidentEvent]) -> RootCauseHypothesis:
    regional_events = [
        event
        for event in events
        if event.region and event.region != "global" and event.event_type in SYMPTOM_EVENT_TYPES
    ]
    impacted_regions = split_regions(regional_events)
    latency_or_impact_events = [
        event
        for event in regional_events
        if event.event_type in {"metric_anomaly", "customer_impact"}
    ]
    confidence = 0.34 + (0.10 * min(len(impacted_regions), 2))

    return RootCauseHypothesis(
        id="hyp-regional-saturation",
        title="Regional checkout saturation amplified the outage",
        confidence=round(confidence, 2),
        reasoning=(
            f"Symptoms appeared across {', '.join(impacted_regions) or 'unknown regions'}, but "
            "regional evidence is weaker than the deploy-to-recovery chain."
        ),
        scoring_signals=[
            f"impacted_regions={len(impacted_regions)}",
            f"regional_symptoms={len(regional_events)}",
            "rollback_explains_recovery=false",
        ],
        supporting_evidence=[event.evidence for event in latency_or_impact_events],
    )


def build_healthy_peer_hypothesis(
    incident: IncidentSummary,
    events: list[IncidentEvent],
) -> RootCauseHypothesis:
    healthy_peer_events = [
        event
        for event in events
        if event.event_type == "baseline"
        and event.service != incident.service
        and "healthy" in event.title.lower()
    ]
    service_name = healthy_peer_events[0].service if healthy_peer_events else "peer service"

    return RootCauseHypothesis(
        id=f"hyp-{slugify(service_name)}-regression",
        title=f"{service_name} regression is unlikely",
        confidence=0.12,
        reasoning=f"{service_name} stayed inside baseline while checkout and payment degraded.",
        scoring_signals=[
            "peer_service_baseline_healthy=true",
            "direct_error_evidence=false",
        ],
        supporting_evidence=[event.evidence for event in healthy_peer_events],
    )


def is_related_to_service(event: IncidentEvent, service: str) -> bool:
    dependency = str(event.evidence.fields.get("dependency", ""))
    return (
        event.service == service
        or dependency == service
        or event.event_type == "customer_impact"
    )


def split_regions(events: list[IncidentEvent]) -> list[str]:
    return sorted(
        {
            region.strip()
            for event in events
            for region in (event.region or "").split(",")
            if region.strip() and region.strip() != "global"
        }
    )


def slugify(value: str) -> str:
    return value.lower().replace("_", "-").replace(" ", "-")


def summarize_blast_radius(events: list[IncidentEvent]) -> BlastRadius:
    impact_events = [
        event
        for event in events
        if event.severity == "critical" or event.event_type in IMPACT_EVENT_TYPES
    ]
    impacted_services = sorted({event.service for event in impact_events})
    impacted_regions = split_regions(impact_events)
    customer_impact_event = next(
        (event for event in events if event.event_type == "customer_impact"),
        None,
    )
    affected_orders = 0
    success_rate = None
    if customer_impact_event:
        affected_orders = int(
            customer_impact_event.evidence.fields.get("affected_orders", 0)
        )
        success_rate = customer_impact_event.evidence.fields.get("success_rate")

    return BlastRadius(
        summary=(
            f"Checkout customers in {format_list(impacted_regions)} experienced elevated latency "
            "and failed orders while checkout calls waited on payment-service."
        ),
        impacted_services=impacted_services,
        impacted_regions=impacted_regions,
        customer_impact=build_customer_impact(success_rate, affected_orders),
        key_metrics=build_key_metrics(events),
        evidence=[event.evidence for event in impact_events],
    )


def build_customer_impact(
    success_rate: str | int | float | None,
    affected_orders: int,
) -> str:
    if success_rate is None:
        return "Customer checkout impact was detected in Splunk business metrics."
    return (
        f"Checkout success rate dropped to {success_rate}%, "
        f"affecting about {affected_orders:,} orders."
    )


def build_key_metrics(events: list[IncidentEvent]) -> list[str]:
    metrics: list[str] = []
    for event in events:
        fields = event.evidence.fields
        if "baseline_p95_ms" in fields and "observed_p95_ms" in fields:
            metrics.append(
                f"{event.service} p95 latency: {fields['baseline_p95_ms']} ms "
                f"to {fields['observed_p95_ms']} ms"
            )
        if "baseline_retries_per_sec" in fields and "observed_retries_per_sec" in fields:
            metrics.append(
                f"{event.service} retry rate: {fields['baseline_retries_per_sec']}/s "
                f"to {fields['observed_retries_per_sec']}/s"
            )
        if event.event_type == "customer_impact" and "success_rate" in fields:
            metrics.append(
                f"checkout success rate: {fields['success_rate']}% during impact window"
            )
    return metrics


def recommend_actions(
    events: list[IncidentEvent],
    top_hypothesis: RootCauseHypothesis,
) -> list[RecommendedAction]:
    rollback = first_event(events, "rollback")
    recovery = first_event(events, "recovery")
    deploy = first_event(events, "deploy")
    retries = first_event(events, "dependency")
    errors = first_event(events, "log_anomaly")
    rollback_version = "the previous stable version"
    if rollback:
        rollback_version = rollback.evidence.fields.get(
            "to_version",
            "the previous stable version",
        )

    return [
        RecommendedAction(
            priority="p0",
            title=f"Keep payment-service on {rollback_version} until retry regression is fixed",
            owner="payments-oncall",
            rationale=f"{top_hypothesis.title} is the highest-confidence root-cause hypothesis.",
            evidence=[event.evidence for event in [rollback, recovery] if event],
        ),
        RecommendedAction(
            priority="p1",
            title="Add payment retry budget and checkout dependency circuit breaker",
            owner="platform-oncall",
            rationale=(
                "Retry amplification turned a payment regression into customer-facing "
                "checkout failures."
            ),
            evidence=[event.evidence for event in [retries, errors] if event],
        ),
        RecommendedAction(
            priority="p1",
            title="Create a Splunk alert for deploy-correlated retry spikes",
            owner="observability",
            rationale=(
                "The earliest high-signal pattern was a retry surge shortly after "
                "a deploy marker."
            ),
            evidence=[event.evidence for event in [deploy, retries] if event],
        ),
    ]


def draft_postmortem(
    incident: IncidentSummary,
    timeline: list[TimelineItem],
    top_hypothesis: RootCauseHypothesis,
    blast_radius: BlastRadius,
    actions: list[RecommendedAction],
    events: list[IncidentEvent],
) -> PostmortemDraft:
    rollback = first_event(events, "rollback")
    recovery = first_event(events, "recovery")
    return PostmortemDraft(
        summary=(
            f"Checkout degraded after {top_hypothesis.title}. Splunk evidence shows "
            "payment retries and gateway errors rising before customer checkout "
            "success dropped."
        ),
        root_cause=top_hypothesis.title,
        impact=blast_radius.customer_impact,
        resolution=build_resolution(rollback, recovery),
        timeline=[f"{item.timestamp.isoformat()} - {item.title}" for item in timeline],
        prevention_tasks=[action.title for action in actions],
        evidence_refs=[
            evidence.id
            for hypothesis in [top_hypothesis]
            for evidence in hypothesis.supporting_evidence
        ],
    )


def first_event(events: list[IncidentEvent], event_type: str) -> IncidentEvent | None:
    return next((event for event in events if event.event_type == event_type), None)


def build_resolution(
    rollback: IncidentEvent | None,
    recovery: IncidentEvent | None,
) -> str:
    if not rollback or not recovery:
        return "Mitigation and recovery steps should be confirmed by the incident commander."
    to_version = rollback.evidence.fields.get("to_version", "the previous stable version")
    rollback_time = rollback.timestamp.strftime("%H:%M UTC")
    recovery_time = recovery.timestamp.strftime("%H:%M UTC")
    return (
        f"payment-service was rolled back to {to_version} at {rollback_time} "
        f"and checkout recovered by {recovery_time}."
    )


def format_list(values: list[str]) -> str:
    if not values:
        return "the impacted regions"
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])} and {values[-1]}"
