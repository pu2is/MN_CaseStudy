# mellow NOIR — Marketing Performance Case Study

Daily CAC/ROAS reporting pipeline: Shopify orders + Meta Ads spend, merged in BigQuery via dbt
into `fct_marketing_performance`, with Prefect-based orchestration and Slack alerting on
ROAS drops.

## Where things live

| Path | Contents |
| --- | --- |
| [`models/`](models/) | dbt SQL models (`staging/` → `intermediate/` → `marts/`) |
| [`orchestration/`](orchestration/) | Prefect flow(s) that run dbt and send Slack alerts |
| [`architecture/`](architecture/) | Architecture diagram(s) and written answers to Task 1 |
| [`docs/`](docs/) | Supporting write-ups and notes |
| [`dbt_project.yml`](dbt_project.yml), [`profiles.yml`](profiles.yml) | dbt project + connection config (no secrets — see below) |
| [`pyproject.toml`](pyproject.toml), [`uv.lock`](uv.lock) | Python dependencies, managed with [uv](https://docs.astral.sh/uv/) |

## Setup

```bash
uv sync
uv run dbt --version
uv run dbt parse
```

`dbt` commands need `DBT_PROFILES_DIR` pointed at the repo root (or pass `--profiles-dir .`):

```bash
export DBT_PROFILES_DIR=.
```

## Running the ROAS alert flow

```bash
uv run python -m orchestration.flow
```

This runs `run_dbt` -> `run_dbt_tests` -> `check_yesterday_roas` -> `send_slack_alert`
(ingestion is assumed to have already completed and is out of scope here). A Slack
message is only sent when yesterday's ROAS is below the alert threshold; a missing or
null ROAS is treated as a data-quality issue, not a low-ROAS alert, and stays silent.

Additional environment variables beyond the BigQuery ones above:

- `SLACK_WEBHOOK_URL` — required only when an alert actually fires.
- `ROAS_ALERT_THRESHOLD` — defaults to `1.5`.
- `BIGQUERY_MARTS_DATASET` — defaults to `<BIGQUERY_DATASET>_marts`, matching dbt's
  default schema naming for the `marts` custom schema.
- `REPORTING_TIMEZONE` — defaults to `Europe/Berlin`. The single reporting-timezone
  policy shared by the Prefect flow's "yesterday" calculation and dbt's `order_date`
  derivation in `stg_shopify_orders` (forwarded to every `dbt` invocation via
  `--vars`, so it never drifts from the `reporting_timezone` default in
  `dbt_project.yml`). Also documents the assumed Meta ad account timezone — see
  `models/staging/meta/stg_meta_insights.sql`. If a real Meta ad account uses a
  different timezone, its dates must be normalized to this one before joining.

Run the automated tests (BigQuery and the Slack webhook call are both mocked) with:

```bash
uv run pytest
```

## Credentials

No secrets are committed to this repo. `profiles.yml` reads connection details from
environment variables:

- `dev` target: uses local `gcloud auth application-default login` credentials (no keyfile
  needed).
- `ci` target: reads a service-account keyfile *path* from `GOOGLE_APPLICATION_CREDENTIALS`.
- `BIGQUERY_PROJECT`, `BIGQUERY_DATASET`, `BIGQUERY_LOCATION` override the BigQuery
  destination.

Slack webhook URLs and any API tokens are supplied at runtime via environment variables —
never checked in.
