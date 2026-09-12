from __future__ import annotations

from copy import deepcopy
from typing import Any


def _simpy_validation(flow_metrics: dict[str, float], projected_lead: float) -> dict[str, float | str]:
    """Runs a small service-queue validation when SimPy is installed."""
    try:
        import simpy
    except ImportError:
        return {"engine": "unavailable"}
    environment = simpy.Environment()
    resource = simpy.Resource(environment, capacity=1)
    waits: list[float] = []
    service_time = max(0.1, flow_metrics["avg_touch_hours"])
    interarrival = max(0.1, service_time * projected_lead / flow_metrics["avg_lead_hours"])

    def ticket(arrival: float) -> Any:
        yield environment.timeout(arrival)
        requested = environment.now
        with resource.request() as request:
            yield request
            waits.append(environment.now - requested)
            yield environment.timeout(service_time)

    for item in range(12):
        environment.process(ticket(item * interarrival))
    environment.run()
    return {"engine": "simpy_single_server_validation", "avg_simulated_wait_hours": round(sum(waits) / len(waits), 2)}


def simulate_change(flow_metrics: dict[str, float], change: dict[str, float]) -> dict[str, float | str]:
    """Uses Little's Law to compare a bounded operational change.

    The model keeps throughput constant and applies changes only to measured
    queue/handoff components. It intentionally does not predict revenue.
    """
    baseline_lead = flow_metrics["avg_lead_hours"]
    baseline_queue = flow_metrics["avg_queue_hours"]
    queue_reduction = min(max(change.get("queue_reduction_pct", 0.0), 0.0), 0.9)
    handoff_reduction = min(max(change.get("handoff_reduction_pct", 0.0), 0.0), 0.9)
    handoff_hours = baseline_queue * flow_metrics["handoffs_per_ticket"] * 0.25
    improved_queue = baseline_queue * (1 - queue_reduction)
    improved_lead = max(
        flow_metrics["avg_touch_hours"],
        baseline_lead - (baseline_queue - improved_queue) - handoff_hours * handoff_reduction,
    )
    throughput_per_hour = flow_metrics["ticket_count"] / (150 * 24)
    result: dict[str, float | str] = {
        "engine": "Little's Law bounded scenario",
        "baseline_lead_hours": round(baseline_lead, 2),
        "projected_lead_hours": round(improved_lead, 2),
        "lead_time_reduction_pct": round(100 * (baseline_lead - improved_lead) / baseline_lead, 2),
        "baseline_wip_estimate": round(throughput_per_hour * baseline_lead, 2),
        "projected_wip_estimate": round(throughput_per_hour * improved_lead, 2),
    }
    result["simpy_validation"] = _simpy_validation(flow_metrics, improved_lead)
    return result


def simulate_horizon_cascade(flow_metrics: dict[str, float]) -> list[dict[str, Any]]:
    """Chains horizons. Each later change is conditional on the prior gate."""
    horizons = [
        ("Horizon 0", "Weeks 1-4", "Remove low-risk approval friction", {"queue_reduction_pct": 0.12},
         "Approval queue and rejection rate remain below baseline for four weeks."),
        ("Horizon 1", "Months 2-4", "Train backup and reroute SPOF work", {"queue_reduction_pct": 0.08, "handoff_reduction_pct": 0.10},
         "No single actor participates in more than 25% of critical handoff endpoints."),
        ("Horizon 2", "Months 4-9", "Create onboarding value-stream unit and transition RACI", {"queue_reduction_pct": 0.15, "handoff_reduction_pct": 0.30},
         "Onboarding lead-time improvement is sustained for two monthly cohorts."),
        ("Horizon 3", "Month 9+", "Move protected capacity from reactive support to core work", {"queue_reduction_pct": 0.05, "handoff_reduction_pct": 0.10},
         "Automation has reduced reactive demand without degrading service levels."),
    ]
    current = deepcopy(flow_metrics)
    result: list[dict[str, Any]] = []
    for name, window, action, change, gate in horizons:
        scenario = simulate_change(current, change)
        result.append({"horizon": name, "window": window, "action": action, "advance_gate": gate, "scenario": scenario})
        current["avg_lead_hours"] = float(scenario["projected_lead_hours"])
        current["avg_queue_hours"] *= 1 - change.get("queue_reduction_pct", 0.0)
        current["handoffs_per_ticket"] *= 1 - change.get("handoff_reduction_pct", 0.0)
    return result
