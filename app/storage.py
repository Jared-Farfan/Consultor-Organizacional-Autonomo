from __future__ import annotations

from pathlib import Path
import json

from app.models import Event


def materialize_events(events: list[Event], database_path: Path) -> dict[str, int | str]:
    """Persists the canonical event log in DuckDB through a pandas dataframe."""
    try:
        import duckdb
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("Install requirements.txt to materialize events in DuckDB.") from error
    database_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for event in events:
        row = event.to_dict()
        row["payload"] = json.dumps(row["payload"], ensure_ascii=False)
        rows.append(row)
    frame = pd.DataFrame(rows)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """CREATE OR REPLACE TABLE events AS
            SELECT ticket_id, CAST(ts AS TIMESTAMPTZ) AS ts, event_type, actor_hash,
                   team, CAST(from_state AS VARCHAR) AS from_state, CAST(to_state AS VARCHAR) AS to_state,
                   CAST(payload AS JSON) AS payload
            FROM frame"""
        )
        count = connection.execute("SELECT count(*) FROM events").fetchone()[0]
    return {"database": str(database_path), "events": int(count)}
