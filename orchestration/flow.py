"""Prefect flow: run dbt, then check yesterday's ROAS and alert Slack if it's low.

Conceptual production flow:

    ingest_shopify -> ingest_meta -> run_dbt -> run_dbt_tests
        -> check_yesterday_roas -> validate_slack_webhook_url -> send_slack_alert

Ingestion is out of scope for this case study (assumed already complete), so
this flow starts at run_dbt. Retries are attached to every task that talks to
an external system (BigQuery, Slack, or a dbt subprocess hitting BigQuery),
not to the pure classification logic in roas_check.evaluate_roas or to
validate_slack_webhook_url, whose config error is permanent and never worth
retrying.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

from google.cloud import bigquery
from prefect import flow, get_run_logger, task

from orchestration.roas_check import (
    RoasCheckResult,
    RoasStatus,
    evaluate_roas,
    fetch_fct_marketing_performance_row,
)
from orchestration.settings import load_settings, reporting_today
from orchestration.slack import build_slack_payload, send_slack_alert

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_dbt_command(*args: str) -> None:
    env = {**os.environ, "DBT_PROFILES_DIR": str(REPO_ROOT)}
    subprocess.run(["uv", "run", "dbt", *args], cwd=REPO_ROOT, env=env, check=True)


def _dbt_vars_args(settings) -> tuple[str, str]:
    # Forwards the same reporting timezone Python uses for "yesterday" into
    # dbt's order_date calculation, so the two never drift -- see
    # orchestration/settings.py's module docstring.
    return ("--vars", json.dumps({"reporting_timezone": settings.reporting_timezone}))


@task(retries=1, retry_delay_seconds=30)
def run_dbt() -> None:
    settings = load_settings()
    _run_dbt_command("run", *_dbt_vars_args(settings))


@task(retries=1, retry_delay_seconds=30)
def run_dbt_tests() -> None:
    settings = load_settings()
    _run_dbt_command("test", *_dbt_vars_args(settings))


@task(retries=3, retry_delay_seconds=[10, 30, 60])
def check_yesterday_roas() -> RoasCheckResult:
    settings = load_settings()
    yesterday = reporting_today(settings) - timedelta(days=1)

    client = bigquery.Client(project=settings.bigquery_project)
    row = fetch_fct_marketing_performance_row(
        client, settings.bigquery_project, settings.marts_dataset, yesterday
    )
    return evaluate_roas(row, yesterday, settings.roas_alert_threshold)


@task
def validate_slack_webhook_url() -> str:
    """Fail fast on missing Slack configuration.

    A missing SLACK_WEBHOOK_URL is a permanent configuration error, not a
    transient failure -- retrying it would just delay an inevitable failure.
    This task deliberately has no retries so the flow fails immediately,
    while send_roas_alert's HTTP call keeps its own retries for genuinely
    transient delivery failures.
    """
    settings = load_settings()
    if not settings.slack_webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set -- cannot send ROAS alert.")
    return settings.slack_webhook_url


@task(retries=3, retry_delay_seconds=[10, 30, 60])
def send_roas_alert(webhook_url: str, result: RoasCheckResult) -> None:
    payload = build_slack_payload(result)
    send_slack_alert(webhook_url, payload)


@flow(name="check-roas-and-alert")
def check_roas_and_alert_flow() -> RoasCheckResult:
    logger = get_run_logger()

    run_dbt()
    run_dbt_tests()

    result = check_yesterday_roas()

    if result.status is RoasStatus.BELOW_THRESHOLD:
        logger.warning(
            "ROAS %.2f on %s is below threshold %.2f -- sending Slack alert.",
            result.roas,
            result.date,
            result.threshold,
        )
        webhook_url = validate_slack_webhook_url()
        send_roas_alert(webhook_url, result)
    elif result.status is RoasStatus.DATA_UNAVAILABLE:
        logger.warning(
            "ROAS unavailable for %s -- treating as a data-quality issue, not a "
            "performance alert. No Slack message sent.",
            result.date,
        )
    else:
        logger.info(
            "ROAS %.2f on %s is at/above threshold %.2f -- no alert needed.",
            result.roas,
            result.date,
            result.threshold,
        )

    return result


if __name__ == "__main__":
    check_roas_and_alert_flow()
