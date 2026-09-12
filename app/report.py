from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_report(
    flow: dict[str, Any], queues: dict[str, Any], graph: dict[str, Any], alignment: dict[str, Any],
    findings: list[dict[str, Any]], blocks: dict[str, Any], horizons: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[str(finding["severity"])].append(finding)
    total_cost = round(sum(float(finding["annual_cost"]) for finding in findings), 2)
    return {
        "data_notice": "All data and cost estimates in this report are synthetic experimental data.",
        "executive_summary": {
            "findings": len(findings),
            "estimated_annual_cost": total_cost,
            "capacity_outside_core_pct": alignment["capacity_outside_core_pct"],
            "decision_rule": "Macro change requires at least 2 of 3: structural scope, persistence, core impact.",
        },
        "flow_metrics": flow,
        "queue_times": queues,
        "handoff_graph": graph,
        "effort_value_matrix": alignment,
        "recommendations_by_severity": dict(grouped),
        "organization_blocks": blocks,
        "horizon_cascade": horizons,
    }
