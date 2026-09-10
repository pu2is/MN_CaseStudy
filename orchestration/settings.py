"""Configuration for the ROAS alert flow, sourced entirely from environment variables.

No secrets or connection details are hard-coded here -- see README.md "Credentials".

REPORTING_TIMEZONE is the single source of truth for "what calendar day is
this" across the whole pipeline: Shopify's order_date (models/staging/shopify/
stg_shopify_orders.sql, via the dbt `reporting_timezone` var), the Meta
account's assumed reporting calendar (models/staging/meta/stg_meta_insights.sql),
and reporting_today() below, which the Prefect flow uses instead of
date.today() so "yesterday" doesn't depend on the host/Docker/developer
machine's timezone. run_dbt()/run_dbt_tests() forward this same value to dbt
via `--vars` so the dbt vars default in dbt_project.yml only matters for a
developer invoking dbt directly, and never drifts from the Python side in the
actual flow. If the real Meta ad account is ever configured with a different
timezone, its dates must be normalized to REPORTING_TIMEZONE before joining
in fct_marketing_performance -- see stg_meta_insights.sql.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    bigquery_project: str
    marts_dataset: str
    roas_alert_threshold: float
    slack_webhook_url: str
    reporting_timezone: str


def load_settings() -> Settings:
    bigquery_project = os.environ.get("BIGQUERY_PROJECT", "mellow-noir-dev")
    bigquery_dataset = os.environ.get("BIGQUERY_DATASET", "mellow_noir")

    # dbt_project.yml puts marts models under `+schema: marts` without a custom
    # generate_schema_name macro, so dbt-bigquery's default naming applies:
    # "<target_dataset>_<custom_schema>". Override with BIGQUERY_MARTS_DATASET
    # if that macro is ever customized.
    default_marts_dataset = f"{bigquery_dataset}_marts"
    marts_dataset = os.environ.get("BIGQUERY_MARTS_DATASET", default_marts_dataset)

    roas_alert_threshold = float(os.environ.get("ROAS_ALERT_THRESHOLD", "1.5"))

    # Deliberately not required here -- only send_slack_alert needs it, and only
    # when an alert actually fires. Missing at that point is a real config error.
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")

    # Must match dbt_project.yml's `reporting_timezone` var default -- see this
    # module's docstring. Validated eagerly so a typo'd zone name fails at
    # startup, not as a silently wrong "yesterday" inside the Prefect flow.
    reporting_timezone = os.environ.get("REPORTING_TIMEZONE", "Europe/Berlin")
    ZoneInfo(reporting_timezone)

    return Settings(
        bigquery_project=bigquery_project,
        marts_dataset=marts_dataset,
        roas_alert_threshold=roas_alert_threshold,
        slack_webhook_url=slack_webhook_url,
        reporting_timezone=reporting_timezone,
    )


def reporting_today(settings: Settings, *, now: datetime | None = None) -> date_cls:
    """Calendar date "today" in settings.reporting_timezone.

    This is the one place "today" is computed for the alert flow -- never call
    date.today() elsewhere, since that silently depends on the host's
    timezone. `now` is only for tests (inject a fixed, timezone-aware
    instant); production callers should omit it.
    """
    current = now if now is not None else datetime.now(ZoneInfo(settings.reporting_timezone))
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(ZoneInfo(settings.reporting_timezone)).date()
