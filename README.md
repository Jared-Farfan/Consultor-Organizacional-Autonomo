# Autonomous Organizational Consultant

An organizational diagnostic application that turns operational ticket events into traceable metrics, prioritized findings, and change proposals. It follows a **compute-first, LLM-last** principle: the code calculates figures, while an optional LLM only drafts answers from evidence that has already been calculated.

> The included data is synthetic and experimental. Teams, people, and costs in the demo do not represent real information and must not be used for real decisions without validating the source data.

## What It Does

- Measures lead time, queue time, handoffs, reassignments, and activity concentration.
- Identifies bottlenecks, slow approvals, single-person dependencies, recurring operational debt, triage ping-pong, and misalignment with core work.
- Classifies every finding as tactical, structural, organizational, or strategic.
- Estimates each finding's annual cost from the configured hourly cost.
- Proposes organizational blocks and progressive change horizons with verifiable gates.
- Retains a trace explaining which tool produced each conclusion.

## Requirements

- Python 3.11 or later.
- Docker and Docker Compose only when using PostgreSQL in a container.
- An API key for an OpenAI-compatible provider only when enabling LLM answers.

## Quick Start

The simplest mode reads the included JSONL directly, with no Docker or database required.

```bash
git clone https://github.com/Jared-Farfan/Consultor-Organizacional-Autonomo.git
cd Consultor-Organizacional-Autonomo
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
```

Set the following variables in `.env` to use the included JSONL file:

```dotenv
DATA_SOURCE=jsonl
RAW_EVENT_LOG_PATH=data/raw/event_log_v2.jsonl
TAXONOMY_PATH=data/raw/business_taxonomy_v2.json
ORG_CHART_PATH=data/raw/org_chart_declared_v2.json
LLM_ENABLED=false
```

Start the server:

```bash
uvicorn app.api:app --reload
```

Open `http://localhost:8000/`. Confirm the selected source with:

```bash
curl http://localhost:8000/health
```

The response should report `"data_source":"jsonl"` when following the quick start.

## Using the Interface

1. Open the application at `http://localhost:8000/`.
2. Enter an optional name to identify the scenario, such as `Baseline cost`.
3. Set **Hourly cost (USD)**. It is the estimated value of one hour of work involved in detected problems; it is not an application or LLM charge.
4. Select **Create diagnosis**.
5. Review the metrics, findings, horizon cascade, and investigation trace.
6. Create another investigation with a different hourly cost when you want to evaluate a new scenario. It replaces the current result.

Annual cost is an estimate: every detector multiplies hours observed or inferred by its rule by the selected hourly cost. For example, 1,000 hours of waiting at an hourly cost of 55 USD produces an estimated annual cost of 55,000 USD. It is not a replacement for validated financial accounting.

Only the active investigation is stored **in memory** for questions and traces. Creating another diagnosis replaces it, and it is lost when the API restarts. PostgreSQL stores input events, not diagnostic history.

## Using the API

| Route | Use |
|---|---|
| `GET /` | Web interface. |
| `GET /health` | Service status and active data source. |
| `GET /config/status` | Safe configuration status without secrets. |
| `GET /demo/report` | Runs a diagnosis without saving it to session history. |
| `POST /investigations` | Creates the active investigation, replacing any previous result. |
| `GET /investigations/{id}` | Retrieves the active investigation report and trace. |
| `POST /investigations/{id}/questions` | Asks a question about an investigation's evidence. |
| `GET /investigations/{id}/trace` | Streams the trace as Server-Sent Events. |
| `POST /datasets/materialize` | Generates derived CSV and DuckDB artifacts from the active source. |

Create an investigation through the API:

```bash
curl -X POST http://localhost:8000/investigations \
  -H "Content-Type: application/json" \
  -d '{"label":"Baseline cost scenario","hourly_cost":55}'
```

`hourly_cost` must be greater than zero. It defaults to `55` when omitted. `label` is optional and supports up to 80 characters.

Ask about the newly created diagnosis:

```bash
curl -X POST http://localhost:8000/investigations/INVESTIGATION_ID/questions \
  -H "Content-Type: application/json" \
  -d '{"question":"Which action should reduce onboarding time first?"}'
```

Replace `INVESTIGATION_ID` with the `id` returned by the create-investigation response.

## Data Sources

The application accepts three `DATA_SOURCE` values:

| Source | When to use it | Required configuration |
|---|---|---|
| `jsonl` | Local development or direct analysis of a V2 event log. | `RAW_EVENT_LOG_PATH`, `TAXONOMY_PATH`, `ORG_CHART_PATH`. |
| `duckdb` | Local queries against a materialized version. | `DUCKDB_PATH` and a generated database file. |
| `postgres` | Shared or persistent service environments. | `DATABASE_URL` and loaded tables. |

Relative paths are resolved from the project root. Shell environment variables take precedence over `.env`, so a source can be tested without editing that file:

```bash
DATA_SOURCE=jsonl LLM_ENABLED=false uvicorn app.api:app --reload
```

### JSONL: Direct Source

`data/raw/event_log_v2.jsonl` is the included canonical source. Every line is a JSON object with at least:

