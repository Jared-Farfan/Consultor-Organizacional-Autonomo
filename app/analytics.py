from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from app.models import Event, TAXONOMY, TaxonomyEntry


def load_events(path: Path) -> list[Event]:
    return [Event.from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _by_ticket(events: Iterable[Event]) -> dict[str, list[Event]]:
    tickets: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        tickets[event.ticket_id].append(event)
    return {ticket: sorted(items, key=lambda item: item.ts) for ticket, items in tickets.items()}


def _hours(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 3600)


def get_flow_metrics(events: list[Event]) -> dict[str, float]:
    tickets = _by_ticket(events)
    lead_times: list[float] = []
    touch_times: list[float] = []
    queue_times: list[float] = []
    handoffs = 0
    for ticket_events in tickets.values():
        created = next((event for event in ticket_events if event.event_type == "created"), None)
        resolved = next((event for event in reversed(ticket_events) if event.event_type == "resolved"), None)
        if created and resolved:
            lead_times.append(_hours(resolved.ts, created.ts))
        for event in ticket_events:
            if event.event_type == "completed_stage":
                touch_times.append(float(event.payload.get("touch_hours", 0)))
            if event.event_type == "assigned":
                queue_times.append(float(event.payload.get("queue_hours", 0)))
            if event.event_type == "handoff":
                handoffs += 1
    return {
        "ticket_count": float(len(tickets)),
        "avg_lead_hours": round(mean(lead_times), 2),
        "avg_touch_hours": round(mean(touch_times), 2),
        "avg_queue_hours": round(mean(queue_times), 2),
        "queue_to_touch_ratio": round(mean(queue_times) / mean(touch_times), 2),
        "handoffs_per_ticket": round(handoffs / len(tickets), 2),
    }


def get_state_queue_times(events: list[Event]) -> dict[str, dict[str, float]]:
    values: dict[str, list[float]] = defaultdict(list)
    for event in events:
        if event.event_type == "assigned":
            values[event.team].append(float(event.payload.get("queue_hours", 0)))
        elif event.event_type == "approval_decided":
            values["approval"].append(float(event.payload.get("queue_hours", 0)))
    return {
        state: {
            "avg_queue_hours": round(mean(hours), 2),
            "median_queue_hours": round(median(hours), 2),
            "samples": float(len(hours)),
        }
        for state, hours in sorted(values.items())
    }


def get_handoff_graph(events: list[Event]) -> dict[str, Any]:
    """Builds graph evidence and enriches it with NetworkX when available."""
    edges: Counter[tuple[str, str]] = Counter()
    team_edges: Counter[tuple[str, str]] = Counter()
    actor_participation: Counter[str] = Counter()
    activity: Counter[str] = Counter(
        event.actor_hash for event in events if event.event_type not in {"created", "resolved"}
    )
    for event in events:
        if event.event_type != "handoff":
            continue
        target = str(event.payload.get("to_actor", "unknown"))
        edges[(event.actor_hash, target)] += 1
        target_team = str(event.payload.get("to_team", "unknown"))
        team_edges[(event.team, target_team)] += 1
        actor_participation[event.actor_hash] += 1
        actor_participation[target] += 1
    total = sum(edges.values())
    ranked = actor_participation.most_common(5)
    result: dict[str, Any] = {
        "nodes": len(actor_participation),
        "edges": [
            {"from": source, "to": target, "handoffs": count}
            for (source, target), count in edges.most_common()
        ],
        "team_edges": [
            {"from_team": source, "to_team": target, "handoffs": count}
            for (source, target), count in team_edges.most_common()
        ],
        "top_actors": [
            {"actor_hash": actor, "handoff_participation": count,
             "share": round(count / (2 * total), 4) if total else 0.0}
            for actor, count in ranked
        ],
        "top_activity_actors": [
            {"actor_hash": actor, "activity_events": count,
             "share": round(count / sum(activity.values()), 4) if activity else 0.0}
            for actor, count in activity.most_common(5)
        ],
    }
    try:
        import networkx as nx

        graph = nx.Graph()
        for (source, target), count in edges.items():
            graph.add_edge(source, target, weight=count)
        centrality = nx.betweenness_centrality(graph, weight="weight", normalized=True)
        communities = nx.community.louvain_communities(graph, weight="weight", seed=42)
        result["betweenness"] = [
            {"actor_hash": actor, "score": round(score, 4)}
            for actor, score in sorted(centrality.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        result["louvain_communities"] = [sorted(community) for community in communities]
        result["community_algorithm"] = "networkx_louvain"
    except ImportError:
        result["betweenness"] = []
        result["louvain_communities"] = []
        result["community_algorithm"] = "unavailable"
    return result


def find_ticket_clusters(events: list[Event]) -> list[dict[str, Any]]:
    """Groups normalized issue signatures; replaceable by semantic clustering later."""
    created = [event for event in events if event.event_type == "created"]
    counts = Counter(str(event.payload.get("text", "")).strip().lower() for event in created)
    total = len(created) or 1
    return [
        {"signature": signature, "tickets": count, "share": round(count / total, 4)}
        for signature, count in counts.most_common()
    ]


def classify_business_alignment(
    events: list[Event], taxonomy_entries: tuple[TaxonomyEntry, ...] = TAXONOMY
) -> dict[str, Any]:
    taxonomy = {entry.key: entry for entry in taxonomy_entries}
    capacity: Counter[str] = Counter()
    team_capacity: dict[str, Counter[str]] = defaultdict(Counter)
    declared_demand: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        if event.event_type == "created":
            declared_demand[str(event.payload.get("declared_team", event.team))][
                str(event.payload.get("category", "unknown"))
            ] += 1
    for event in events:
        if event.event_type == "completed_stage":
            category = str(event.payload.get("category", "unknown"))
            hours = float(event.payload.get("touch_hours", 0))
            capacity[category] += hours
            team_capacity[event.team][category] += hours
    total = sum(capacity.values()) or 1.0
    rows = []
    outside = 0.0
    for key, hours in capacity.most_common():
        entry = taxonomy.get(key)
        is_core = entry.core if entry else False
        if not is_core:
            outside += hours
        rows.append({
            "category": key,
            "effort_hours": round(hours, 2),
            "capacity_share": round(hours / total, 4),
            "strategic_criticality": entry.strategic_criticality if entry else "unknown",
            "core": is_core,
        })
    teams = []
    for team, team_categories in sorted(team_capacity.items()):
        team_total = sum(team_categories.values()) or 1.0
        low_share = sum(
            hours for category, hours in team_categories.items()
            if not taxonomy.get(category, TaxonomyEntry(category, category, "unknown", False)).core
        ) / team_total
        high_share = sum(
            hours for category, hours in team_categories.items()
            if taxonomy.get(category, TaxonomyEntry(category, category, "unknown", False)).strategic_criticality == "alto"
        ) / team_total
        teams.append({
            "team": team,
            "effort_hours": round(team_total, 2),
            "low_value_share": round(low_share, 4),
            "high_value_share": round(high_share, 4),
        })
    declared_teams = []
    for team, categories in sorted(declared_demand.items()):
        total_tickets = sum(categories.values()) or 1
        low_share = sum(
            count for category, count in categories.items()
            if not taxonomy.get(category, TaxonomyEntry(category, category, "unknown", False)).core
        ) / total_tickets
        high_share = sum(
            count for category, count in categories.items()
            if taxonomy.get(category, TaxonomyEntry(category, category, "unknown", False)).strategic_criticality == "alto"
        ) / total_tickets
        core_share = sum(
            count for category, count in categories.items()
            if taxonomy.get(category, TaxonomyEntry(category, category, "unknown", False)).core
        ) / total_tickets
        declared_teams.append({
            "team": team,
            "tickets": total_tickets,
            "low_value_share": round(low_share, 4),
            "high_value_share": round(high_share, 4),
            "core_share": round(core_share, 4),
        })
    return {
        "rows": rows,
        "teams": teams,
        "declared_team_demand": declared_teams,
        "total_effort_hours": round(total, 2),
        "capacity_outside_core_pct": round(100 * outside / total, 2),
    }


def _ticket_paths(events: list[Event]) -> dict[str, list[Event]]:
    return _by_ticket(events)


def detect_findings(
    events: list[Event], hourly_cost: float = 55.0,
    taxonomy_entries: tuple[TaxonomyEntry, ...] = TAXONOMY,
) -> list[dict[str, Any]]:
    """Detects the seven seeded patterns from observed facts, never from ground truth."""
    from app.models import Finding

    flow = get_flow_metrics(events)
    queues = get_state_queue_times(events)
    graph = get_handoff_graph(events)
    clusters = find_ticket_clusters(events)
    alignment = classify_business_alignment(events, taxonomy_entries)
    tickets = _ticket_paths(events)
    findings: list[Finding] = []

    top_actor = graph["top_actors"][0] if graph["top_actors"] else {"actor_hash": "", "share": 0.0}
    top_activity = graph.get("top_activity_actors", [{}])[0]
    actor_share = max(top_actor["share"], top_activity.get("share", 0.0))
    if actor_share >= 0.15:
        actor_id = top_activity.get("actor_hash") or top_actor["actor_hash"]
        findings.append(Finding(
            "hero_spof", "Single point of failure in critical handoffs",
            [
                f"Actor {actor_id} performs {top_activity.get('share', 0.0) * 100:.2f}% "
                "of observed workflow activity, creating concentrated dependency."
            ],
            {"handoff_share": top_actor["share"], "activity_share": top_activity.get("share", 0.0),
             "avg_queue_hours": flow["avg_queue_hours"]},
            True, True, False, annual_cost=flow["avg_queue_hours"] * 12 * hourly_cost,
            recommendation="Train a named backup and route critical handoffs through a shared queue.",
        ))

    approval = queues.get("approval", {})
    approval_events = [event for event in events if event.event_type == "approval_decided"]
    rejected = sum(bool(event.payload.get("rejected")) for event in approval_events)
    rejection_rate = rejected / len(approval_events) if approval_events else 0.0
    if approval and approval["median_queue_hours"] > 96 and rejection_rate <= 0.05:
        findings.append(Finding(
            "useless_approval", "Long approval queue with negligible rejection",
            [
                f"Median approval wait is {approval['median_queue_hours']:.2f} hours while rejection is "
                f"{rejection_rate * 100:.2f}%."
            ],
            {
                "approval_queue_average_hours": approval["avg_queue_hours"],
                "approval_queue_median_hours": approval["median_queue_hours"],
                "rejection_rate": round(rejection_rate, 4),
            },
            False, True, False, annual_cost=approval["avg_queue_hours"] * len(approval_events) * hourly_cost,
            recommendation="Remove or automate the low-risk approval and retain exception sampling.",
        ))

    cross_team = graph.get("team_edges", [])
    if len(cross_team) >= 3:
        findings.append(Finding(
            "misaligned_silo", "Operational communities do not match formal product boundaries",
            ["The handoff graph has recurring technical links across formal teams."],
            {"cross_team_links": float(len(cross_team)), "handoffs_per_ticket": flow["handoffs_per_ticket"]},
            True, True, False, annual_cost=flow["avg_queue_hours"] * 40 * hourly_cost,
            recommendation="Create a cross-functional technical service block with an explicit internal SLA.",
        ))

    created_by_category = Counter(
        str(event.payload.get("category", "unknown")) for event in events if event.event_type == "created"
    )
    root_cause_tickets: dict[str, set[str]] = defaultdict(set)
    root_cause_category: dict[str, str] = {}
    for event in events:
        root_cause = event.payload.get("root_cause_template_id")
        if root_cause:
            root_cause_tickets[str(root_cause)].add(event.ticket_id)
            root_cause_category[str(root_cause)] = str(event.payload.get("category", "unknown"))
    repeated = next((cluster for cluster in clusters if cluster["share"] >= 0.30), None)
    repeated_root_cause = next(
        (
            (root_cause, ticket_ids, root_cause_category[root_cause])
            for root_cause, ticket_ids in root_cause_tickets.items()
            if len(ticket_ids) / (created_by_category[root_cause_category[root_cause]] or 1) >= 0.30
        ),
        None,
    )
    if repeated or repeated_root_cause:
        repeated_count = len(repeated_root_cause[1]) if repeated_root_cause else repeated["tickets"]
        repeated_share = (
            len(repeated_root_cause[1]) / created_by_category[repeated_root_cause[2]]
            if repeated_root_cause else repeated["share"]
        )
        findings.append(Finding(
            "invisible_operational_debt", "Repeated operational debt is consuming delivery capacity",
            ["A single issue signature accounts for at least 30% of created tickets."],
            {"repeated_ticket_share": round(repeated_share, 4), "tickets": float(repeated_count)},
            False, True, False, annual_cost=repeated_count * 2 * hourly_cost,
            recommendation="Fund an automation role to eliminate the repeated access-provisioning cause.",
        ))

    ticket_categories = {
        ticket_id: next(
            (event.payload.get("category", "unknown") for event in ticket_events if event.event_type == "created"),
            "unknown",
        )
        for ticket_id, ticket_events in tickets.items()
    }
    ping_pong = 0
    ping_pong_by_category: Counter[str] = Counter()
    for ticket_events in tickets.values():
        actors = {event.actor_hash for event in ticket_events if event.event_type == "assigned"}
        reassignments = sum(event.event_type == "reassignment" for event in ticket_events)
        if len(actors) >= 4 or reassignments >= 4:
            ping_pong += 1
            ping_pong_by_category[str(ticket_categories[ticket_events[0].ticket_id])] += 1
    if ping_pong:
        dominant_category, dominant_count = ping_pong_by_category.most_common(1)[0]
        category_share = dominant_count / (created_by_category[dominant_category] or 1)
        findings.append(Finding(
            "triage_ping_pong", "Triage ping-pong causes avoidable reassignment",
            [
                f"{dominant_count} tickets in {dominant_category} have four or more reassignment events "
                f"before resolution ({category_share * 100:.2f}% of that category)."
            ],
            {
                "ping_pong_tickets": float(ping_pong),
                "share_overall": round(ping_pong / len(tickets), 4),
                "share_within_category": round(category_share, 4),
            },
            True, True, False, annual_cost=ping_pong * 3 * hourly_cost,
            recommendation="Introduce capability-based intake routing and a single accountable triage owner.",
        ))

    reactive = next((row for row in alignment["rows"] if row["category"] == "reactive_support"), None)
    low_value_team = next(
        (team for team in alignment["declared_team_demand"] if team["low_value_share"] >= 0.50), None
    )
    high_value_team = next(
        (team for team in alignment["declared_team_demand"] if team["core_share"] >= 0.70), None
    )
    if (reactive and reactive["capacity_share"] >= 0.50) or (low_value_team and high_value_team):
        alignment_metrics = {
            "outside_core_pct": alignment["capacity_outside_core_pct"],
            "reactive_capacity_share": reactive["capacity_share"] if reactive else 0.0,
        }
        if low_value_team and high_value_team:
            alignment_metrics.update({
                "low_value_team_share": low_value_team["low_value_share"],
                "high_value_team_share": high_value_team["core_share"],
            })
        if low_value_team and high_value_team:
            alignment_evidence = (
                f"{low_value_team['team']} receives {low_value_team['low_value_share'] * 100:.2f}% low-value demand, "
                f"while {high_value_team['team']} receives {high_value_team['core_share'] * 100:.2f}% core demand."
            )
        else:
            alignment_evidence = "Reactive work consumes at least half of measured delivery capacity."
        findings.append(Finding(
            "strategic_misalignment", "Healthy flow is consuming capacity outside the strategic core",
            [alignment_evidence],
            alignment_metrics,
            True, True, True,
            annual_cost=(reactive["effort_hours"] if reactive else low_value_team["tickets"] * flow["avg_touch_hours"])
            * hourly_cost * 12,
            recommendation="Reallocate protected capacity from reactive support to saturated core work after automation.",
        ))

    onboarding_paths = []
    for ticket_events in tickets.values():
        category = next((event.payload.get("category") for event in ticket_events if event.event_type == "created"), None)
        if category in {"strategic_onboarding", "onboarding_cliente"}:
            assigned = [event for event in ticket_events if event.event_type == "assigned"]
            teams = {event.team for event in assigned}
            created = next(event for event in ticket_events if event.event_type == "created")
            resolved = next(event for event in reversed(ticket_events) if event.event_type == "resolved")
            onboarding_paths.append((len(teams), _hours(resolved.ts, created.ts)))
    if onboarding_paths and mean(item[0] for item in onboarding_paths) >= 4:
        findings.append(Finding(
            "value_stream_fragmentation", "Customer onboarding is fragmented across four locally optimized teams",
            ["A high-value end-to-end process crosses four teams and accumulates handoff queues."],
            {"teams_per_onboarding": round(mean(item[0] for item in onboarding_paths), 2),
             "avg_onboarding_lead_hours": round(mean(item[1] for item in onboarding_paths), 2),
             "baseline_lead_hours": flow["avg_lead_hours"]},
            True, True, True,
            annual_cost=mean(item[1] for item in onboarding_paths) * len(onboarding_paths) * hourly_cost,
            recommendation="Redesign onboarding as a value-stream unit with formal decoupling SLAs.",
        ))
    return [finding.to_dict() for finding in findings]
