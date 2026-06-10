from backend.app.analysis import build_incident_analysis
from backend.app.models import IncidentAnalysis, IncidentSummary
from backend.app.splunk_client import DemoSplunkAdapter, SplunkAdapter


class IncidentService:
    def __init__(self, splunk_adapter: SplunkAdapter | None = None) -> None:
        self.splunk_adapter = splunk_adapter or DemoSplunkAdapter()

    def list_incidents(self) -> list[IncidentSummary]:
        return self.splunk_adapter.list_incidents()

    def analyze_incident(self, incident_id: str) -> IncidentAnalysis:
        incidents = {incident.id: incident for incident in self.splunk_adapter.list_incidents()}
        if incident_id not in incidents:
            raise KeyError(f"Unknown incident: {incident_id}")

        events = self.splunk_adapter.fetch_incident_events(incident_id)
        return build_incident_analysis(incidents[incident_id], events)
