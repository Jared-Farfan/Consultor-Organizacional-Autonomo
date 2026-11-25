from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import RestructuringAgent
from app.config import PROJECT_ROOT, settings
from app.database import load_duckdb_events, load_postgres_events, load_postgres_taxonomy
from app.ingestion import load_event_log_v2, load_taxonomy, write_observed_ticket_summary
from app.llm import answer_question
from app.storage import materialize_events

app = FastAPI(title="Autonomous Organizational Consultant", version="0.1.0")
_active_investigation: dict | None = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins), allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


class InvestigationRequest(BaseModel):
    hourly_cost: float = Field(default=55.0, gt=0)
    label: str = Field(default="", max_length=80)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)


RAW_DATA = PROJECT_ROOT / "data" / "raw"
DERIVED_DATA = PROJECT_ROOT / "data" / "derived"
STATIC_DIR = PROJECT_ROOT / "app" / "static"
app.mount("/ui", StaticFiles(directory=STATIC_DIR), name="ui")


def _dataset() -> tuple[list, tuple]:
    if settings.data_source == "postgres":
        events = load_postgres_events(settings.database_url, settings.db_connect_timeout_seconds)
        taxonomy = load_postgres_taxonomy(settings.database_url, settings.db_connect_timeout_seconds)
    elif settings.data_source == "duckdb":
        events = load_duckdb_events(settings.duckdb_path)
        taxonomy = load_taxonomy(settings.taxonomy_path)
    else:
        events = load_event_log_v2(settings.raw_event_log_path, settings.org_chart_path)
        taxonomy = load_taxonomy(settings.taxonomy_path)
    if not events or not taxonomy:
        raise RuntimeError("Configured data source returned no observable events or taxonomy")
    return events, taxonomy


def _agent(hourly_cost: float = 55.0) -> RestructuringAgent:
    events, taxonomy = _dataset()
    return RestructuringAgent(events, hourly_cost, taxonomy)


def _get_active_investigation(investigation_id: str) -> dict:
    if not _active_investigation or _active_investigation["meta"]["id"] != investigation_id:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return _active_investigation


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment, "data_source": settings.data_source}


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config/status")
def config_status() -> dict:
    return {
        "environment": settings.environment,
        "data_source": settings.data_source,
        "synthetic_data_allowed": settings.allow_synthetic_data,
        "llm_enabled": settings.llm_enabled,
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
        "db_read_only": settings.db_read_only,
        "trace_includes_payloads": settings.trace_include_payloads,
    }


@app.get("/demo/report")
def demo_report() -> dict:
    return _agent().investigate()


@app.post("/datasets/materialize")
def materialize_demo_dataset() -> dict:
    events, _ = _dataset()
    summary_count = write_observed_ticket_summary(events, DERIVED_DATA / "tickets_observed_v2.csv")
    result = materialize_events(events, DERIVED_DATA / "organizational_events_v2.duckdb")
    return {**result, "observed_tickets": summary_count}


@app.post("/investigations", status_code=201)
def create_investigation(request: InvestigationRequest) -> dict:
    global _active_investigation
    try:
        result = _agent(request.hourly_cost).investigate()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    investigation_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    result["meta"] = {
        "id": investigation_id,
        "label": request.label.strip() or f"Investigation {created_at[:16].replace('T', ' ')} UTC",
        "created_at": created_at,
        "hourly_cost": request.hourly_cost,
    }
    _active_investigation = result
    return {"id": investigation_id, "meta": result["meta"], "trace": result["trace"], "report": result["report"]}


@app.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str) -> dict:
    return _get_active_investigation(investigation_id)


@app.post("/investigations/{investigation_id}/questions")
def ask_question(investigation_id: str, request: QuestionRequest) -> dict:
    try:
        return answer_question(request.question, _get_active_investigation(investigation_id)["report"], settings)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/investigations/{investigation_id}/trace")
def stream_trace(investigation_id: str) -> StreamingResponse:
    investigation = _get_active_investigation(investigation_id)

    def events():
        import json
        for step in investigation["trace"]:
            yield f"data: {json.dumps(step)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
