from __future__ import annotations

import hashlib
import json
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import Event, TaxonomyEntry


def anonymize_actor(value: str | None) -> str:
    """Produces a stable non-reversible identifier for imported actor fields."""
    normalized = (value or "unknown").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_jira_ticket(ticket: dict[str, Any]) -> list[Event]:
    """Adapts a minimal Jira-like record to the portable canonical event log.

    Raw display names and emails never survive the adapter: only actor hashes
    are emitted. Other connectors should target the same Event contract.
    """
    fields = ticket.get("fields") or {}
    ticket_id = str(ticket.get("key") or ticket.get("id"))
    if not ticket_id or ticket_id == "None":
        raise ValueError("Ticket requires key or id")
    created_at = _timestamp(fields["created"])
    category = fields.get("business_category", "unknown")
    effort_type = fields.get("effort_type", "unknown")
    summary = str(fields.get("summary", ""))
    team = str(fields.get("team", "Unassigned"))
    actor = anonymize_actor((fields.get("reporter") or {}).get("emailAddress") or fields.get("reporter"))
    events = [Event(ticket_id, created_at, "created", actor, team, payload={
        "category": category, "effort_type": effort_type, "text": summary,
    })]
    previous_state = None
    for history in sorted(ticket.get("changelog", []), key=lambda item: item["created"]):
        event_time = _timestamp(history["created"])
        author = anonymize_actor((history.get("author") or {}).get("emailAddress") or history.get("author"))
        for item in history.get("items", []):
            if item.get("field") == "status":
                events.append(Event(ticket_id, event_time, "state_changed", author, team,
                                    previous_state or item.get("fromString"), item.get("toString"),
                                    {"category": category, "effort_type": effort_type, "text": summary}))
                previous_state = item.get("toString")
            elif item.get("field") == "assignee":
                events.append(Event(ticket_id, event_time, "assigned", author, team, payload={
                    "category": category, "effort_type": effort_type, "text": summary,
                    "assignee_hash": anonymize_actor(item.get("toString")),
                }))
    return events


