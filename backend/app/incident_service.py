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
    def __init__(self, splunk_adapter: SplunkAdapter | None = None) -> None:
        self.splunk_adapter = splunk_adapter or build_splunk_adapter()

    def list_incidents(self) -> list[IncidentSummary]:
        return self.splunk_adapter.list_incidents()

    def analyze_incident(self, incident_id: str) -> IncidentAnalysis:
        incidents = {incident.id: incident for incident in self.splunk_adapter.list_incidents()}
        if incident_id not in incidents:
            raise KeyError(f"Unknown incident: {incident_id}")

        events = self.splunk_adapter.fetch_incident_events(incident_id)
        return build_incident_analysis(incidents[incident_id], events)

    def list_events(self, incident_id: str) -> list[IncidentEvent]:
        return self.splunk_adapter.fetch_incident_events(incident_id)

    def list_evidence(self, incident_id: str) -> list[Evidence]:
        return [event.evidence for event in self.list_events(incident_id)]

    def adapter_status(self) -> AdapterStatus:
        return self.splunk_adapter.status()
