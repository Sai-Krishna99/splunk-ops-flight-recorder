from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.incident_service import IncidentService
from backend.app.models import (
    AdapterStatus,
    Evidence,
    IncidentAnalysis,
    IncidentEvent,
    IncidentSummary,
)

app = FastAPI(title="Ops Flight Recorder", version="0.1.0")
service = IncidentService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/", response_class=FileResponse)
def workspace() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": service.adapter_status().mode}


@app.get("/api/adapter/status", response_model=AdapterStatus)
def adapter_status() -> AdapterStatus:
    return service.adapter_status()


@app.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents() -> list[IncidentSummary]:
    return service.list_incidents()


@app.get("/api/incidents/{incident_id}/analysis", response_model=IncidentAnalysis)
def analyze_incident(incident_id: str) -> IncidentAnalysis:
    try:
        return service.analyze_incident(incident_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/incidents/{incident_id}/events", response_model=list[IncidentEvent])
def list_events(incident_id: str) -> list[IncidentEvent]:
    try:
        return service.list_events(incident_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/incidents/{incident_id}/evidence", response_model=list[Evidence])
def list_evidence(incident_id: str) -> list[Evidence]:
    try:
        return service.list_evidence(incident_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
