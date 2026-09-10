"""Prefect flow: run dbt, then check yesterday's ROAS and alert Slack if it's low.

Conceptual production flow:

    ingest_shopify -> ingest_meta -> run_dbt -> run_dbt_tests
        -> check_yesterday_roas -> send_slack_alert

Ingestion is out of scope for this case study (assumed already complete), so
this flow starts at run_dbt. Retries are attached to every task that talks to
an external system (BigQuery, Slack, or a dbt subprocess hitting BigQuery),
not to the pure classification logic in roas_check.evaluate_roas.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

from google.cloud import bigquery
from prefect import flow, get_run_logger, task

from orchestration.roas_check import (
    RoasCheckResult,
    RoasStatus,
    evaluate_roas,
    fetch_fct_marketing_performance_row,
)
from orchestration.settings import load_settings
from orchestration.slack import build_slack_payload, send_slack_alert

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_dbt_command(*args: str) -> None:
    env = {**os.environ, "DBT_PROFILES_DIR": str(REPO_ROOT)}
    subprocess.run(["uv", "run", "dbt", *args], cwd=REPO_ROOT, env=env, check=True)


@task(retries=1, retry_delay_seconds=30)
def run_dbt() -> None:
    _run_dbt_command("run")


@task(retries=1, retry_delay_seconds=30)
def run_dbt_tests() -> None:
    _run_dbt_command("test")


@task(retries=3, retry_delay_seconds=[10, 30, 60])
def check_yesterday_roas() -> RoasCheckResult:
    settings = load_settings()
    yesterday = date.today() - timedelta(days=1)

    client = bigquery.Client(project=settings.bigquery_project)
    row = fetch_fct_marketing_performance_row(
        client, settings.bigquery_project, settings.marts_dataset, yesterday
    )
    return evaluate_roas(row, yesterday, settings.roas_alert_threshold)


@task(retries=3, retry_delay_seconds=[10, 30, 60])
def send_roas_alert(result: RoasCheckResult) -> None:
    settings = load_settings()
    payload = build_slack_payload(result)
    send_slack_alert(settings.slack_webhook_url, payload)


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
        send_roas_alert(result)
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
