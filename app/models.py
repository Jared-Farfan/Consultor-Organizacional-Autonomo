from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    TACTICAL = "tactical"
    STRUCTURAL = "structural"
    ORGANIZATIONAL = "organizational"
    STRATEGIC = "strategic"


@dataclass(frozen=True)
class Event:
    ticket_id: str
    ts: datetime
    event_type: str
    actor_hash: str
    team: str
    from_state: str | None = None
    to_state: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ts"] = self.ts.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            ticket_id=data["ticket_id"],
            ts=datetime.fromisoformat(data["ts"]),
            event_type=data["event_type"],
            actor_hash=data["actor_hash"],
            team=data["team"],
            from_state=data.get("from_state"),
            to_state=data.get("to_state"),
            payload=data.get("payload") or {},
        )


@dataclass(frozen=True)
class TaxonomyEntry:
    key: str
    label: str
    strategic_criticality: str
    core: bool


@dataclass
class Finding:
    id: str
    title: str
    evidence: list[str]
    metrics: dict[str, float]
    structural_scope: bool
    persistent: bool
    core_impact: bool
    severity: Severity | None = None
    annual_cost: float = 0.0
    recommendation: str = ""
    horizon: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value if self.severity else None
        return data


@dataclass(frozen=True)
class TraceStep:
    hypothesis: str
    tool: str
    result: dict[str, Any]
    conclusion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TAXONOMY = (
    TaxonomyEntry("customer_retention", "Customer retention", "high", True),
    TaxonomyEntry("regulatory_compliance", "Regulatory compliance", "high", True),
    TaxonomyEntry("critical_technical_debt", "Critical technical debt", "high", True),
    TaxonomyEntry("strategic_onboarding", "Strategic customer onboarding", "high", True),
    TaxonomyEntry("reactive_support", "Reactive undifferentiated support", "low", False),
    TaxonomyEntry("operational_debt", "Operational debt", "medium", False),
    TaxonomyEntry("process_friction", "Process friction", "low", False),
)
