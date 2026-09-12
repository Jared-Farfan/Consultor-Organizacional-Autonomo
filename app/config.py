from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else PROJECT_ROOT / value


@dataclass(frozen=True)
class Settings:
    environment: str
    api_host: str
    api_port: int
    cors_origins: tuple[str, ...]
    data_source: str
    allow_synthetic_data: bool
    raw_event_log_path: Path
    taxonomy_path: Path
    org_chart_path: Path
    policy_path: Path
    duckdb_path: Path
    database_url: str
    db_read_only: bool
    db_connect_timeout_seconds: int
    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: int
    llm_max_tokens: int
    llm_temperature: float
    llm_structured_outputs: bool
    policy_require_evidence: bool
    policy_allow_macro_change: bool
    trace_include_payloads: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        if load_dotenv:
            load_dotenv(PROJECT_ROOT / ".env", override=False)
        data_source = os.getenv("DATA_SOURCE", "jsonl").strip().lower()
        if data_source not in {"jsonl", "duckdb", "postgres"}:
            raise ValueError("DATA_SOURCE must be jsonl, duckdb or postgres")
        return cls(
            environment=os.getenv("APP_ENV", "development"),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8000")),
            cors_origins=tuple(item.strip() for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()),
            data_source=data_source,
            allow_synthetic_data=_bool("ALLOW_SYNTHETIC_DATA", False),
            raw_event_log_path=_path("RAW_EVENT_LOG_PATH", "data/raw/event_log_v2.jsonl"),
            taxonomy_path=_path("TAXONOMY_PATH", "data/raw/business_taxonomy_v2.json"),
            org_chart_path=_path("ORG_CHART_PATH", "data/raw/org_chart_declared_v2.json"),
            policy_path=_path("POLICY_PATH", "config/policies.json"),
            duckdb_path=_path("DUCKDB_PATH", "data/derived/organizational_events_v2.duckdb"),
            database_url=os.getenv("DATABASE_URL", ""),
            db_read_only=_bool("DB_READ_ONLY", True),
            db_connect_timeout_seconds=int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
            llm_enabled=_bool("LLM_ENABLED", False),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1200")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            llm_structured_outputs=_bool("LLM_STRUCTURED_OUTPUTS", True),
            policy_require_evidence=_bool("POLICY_REQUIRE_EVIDENCE", True),
            policy_allow_macro_change=_bool("POLICY_ALLOW_MACRO_CHANGE", True),
            trace_include_payloads=_bool("TRACE_INCLUDE_PAYLOADS", False),
        )


settings = Settings.from_environment()
