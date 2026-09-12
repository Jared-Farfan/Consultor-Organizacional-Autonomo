from __future__ import annotations

import json
from pathlib import Path

from app.models import Event, TaxonomyEntry


def _postgres_connection(database_url: str, timeout_seconds: int):
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("Install requirements.txt to use PostgreSQL.") from error
    return psycopg.connect(database_url, connect_timeout=timeout_seconds)


def load_postgres_events(database_url: str, timeout_seconds: int) -> list[Event]:
    query = """SELECT ticket_id, ts, event_type, actor_hash, team, from_state, to_state, payload
               FROM events ORDER BY ticket_id, ts, event_id"""
    with _postgres_connection(database_url, timeout_seconds) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query)
            rows = cursor.fetchall()
    return [
        Event(
            ticket_id=row[0], ts=row[1], event_type=row[2], actor_hash=row[3], team=row[4],
            from_state=row[5], to_state=row[6], payload=row[7] if isinstance(row[7], dict) else json.loads(row[7]),
        )
        for row in rows
    ]


def load_postgres_taxonomy(database_url: str, timeout_seconds: int) -> tuple[TaxonomyEntry, ...]:
    with _postgres_connection(database_url, timeout_seconds) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT category_key, label, strategic_criticality, core FROM business_taxonomy ORDER BY category_key"
            )
            rows = cursor.fetchall()
    return tuple(TaxonomyEntry(key=row[0], label=row[1], strategic_criticality=row[2], core=row[3]) for row in rows)


def load_duckdb_events(database_path: Path) -> list[Event]:
    try:
        import duckdb
    except ImportError as error:
        raise RuntimeError("Install requirements.txt to use DuckDB.") from error
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT ticket_id, ts, event_type, actor_hash, team, from_state, to_state, payload FROM events ORDER BY ticket_id, ts"
        ).fetchall()
    return [
        Event(
            ticket_id=row[0], ts=row[1], event_type=row[2], actor_hash=row[3], team=row[4],
            from_state=row[5], to_state=row[6], payload=row[7] if isinstance(row[7], dict) else json.loads(row[7]),
        )
        for row in rows
    ]
