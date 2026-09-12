from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models import Event


FORMAL_ORG = {
    "Onboarding Product": ["onboarding-1", "onboarding-2"],
    "Customer Support": ["support-1", "support-2", "support-hero"],
    "Platform Engineering": ["platform-1", "platform-2"],
    "Risk and Compliance": ["risk-1", "risk-2"],
}

GROUND_TRUTH = {
    "hero_spof": "support-hero participates in critical handoffs",
    "useless_approval": "approval queue is long with low rejection rate",
    "misaligned_silo": "technical communities cross formal product teams",
    "invisible_operational_debt": "repeated access reset cause",
    "triage_ping_pong": "support incidents rotate across four assignees",
    "strategic_misalignment": "support capacity is mostly low strategic value",
    "value_stream_fragmentation": "onboarding crosses four teams with handoff queues",
}


def _actor(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def _event(ticket: str, ts: datetime, kind: str, actor: str, team: str, **payload: object) -> Event:
    return Event(ticket, ts, kind, _actor(actor), team, payload=payload)


def _ticket_events(
    ticket: str,
    start: datetime,
    path: list[tuple[str, str]],
    category: str,
    effort_type: str,
    text: str,
    rng: random.Random,
    approval: bool = False,
) -> list[Event]:
    events = [_event(ticket, start, "created", "intake-bot", path[0][1], category=category,
                     effort_type=effort_type, text=text)]
    current = start
    for index, (team, actor) in enumerate(path):
        queue_hours = rng.expovariate(1 / 10) + (18 if index else 0)
        touch_hours = max(0.3, rng.lognormvariate(0.2, 0.45))
        assigned = current + timedelta(hours=queue_hours)
        events.append(_event(ticket, assigned, "assigned", actor, team, category=category,
                             effort_type=effort_type, text=text, queue_hours=queue_hours))
        current = assigned + timedelta(hours=touch_hours)
        events.append(_event(ticket, current, "completed_stage", actor, team, category=category,
                             effort_type=effort_type, text=text, touch_hours=touch_hours))
        if index < len(path) - 1:
            next_team, next_actor = path[index + 1]
            events.append(_event(ticket, current, "handoff", actor, team, to_team=next_team,
                                 to_actor=_actor(next_actor), category=category, text=text))
    if approval:
        approval_start = current
        approval_end = approval_start + timedelta(days=6 + rng.random())
        events.append(_event(ticket, approval_start, "approval_requested", "risk-1", "Risk and Compliance",
                             category=category, effort_type=effort_type, text=text))
        events.append(_event(ticket, approval_end, "approval_decided", "risk-2", "Risk and Compliance",
                             category=category, effort_type=effort_type, text=text,
                             rejected=rng.random() < 0.02, queue_hours=(approval_end - approval_start).total_seconds() / 3600))
        current = approval_end
    events.append(_event(ticket, current + timedelta(hours=1), "resolved", path[-1][1], path[-1][0],
                         category=category, effort_type=effort_type, text=text))
    return events


def generate_events(seed: int = 42) -> list[Event]:
    """Builds a reproducible dataset. Ground truth is not returned to callers."""
    rng = random.Random(seed)
    base = datetime(2026, 1, 5, tzinfo=timezone.utc)
    events: list[Event] = []
    number = 0

    def add(path: list[tuple[str, str]], category: str, effort: str, text: str, count: int, **kwargs: bool) -> None:
        nonlocal number
        for _ in range(count):
            number += 1
            start = base + timedelta(hours=rng.randint(0, 24 * 150))
            events.extend(_ticket_events(f"T-{number:04d}", start, path, category, effort, text, rng, **kwargs))

    # Fragmented value stream: a high-value customer onboarding crosses four teams.
    add([
        ("Onboarding Product", "onboarding-1"),
        ("Platform Engineering", "support-hero"),
        ("Risk and Compliance", "risk-1"),
        ("Customer Support", "support-hero"),
    ], "strategic_onboarding", "direct_value", "enterprise onboarding provisioning verification", 70)

    # Low-value reactive demand consumes most support capacity and creates a repeated root cause.
    add([("Customer Support", "support-1"), ("Platform Engineering", "platform-2")],
        "reactive_support", "operational_debt", "password reset access provisioning request", 115)

    # Ping-pong triage, intentionally four assignees before a solution.
    add([
        ("Customer Support", "support-1"),
        ("Customer Support", "support-2"),
        ("Platform Engineering", "platform-1"),
        ("Customer Support", "support-hero"),
    ], "reactive_support", "process_friction", "ambiguous integration incident triage", 61)

    # Approval delay is a contained tactical friction.
    add([("Onboarding Product", "onboarding-2"), ("Risk and Compliance", "risk-2")],
        "regulatory_compliance", "process_friction", "standard contract approval review", 55, approval=True)

    # Background healthy, high-value work.
    add([("Platform Engineering", "platform-1"), ("Onboarding Product", "onboarding-2")],
        "customer_retention", "direct_value", "retention integration configuration", 35)
    return sorted(events, key=lambda event: (event.ticket_id, event.ts))


def write_dataset(output: Path, seed: int) -> None:
    events = generate_events(seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([event.to_dict() for event in events], indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reproducible synthetic event data")
    parser.add_argument("--output", type=Path, default=Path("data/legacy/v1/synthetic_events_v1.json"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    write_dataset(args.output, args.seed)
    print(f"Wrote synthetic dataset to {args.output}")


if __name__ == "__main__":
    main()
