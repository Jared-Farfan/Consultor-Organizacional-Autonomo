#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.ingestion import load_event_log_v2, load_org_chart, load_taxonomy


def import_v2(replace: bool) -> dict[str, int]:
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required to import PostgreSQL data")
    import psycopg

    events = load_event_log_v2(settings.raw_event_log_path, settings.org_chart_path)
    taxonomy = load_taxonomy(settings.taxonomy_path)
    org_chart = load_org_chart(settings.org_chart_path)
    with psycopg.connect(settings.database_url, connect_timeout=settings.db_connect_timeout_seconds) as connection:
        with connection.cursor() as cursor:
            if replace:
                cursor.execute("TRUNCATE events, org_members, org_teams, business_taxonomy, dataset_metadata RESTART IDENTITY CASCADE")
            cursor.executemany(
                """INSERT INTO events (ticket_id, ts, event_type, actor_hash, team, from_state, to_state, payload)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (event.ticket_id, event.ts, event.event_type, event.actor_hash, event.team,
                     event.from_state, event.to_state, Jsonb(event.payload))
                    for event in events
                ],
            )
            cursor.executemany(
                """INSERT INTO business_taxonomy (category_key, label, strategic_criticality, core)
                   VALUES (%s, %s, %s, %s)""",
                [(item.key, item.label, item.strategic_criticality, item.core) for item in taxonomy],
            )
            cursor.executemany(
                "INSERT INTO org_teams (team_id, name, product_line) VALUES (%s, %s, %s)",
                [(team_id, team["name"], team["product_line"]) for team_id, team in org_chart["teams"].items()],
            )
            cursor.executemany(
                "INSERT INTO org_members (actor_hash, declared_team, role) VALUES (%s, %s, %s)",
                [(member["actor_id_hash"], member["declared_team"], member["role"]) for member in org_chart["members"]],
            )
            cursor.execute(
                """INSERT INTO dataset_metadata (metadata_key, metadata_value)
                   VALUES ('v2_import', %s)
                   ON CONFLICT (metadata_key) DO UPDATE SET metadata_value = EXCLUDED.metadata_value,
                   updated_at = CURRENT_TIMESTAMP""",
                (Jsonb({"events": len(events), "tickets": len({event.ticket_id for event in events})}),),
            )
    return {"events": len(events), "tickets": len({event.ticket_id for event in events}), "taxonomy": len(taxonomy)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the normalized V2 dataset into PostgreSQL")
    parser.add_argument("--replace", action="store_true", help="Replace existing imported data")
    args = parser.parse_args()
    print(json.dumps(import_v2(args.replace), indent=2))


if __name__ == "__main__":
    main()
