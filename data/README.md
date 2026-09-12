# Data Layout

## Runtime Inputs

`raw/event_log_v2.jsonl` is the canonical source consumed by the application.
It contains operational events only. `raw/event_log_v2.csv` is an equivalent
tabular export, retained for inspection and interoperability.

`raw/business_taxonomy_v2.json` anchors strategic value classification.
`raw/org_chart_declared_v2.json` contains the formal organization used to
contrast observed handoffs with declared teams.

## Derived Outputs

Run `python -m app.prepare_data` to generate:

- `derived/tickets_observed_v2.csv`: observable ticket facts only.
- `derived/organizational_events_v2.duckdb`: normalized analytical store.

These outputs can always be regenerated from `raw/`.

## Private Evaluation Material

`private/evaluation/` contains labels and ground truth exclusively for
validation. The API, loader and agent never read this directory. Do not serve,
package or use these files as input to a detector.

## Legacy Material

`legacy/v1/` keeps the earlier 336-ticket synthetic demo for regression only.
It is not the active API dataset.
