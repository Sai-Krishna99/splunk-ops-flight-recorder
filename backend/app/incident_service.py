from backend.app.ai_analyst import AIAnalyst
from backend.app.analysis import build_incident_analysis
from backend.app.models import (
    AdapterStatus,
    Evidence,
    IncidentAnalysis,
    IncidentEvent,
    IncidentSummary,
)
from backend.app.splunk_client import SplunkAdapter, build_splunk_adapter


class IncidentService:
    def __init__(
        self,
        splunk_adapter: SplunkAdapter | None = None,
        analyst: AIAnalyst | None = None,
    ) -> None:
        self.splunk_adapter = splunk_adapter or build_splunk_adapter()
        self.analyst = analyst or AIAnalyst()

    def list_incidents(self) -> list[IncidentSummary]:
        return self.splunk_adapter.list_incidents()

    def analyze_incident(self, incident_id: str) -> IncidentAnalysis:
        incidents = {incident.id: incident for incident in self.splunk_adapter.list_incidents()}
        if incident_id not in incidents:
            raise KeyError(f"Unknown incident: {incident_id}")

        events = self.splunk_adapter.fetch_incident_events(incident_id)
        analysis = build_incident_analysis(incidents[incident_id], events)
        return self._with_ai_reasoning(analysis, incidents[incident_id], events)

    def _with_ai_reasoning(
        self,
        analysis: IncidentAnalysis,
        incident: IncidentSummary,
        events: list[IncidentEvent],
    ) -> IncidentAnalysis:
        if not self.analyst.enabled:
            return analysis
        try:
            reasoning = self.analyst.reason(incident, events)
        except Exception:
            # AI reasoning is best-effort: fall back to the deterministic engine
            # so the analysis API never fails during a live demo.
            return analysis
        return analysis.model_copy(
            update={
                "hypotheses": reasoning.hypotheses,
                "recommended_actions": reasoning.actions,
                "postmortem": reasoning.postmortem,
                "reasoning": "ai",
                "reasoning_model": reasoning.model,
            }
        )

    def list_events(self, incident_id: str) -> list[IncidentEvent]:
        return self.splunk_adapter.fetch_incident_events(incident_id)

    def list_evidence(self, incident_id: str) -> list[Evidence]:
        return [event.evidence for event in self.list_events(incident_id)]

    def adapter_status(self) -> AdapterStatus:
        return self.splunk_adapter.status()
