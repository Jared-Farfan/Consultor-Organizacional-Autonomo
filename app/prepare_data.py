from __future__ import annotations

from pathlib import Path

from app.ingestion import load_event_log_v2, write_observed_ticket_summary
from app.storage import materialize_events


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    raw = root / "data" / "raw"
    derived = root / "data" / "derived"
    events = load_event_log_v2(raw / "event_log_v2.jsonl", raw / "org_chart_declared_v2.json")
    tickets = write_observed_ticket_summary(events, derived / "tickets_observed_v2.csv")
    database = materialize_events(events, derived / "organizational_events_v2.duckdb")
    print(f"Normalized {len(events)} events and wrote {tickets} observable ticket summaries.")
    print(database)


if __name__ == "__main__":
    main()
