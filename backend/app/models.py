from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


EventType = Literal[
    "deploy",
    "alert",
    "metric_anomaly",
    "log_anomaly",
    "dependency",
    "customer_impact",
    "rollback",
    "recovery",
    "baseline",
]

Severity = Literal["info", "warning", "critical"]


class Evidence(BaseModel):
    id: str
    title: str
    source: Literal["splunk_demo", "splunk_search", "splunk_mcp"]
    query: str
    index: str = "ops_demo"
    sourcetype: str
    timestamp: datetime
    fields: dict[str, str | int | float]


class IncidentEvent(BaseModel):
    id: str
    timestamp: datetime
    service: str
    event_type: EventType
    severity: Severity
    title: str
    description: str
    region: str | None = None
    evidence: Evidence


class IncidentSummary(BaseModel):
    id: str
    title: str
    service: str
    severity: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)


class TimelineItem(BaseModel):
    timestamp: datetime
    service: str
    event_type: EventType
    severity: Severity
    title: str
    description: str
    evidence: Evidence


class RootCauseHypothesis(BaseModel):
    id: str
    title: str
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    supporting_evidence: list[Evidence]


class BlastRadius(BaseModel):
    summary: str
    impacted_services: list[str]
    impacted_regions: list[str]
    customer_impact: str
    key_metrics: list[str]
    evidence: list[Evidence]


class RecommendedAction(BaseModel):
    priority: Literal["p0", "p1", "p2"]
    title: str
    owner: str
    rationale: str
    evidence: list[Evidence]


class PostmortemDraft(BaseModel):
    summary: str
    root_cause: str
    impact: str
    resolution: str
    timeline: list[str]
    prevention_tasks: list[str]
    evidence_refs: list[str]


class InvestigationPlan(BaseModel):
    objective: str
    steps: list[str]
    splunk_queries: list[str]


class IncidentAnalysis(BaseModel):
    incident: IncidentSummary
    investigation_plan: InvestigationPlan
    timeline: list[TimelineItem]
    hypotheses: list[RootCauseHypothesis]
    blast_radius: BlastRadius
    recommended_actions: list[RecommendedAction]
    postmortem: PostmortemDraft
