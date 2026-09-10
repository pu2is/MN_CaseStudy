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