```json
{
  "ticket_id": "TCK-00001",
  "ts": "2025-12-16T09:19:23.584192",
  "event_type": "created",
  "actor_hash": "ca6ffc3d276c",
  "from_state": null,
  "to_state": "Backlog",
  "payload": {
    "category": "soporte_reactivo",
    "declared_team": "team_alpha",
    "title": "Work description"
  }
}
```

The loader normalizes the V2 log and derives operational events such as `assigned`, `handoff`, `approval_requested`, `approval_decided`, `completed_stage`, and `resolved`. To keep metrics comparable, a custom dataset must preserve V2 transition semantics, ISO 8601 timestamps, and stable hashes in `actor_hash`.

`data/raw/event_log_v2.csv` is an export for inspection and interoperability; it is **not** the API's input source. Convert a CSV to V2 JSONL or import its events into PostgreSQL before using it.

Provide these files as well, keeping categories and teams consistent with the log:

- `business_taxonomy_v2.json`: a `{category: {label, strategic_value}}` map. `strategic_value` accepts `alto`, `medio`, or `bajo` in the included V2 dataset.
- `org_chart_declared_v2.json`: an object with `teams` and `members`; each member uses `actor_id_hash`, `declared_team`, and `role`.

Example configuration for custom files:

```dotenv
DATA_SOURCE=jsonl
RAW_EVENT_LOG_PATH=/secure/path/my_events.jsonl
TAXONOMY_PATH=/secure/path/my_taxonomy.json
ORG_CHART_PATH=/secure/path/my_organization.json
```

For Jira integrations, `app.ingestion.normalize_jira_ticket()` transforms a Jira-like ticket into the internal `Event` contract and replaces names or emails with hashes. Connectors for Zendesk, ServiceNow, or other tools should produce the same contract and must not read private evaluation material.

### DuckDB: Local Materialized Source

Generate derived artifacts from the included V2 dataset:

```bash
. .venv/bin/activate
python -m app.prepare_data
```

This creates the following files in `data/derived/`:

- `tickets_observed_v2.csv`, an observable-facts summary per ticket.
- `organizational_events_v2.duckdb`, a normalized `events` table.

Then select DuckDB:

```dotenv
DATA_SOURCE=duckdb
DUCKDB_PATH=data/derived/organizational_events_v2.duckdb
```

The DuckDB database is opened read-only during diagnosis. `app.prepare_data` is built for the included V2 dataset; for custom data, first load it into an `events` table using the schema in `db/init/001_schema.sql`, or use the PostgreSQL workflow.

### PostgreSQL: Shared Source

1. Copy `.env.template` to `.env` and replace `POSTGRES_PASSWORD` and `DATABASE_URL` with real values.
2. Keep `DATA_SOURCE=postgres`.
3. Start PostgreSQL and load the events configured by the JSONL, taxonomy, and organization paths:

```bash
docker compose up -d postgres
. .venv/bin/activate
python scripts/import_v2_to_postgres.py --replace
uvicorn app.api:app --reload
```

`--replace` clears and reloads `events`, `org_members`, `org_teams`, `business_taxonomy`, and `dataset_metadata`; only use it when replacing the previous import. The API reads from PostgreSQL in a read-only transaction.

To run the API in Docker after importing data:

```bash
docker compose --profile app up -d api
```

Inspect services with `docker compose ps` and logs with `docker compose logs -f postgres` or `docker compose logs -f api`.

## Optional LLM

Without an LLM, questions receive a deterministic answer based on calculated findings. To use Ollama Cloud or another OpenAI-compatible endpoint, configure:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://ollama.com/v1
LLM_API_KEY=your_secret_key
LLM_MODEL=gpt-oss:20b
LLM_TEMPERATURE=0
LLM_STRUCTURED_OUTPUTS=true
```

The model receives only the executive summary, metrics, findings, and horizon cascade for the selected investigation. It does not receive secrets, private evaluation files, or additional raw data. The model does not calculate metrics or estimate new amounts.

## Security and Data

- `.env` contains local secrets and is excluded from Git. Never publish it.
- `data/private/` contains evaluation material and ground truth. The API, loaders, and detectors do not use it as input.
- `data/derived/` contains regenerable output and is excluded from Git.
- The active demo source contains 6,000 synthetic tickets and 36,910 events in `data/raw/event_log_v2.jsonl`.
- Before loading real information, anonymize personal identifiers and review your organization's retention and access policies.

## Tests and Verification

Run the full suite with the virtual environment available:

```bash
.venv/bin/python -m pytest
```

The suite covers secure configuration, V2 loading and normalization, finding detection, and agent behavior. Before operating the service, also validate the active data source:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/config/status
```

## Agent Tools

- `get_flow_metrics`
- `get_state_queue_times`
- `get_handoff_graph`
- `find_ticket_clusters`
- `classify_business_alignment`
- `classify_change_severity`
- `propose_org_blocks`
- `simulate_change`
- `simulate_horizon_cascade`

A macro change requires at least two of three calculated criteria: structural scope, persistence, and core impact. This rule prevents recommending a full reorganization for an isolated friction point.
