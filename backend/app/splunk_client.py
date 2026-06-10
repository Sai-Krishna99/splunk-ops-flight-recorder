import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from backend.app.demo_data import demo_events, demo_incident_summary
from backend.app.models import AdapterStatus, Evidence, IncidentEvent, IncidentSummary


@dataclass(frozen=True)
class SplunkConfig:
    base_url: str
    index: str
    username: str | None
    password: str | None
    token: str | None
    verify_ssl: bool

    @classmethod
    def from_env(cls) -> "SplunkConfig":
        return cls(
            base_url=os.getenv("SPLUNK_BASE_URL", "https://127.0.0.1:8089").rstrip("/"),
            index=os.getenv("SPLUNK_INDEX", "ops_demo"),
            username=os.getenv("SPLUNK_USERNAME"),
            password=os.getenv("SPLUNK_PASSWORD"),
            token=os.getenv("SPLUNK_TOKEN"),
            verify_ssl=os.getenv("SPLUNK_VERIFY_SSL", "false").lower()
            in {"1", "true", "yes"},
        )

    @property
    def has_auth(self) -> bool:
        return bool(self.token or (self.username and self.password))


class SplunkAdapter(Protocol):
    def list_incidents(self) -> list[IncidentSummary]:
        ...

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        ...

    def status(self) -> AdapterStatus:
        ...


class DemoSplunkAdapter:
    def list_incidents(self) -> list[IncidentSummary]:
        return [demo_incident_summary()]

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        incident = demo_incident_summary()
        if incident_id != incident.id:
            raise KeyError(f"Unknown demo incident: {incident_id}")
        return demo_events()

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            mode="demo",
            source="splunk_demo",
            description="Using deterministic local events shaped like Splunk search results.",
            next_steps=[
                "Replay the synthetic checkout incident.",
                "Inspect generated SPL-shaped evidence.",
                "Switch to real Splunk search when credentials are configured.",
            ],
        )


class RealSplunkAdapter:
    def __init__(
        self,
        config: SplunkConfig | None = None,
        client: "SplunkRestClient | None" = None,
    ) -> None:
        self.config = config or SplunkConfig.from_env()
        self.client = client or SplunkRestClient(self.config)

    def list_incidents(self) -> list[IncidentSummary]:
        rows = self.client.export_search(
            (
                f"search index={self.config.index} source=ops-flight-recorder "
                "incident_id=* | spath "
                "| stats min(time) as started_at max(time) as ended_at "
                "values(service) as services values(severity) as severities "
                "by incident_id "
                "| sort - started_at"
            )
        )
        return [row_to_incident_summary(row) for row in rows]

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        rows = self.client.export_search(
            (
                f"search index={self.config.index} source=ops-flight-recorder "
                f'incident_id="{incident_id}" | spath | sort 0 time'
            )
        )
        if not rows:
            raise KeyError(f"Unknown Splunk incident: {incident_id}")
        return [row_to_incident_event(row, self.config.index) for row in rows]

    def status(self) -> AdapterStatus:
        if not self.config.has_auth:
            description = (
                "Real Splunk adapter selected, but SPLUNK_TOKEN or "
                "SPLUNK_USERNAME/SPLUNK_PASSWORD is not configured."
            )
        else:
            description = (
                f"Real Splunk adapter configured for {self.config.base_url} "
                f"and index={self.config.index}."
            )
        return AdapterStatus(
            mode="real",
            source="splunk_search",
            description=description,
            next_steps=[
                "Splunk REST searches are powering incident evidence.",
                "Search rows are normalized into timeline and evidence records.",
                "The MCP adapter can replace REST search with the same event contract.",
            ],
        )


class SplunkMcpAdapter:
    def list_incidents(self) -> list[IncidentSummary]:
        raise NotImplementedError(
            "Splunk MCP adapter requires a callable Splunk MCP Server tool."
        )

    def fetch_incident_events(self, incident_id: str) -> list[IncidentEvent]:
        raise NotImplementedError(
            "Splunk MCP adapter requires a callable Splunk MCP Server tool."
        )

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            mode="real",
            source="splunk_mcp",
            description=(
                "Splunk MCP adapter slot is defined, but no callable Splunk MCP "
                "Server tool is available in this runtime."
            ),
            next_steps=[
                "Install or expose the Splunk MCP Server tool to the app runtime.",
                "Execute the documented incident searches through MCP.",
                "Return rows through the same IncidentEvent and Evidence contract.",
            ],
        )


def build_splunk_adapter() -> SplunkAdapter:
    mode = os.getenv("OPS_FLIGHT_RECORDER_ADAPTER", "demo").lower()
    if mode == "real":
        return RealSplunkAdapter()
    if mode == "mcp":
        return SplunkMcpAdapter()
    return DemoSplunkAdapter()


