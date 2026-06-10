from typing import Protocol

from backend.app.demo_data import demo_events, demo_incident_summary
from backend.app.models import IncidentEvent, IncidentSummary


class SplunkAdapter(Protocol):
    def list_incidents(self) -> list[IncidentSummary]:
        ...

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        ...


class DemoSplunkAdapter:
    def list_incidents(self) -> list[IncidentSummary]:
        return [demo_incident_summary()]

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        incident = demo_incident_summary()
        if incident_id != incident.id:
            raise KeyError(f"Unknown demo incident: {incident_id}")
        return demo_events()


class RealSplunkAdapter:
    def list_incidents(self) -> list[IncidentSummary]:
        raise NotImplementedError("Real Splunk/MCP integration is planned after the demo adapter.")

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        raise NotImplementedError("Real Splunk/MCP integration is planned after the demo adapter.")
