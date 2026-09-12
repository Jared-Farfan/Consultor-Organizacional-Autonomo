from __future__ import annotations

from typing import Any

from app import analytics
from app.models import TAXONOMY, TaxonomyEntry, TraceStep
from app.organization import propose_org_blocks
from app.report import build_report
from app.severity import classify_all
from app.simulation import simulate_change, simulate_horizon_cascade


class RestructuringAgent:
    """Research protocol. Tools produce facts before any narrative layer runs."""

    def __init__(
        self, events: list[Any], hourly_cost: float = 55.0,
        taxonomy: tuple[TaxonomyEntry, ...] = TAXONOMY,
    ):
        self.events = events
        self.hourly_cost = hourly_cost
        self.taxonomy = taxonomy
        self.trace: list[TraceStep] = []

    def _observe(self, hypothesis: str, tool: str, result: dict[str, Any], conclusion: str) -> dict[str, Any]:
        self.trace.append(TraceStep(hypothesis, tool, result, conclusion))
        return result

    def get_flow_metrics(self) -> dict[str, Any]:
        result = analytics.get_flow_metrics(self.events)
        return self._observe("Work may wait more than it is touched.", "get_flow_metrics", result,
                             "Queue and handoff metrics establish the flow baseline.")

    def get_state_queue_times(self) -> dict[str, Any]:
        result = analytics.get_state_queue_times(self.events)
        return self._observe("A state may create concentrated waiting.", "get_state_queue_times", result,
                             "State-level queues isolate approval and team bottlenecks.")

    def get_handoff_graph(self) -> dict[str, Any]:
        result = analytics.get_handoff_graph(self.events)
        return self._observe("Dependencies may reveal hidden concentration or silos.", "get_handoff_graph", result,
                             "Handoff participation exposes concentration without naming individuals.")

    def find_ticket_clusters(self) -> dict[str, Any]:
        result = {"clusters": analytics.find_ticket_clusters(self.events)}
        return self._observe("Repeated demand may be hidden by ticket-level reporting.", "find_ticket_clusters", result,
                             "Issue signatures quantify repeated operational debt.")

    def classify_business_alignment(self) -> dict[str, Any]:
        result = analytics.classify_business_alignment(self.events, self.taxonomy)
        return self._observe("Fast work can still be strategically misallocated.", "classify_business_alignment", result,
                             "The fixed taxonomy quantifies capacity consumed outside the core.")

    def investigate(self) -> dict[str, Any]:
        flow = self.get_flow_metrics()
        queues = self.get_state_queue_times()
        graph = self.get_handoff_graph()
        self.find_ticket_clusters()
        alignment = self.classify_business_alignment()
        raw_findings = analytics.detect_findings(self.events, self.hourly_cost, self.taxonomy)
        findings = classify_all(raw_findings)
        self._observe("Each confirmed issue must be proportionately classified.", "classify_change_severity",
                      {"finding_count": len(findings), "severities": [finding["severity"] for finding in findings]},
                      "The two-of-three rule separates tactical action from macro change.")
        blocks = propose_org_blocks(graph, alignment)
        self._observe("Macro findings require operating units anchored in real flow.", "propose_org_blocks", blocks,
                      "Blocks derive from observed dependencies and core categories.")
        local_scenario = simulate_change(flow, {"queue_reduction_pct": 0.15, "handoff_reduction_pct": 0.20})
        self._observe("A proposal should have a bounded operational scenario.", "simulate_change", local_scenario,
                      "Scenario changes measured queue and handoff components only.")
        horizons = simulate_horizon_cascade(flow)
        self._observe("Macro change must advance through evidence gates.", "simulate_horizon_cascade", {"horizons": horizons},
                      "Each horizon is conditional on sustained metrics from the preceding horizon.")
        report = build_report(flow, queues, graph, alignment, findings, blocks, horizons)
        return {"trace": [step.to_dict() for step in self.trace], "report": report}