class SplunkRestClient:
    def __init__(self, config: SplunkConfig) -> None:
        self.config = config

    def export_search(self, search: str) -> list[dict[str, str]]:
        body = urllib.parse.urlencode(
            {
                "search": search,
                "output_mode": "json",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/services/search/jobs/export",
            data=body,
            method="POST",
        )
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        for name, value in self.auth_headers().items():
            request.add_header(name, value)

        try:
            with urllib.request.urlopen(
                request,
                context=self.ssl_context(),
                timeout=20,
            ) as response:
                return parse_export_rows(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Splunk search failed: HTTP {exc.code} {message}") from exc

    def auth_headers(self) -> dict[str, str]:
        if self.config.token:
            return {"Authorization": f"Bearer {self.config.token}"}
        if self.config.username and self.config.password:
            auth = f"{self.config.username}:{self.config.password}".encode("utf-8")
            import base64

            return {"Authorization": f"Basic {base64.b64encode(auth).decode('ascii')}"}
        return {}

    def ssl_context(self) -> ssl.SSLContext:
        if self.config.verify_ssl:
            return ssl.create_default_context()
        return ssl._create_unverified_context()


def parse_export_rows(payload: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if "result" in item:
            rows.append(item["result"])
    return rows


def row_to_incident_summary(row: dict[str, str]) -> IncidentSummary:
    incident_id = first_value(row.get("incident_id")) or "unknown-incident"
    services = split_multivalue(row.get("services"))
    severity = highest_severity(split_multivalue(row.get("severities")))
    service = choose_primary_service(services)
    started_at = parse_splunk_time(row.get("started_at"))
    ended_at = parse_splunk_time(row.get("ended_at"))
    return IncidentSummary(
        id=incident_id,
        title=build_incident_title(service),
        service=service,
        severity=severity,
        status="investigating",
        started_at=started_at,
        ended_at=ended_at,
        confidence=0.72,
    )


def row_to_incident_event(row: dict[str, str], default_index: str) -> IncidentEvent:
    timestamp = parse_splunk_time(
        row.get("time") or row.get("event_epoch") or row.get("_time")
    )
    event_id = first_value(row.get("event_id")) or f"evt-{int(timestamp.timestamp())}"
    evidence_id = first_value(row.get("evidence_id")) or f"ev-{event_id}"
    service = first_value(row.get("service")) or "unknown-service"
    event_type = first_value(row.get("event_type")) or "log_anomaly"
    severity = first_value(row.get("severity")) or "warning"
    title = first_value(row.get("title")) or f"{service} {event_type}"
    query = first_value(row.get("query")) or build_row_query(row, default_index)

    evidence = Evidence(
        id=evidence_id,
        title=title,
        source="splunk_search",
        query=query,
        index=first_value(row.get("index")) or default_index,
        sourcetype=first_value(row.get("sourcetype")) or "splunk_event",
        timestamp=timestamp,
        fields=extract_evidence_fields(row),
    )
    return IncidentEvent(
        id=event_id,
        timestamp=timestamp,
        service=service,
        event_type=event_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        title=title,
        description=first_value(row.get("description")) or title,
        region=first_value(row.get("region")),
        evidence=evidence,
    )


def extract_evidence_fields(row: dict[str, str]) -> dict[str, str | int | float]:
    excluded = {
        "_raw",
        "_time",
        "time",
        "date_hour",
        "date_mday",
        "date_minute",
        "date_month",
        "date_second",
        "date_wday",
        "date_year",
        "event_id",
        "evidence_id",
        "event_type",
        "event_epoch",
        "host",
        "index",
        "incident_id",
        "linecount",
        "punct",
        "query",
        "source",
        "sourcetype",
        "splunk_server",
        "service",
        "severity",
        "title",
        "description",
        "region",
    }
    return {
        key: coerce_value(first_value(value) or "")
        for key, value in row.items()
        if key not in excluded and first_value(value) not in {None, ""}
    }


def build_row_query(row: dict[str, str], default_index: str) -> str:
    incident_id = first_value(row.get("incident_id"))
    event_id = first_value(row.get("event_id"))
    if incident_id and event_id:
        return f'index={default_index} incident_id="{incident_id}" event_id="{event_id}"'
    return f"index={default_index} source=ops-flight-recorder"


def parse_splunk_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    item = first_value(value) or value
    try:
        return datetime.fromtimestamp(float(item), tz=timezone.utc)
    except ValueError:
        pass
    normalized = item.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def split_multivalue(value: str | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    item = first_value(value)
    if not item:
        return []
    if isinstance(item, str) and "\n" in item:
        return [part.strip() for part in item.splitlines() if part.strip()]
    return [part.strip() for part in str(item).split(",") if part.strip()]


def first_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def highest_severity(values: list[str]) -> str:
    ranking = ["SEV-1", "SEV-2", "SEV-3", "critical", "warning", "info"]
    lower_values = {value.lower(): value for value in values}
    for item in ranking:
        if item.lower() in lower_values:
            return lower_values[item.lower()]
    return values[0] if values else "SEV-2"


def choose_primary_service(services: list[str]) -> str:
    if "checkout-service" in services:
        return "checkout-service"
    for service in services:
        if service not in {"auth-service"}:
            return service
    return services[0] if services else "unknown-service"


def build_incident_title(service: str) -> str:
    if service == "checkout-service":
        return "Checkout degradation after payment-service deploy"
    return f"{service} incident reconstructed from Splunk"


def coerce_value(value: str) -> str | int | float:
    try:
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value