def load_taxonomy(path: Path) -> tuple[TaxonomyEntry, ...]:
    """Loads the external strategic taxonomy; low-value categories are non-core."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        TaxonomyEntry(
            key=key,
            label=value["label"],
            strategic_criticality=value["strategic_value"],
            core=value["strategic_value"] != "bajo",
        )
        for key, value in data.items()
    )


def load_org_chart(path: Path) -> dict[str, Any]:
    """Loads declared reporting structure used only for observed-flow comparison."""
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_ticket_context(raw_events: list[dict[str, Any]]) -> dict[str, Any]:
    created = next(item for item in raw_events if item["event_type"] == "created")
    return dict(created.get("payload") or {})


def load_event_log_v2(event_log_path: Path, org_chart_path: Path) -> list[Event]:
    """Normalizes the V2 JSONL event log into the project's canonical Event model.

    The raw source remains intact. Derived events make dwell time and handoffs
    explicit so downstream metrics never need the private evaluation labels.
    """
    raw_events = [json.loads(line) for line in event_log_path.read_text(encoding="utf-8").splitlines() if line]
    org_chart = load_org_chart(org_chart_path)
    actor_team = {member["actor_id_hash"]: member["declared_team"] for member in org_chart["members"]}
    tickets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in raw_events:
        tickets[item["ticket_id"]].append(item)

    normalized: list[Event] = []
    for ticket_id, ticket_events in tickets.items():
        ticket_events.sort(key=lambda item: item["ts"])
        context = _merge_ticket_context(ticket_events)
        last_handoff: dict[str, Any] | None = None
        stage_started: datetime | None = None
        initial_assigned = False
        for index, item in enumerate(ticket_events):
            payload = {**context, **(item.get("payload") or {})}
            payload["text"] = payload.get("title", "")
            timestamp = _timestamp(item["ts"])
            actor = item["actor_hash"]
            team = str(
                payload.get("leg_team")
                or payload.get("leaving_team")
                or actor_team.get(actor)
                or context.get("declared_team", "unassigned")
            )
            raw_type = item["event_type"]
            from_state = item.get("from_state")
            to_state = item.get("to_state")

            if raw_type == "created":
                normalized.append(Event(ticket_id, timestamp, "created", actor, team, from_state, to_state, payload))
                continue

            if raw_type == "reassignment":
                normalized.append(Event(ticket_id, timestamp, "reassignment", actor, team, from_state, to_state, payload))
                continue

            if to_state == "Pending Approval Security":
                last_handoff = None
                normalized.append(Event(ticket_id, timestamp, "approval_requested", actor, team, from_state, to_state, payload))
                continue

            if from_state == "Pending Approval Security":
                approval_start = next(
                    event.ts for event in reversed(normalized)
                    if event.ticket_id == ticket_id and event.event_type == "approval_requested"
                )
                payload["queue_hours"] = (timestamp - approval_start).total_seconds() / 3600
                payload["rejected"] = payload.get("approval_result") == "rejected"
                normalized.append(Event(ticket_id, timestamp, "approval_decided", actor, team, from_state, to_state, payload))
                stage_started = timestamp
                continue

            if to_state == "Waiting Handoff":
                if stage_started:
                    completed = dict(payload)
                    completed["touch_hours"] = max(0.0, (timestamp - stage_started).total_seconds() / 3600)
                    normalized.append(Event(ticket_id, timestamp, "completed_stage", actor, team, from_state, to_state, completed))
                next_team = str(payload["next_team"])
                next_actor = next(
                    (
                        candidate["actor_hash"]
                        for candidate in ticket_events[index + 1:]
                        if (candidate.get("payload") or {}).get("leg_team") == next_team
                    ),
                    actor,
                )
                payload["to_team"] = next_team
                payload["to_actor"] = next_actor
                normalized.append(Event(ticket_id, timestamp, "handoff", actor, team, from_state, to_state, payload))
                last_handoff = {"ts": timestamp, "next_team": next_team}
                stage_started = None
                continue

            if from_state == "Waiting Handoff" and to_state == "In Progress":
                if last_handoff:
                    assigned = dict(payload)
                    assigned["queue_hours"] = max(0.0, (timestamp - last_handoff["ts"]).total_seconds() / 3600)
                    normalized.append(Event(ticket_id, timestamp, "assigned", actor, last_handoff["next_team"], from_state, to_state, assigned))
                stage_started = timestamp
                last_handoff = None
                continue

            if to_state == "In Progress":
                if not initial_assigned:
                    created = next(event for event in normalized if event.ticket_id == ticket_id and event.event_type == "created")
                    assigned = dict(payload)
                    assigned["queue_hours"] = max(0.0, (timestamp - created.ts).total_seconds() / 3600)
                    normalized.append(Event(ticket_id, timestamp, "assigned", actor, team, from_state, to_state, assigned))
                    initial_assigned = True
                stage_started = timestamp
                continue

            if to_state in {"In Review", "Done"}:
                if stage_started:
                    completed = dict(payload)
                    completed["touch_hours"] = max(0.0, (timestamp - stage_started).total_seconds() / 3600)
                    normalized.append(Event(ticket_id, timestamp, "completed_stage", actor, team, from_state, to_state, completed))
                stage_started = None
                if to_state == "Done":
                    normalized.append(Event(ticket_id, timestamp, "resolved", actor, team, from_state, to_state, payload))
                continue

            normalized.append(Event(ticket_id, timestamp, "state_transition", actor, team, from_state, to_state, payload))
    return sorted(normalized, key=lambda event: (event.ticket_id, event.ts, event.event_type))


def write_observed_ticket_summary(events: list[Event], output_path: Path) -> int:
    """Writes only observable ticket facts; evaluation labels are intentionally excluded."""
    tickets: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        tickets[event.ticket_id].append(event)
    rows = []
    for ticket_id, ticket_events in sorted(tickets.items()):
        ticket_events.sort(key=lambda event: event.ts)
        created = next(event for event in ticket_events if event.event_type == "created")
        resolved = next(event for event in reversed(ticket_events) if event.event_type == "resolved")
        rows.append({
            "ticket_id": ticket_id,
            "category": created.payload.get("category"),
            "declared_team": created.payload.get("declared_team"),
            "created_at": created.ts.isoformat(),
            "resolved_at": resolved.ts.isoformat(),
            "lead_time_hours": round((resolved.ts - created.ts).total_seconds() / 3600, 2),
            "reassignments": sum(event.event_type == "reassignment" for event in ticket_events),
            "handoffs": sum(event.event_type == "handoff" for event in ticket_events),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
