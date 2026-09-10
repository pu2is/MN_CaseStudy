"""Build and validate the daily mart, then alert on yesterday's blended ROAS.

Ingestion is assumed complete by the case study. External tasks explicitly
disable caching so each invocation performs its database or delivery operation.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from google.cloud import bigquery
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from orchestration.roas_check import (
    RoasCheckResult,
    RoasStatus,
    evaluate_roas,
    fetch_fct_marketing_performance_row,
)
from orchestration.settings import alert_state_path, load_settings, reporting_today
from orchestration.slack import (
    build_slack_payload,
    send_slack_alert,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@task(retries=0, cache_policy=NO_CACHE)
def build_dbt() -> None:
    env = {**os.environ, "DBT_PROFILES_DIR": str(REPO_ROOT)}
    # Use the running environment; nested `uv run` could select another Python.
    # build tests upstream models before allowing dependent models to run.
    subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "build"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        timeout=1800,
    )


@task(retries=3, retry_delay_seconds=[10, 30, 60], cache_policy=NO_CACHE)
def check_roas(
    target_date: date, bigquery_project: str, marts_dataset: str, roas_alert_threshold: float
) -> RoasCheckResult:
    with bigquery.Client(project=bigquery_project) as client:
        row = fetch_fct_marketing_performance_row(
            client, bigquery_project, marts_dataset, target_date
        )
    return evaluate_roas(row, target_date, roas_alert_threshold)


def alert_key(
    kind: str, target_date: date, bigquery_project: str, marts_dataset: str, reporting_timezone: str
) -> str:
    return f"{bigquery_project}.{marts_dataset}:{reporting_timezone}:{target_date}:{kind}"


@task(retries=0, cache_policy=NO_CACHE)
def send_roas_alert(result: RoasCheckResult, delivery_key: str) -> None:
    # Read directly from the environment -- a webhook secret must never be
    # passed as a task parameter, where Prefect would record it as a visible
    # task input.
    send_slack_alert(
        os.environ.get("SLACK_WEBHOOK_URL", "").strip(),
        build_slack_payload(result),
        delivery_key=delivery_key,
        state_path=alert_state_path(),
    )


@task(retries=0, cache_policy=NO_CACHE)
def send_operational_alert(
    target_date: date, stage: str, bigquery_project: str, marts_dataset: str, delivery_key: str
) -> None:
    webhook = (
        os.environ.get("OPS_SLACK_WEBHOOK_URL", "").strip()
        or os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    )
    # Do not include exception text: API errors may contain credentials or source data.
    payload = {
        "text": (
            f":warning: *Marketing pipeline failure -- {target_date}*\n"
            f"Stage: {stage}\n"
            f"Dataset: {bigquery_project}.{marts_dataset}\n"
            "Report not validated. Check the failed Prefect run and dbt results.\n"
            "This is a data/operations alert, not a low-ROAS warning."
        )
    }
    send_slack_alert(webhook, payload, delivery_key=delivery_key, state_path=alert_state_path())


@flow(name="check-roas-and-alert")
def check_roas_and_alert_flow(target_date: date | None = None) -> RoasCheckResult:
    logger = get_run_logger()
    # Freeze the business date before build/retries can cross midnight.
    settings = load_settings()
    target_date = target_date or reporting_today(settings) - timedelta(days=1)
    # Configuration is mandatory before work starts: failures need a human channel.
    if not (os.environ.get("OPS_SLACK_WEBHOOK_URL", "").strip() or settings.slack_webhook_url):
        raise RuntimeError(
            "OPS_SLACK_WEBHOOK_URL or SLACK_WEBHOOK_URL is required for failure alerts"
        )
    stage = "dbt-build"
    try:
        build_dbt()
        stage = "roas-query"
        result = check_roas(
            target_date,
            settings.bigquery_project,
            settings.marts_dataset,
            settings.roas_alert_threshold,
        )
        if result.status is RoasStatus.DATA_UNAVAILABLE:
            stage = "data-quality"
            raise RuntimeError(f"ROAS data unavailable or invalid for {result.date}")
        if result.status is RoasStatus.BELOW_THRESHOLD:
            stage = "roas-alert"
            logger.warning(
                "ROAS %.2f on %s is below %.2f; checking alert delivery.",
                result.roas,
                result.date,
                result.threshold,
            )
            send_roas_alert(
                result,
                alert_key(
                    "low-roas",
                    result.date,
                    settings.bigquery_project,
                    settings.marts_dataset,
                    settings.reporting_timezone,
                ),
            )
        elif result.status is RoasStatus.NO_SPEND:
            logger.info("No ad spend on %s; ROAS is undefined and no alert is needed.", result.date)
        else:
            logger.info(
                "ROAS %.2f on %s is at/above %.2f.", result.roas, result.date, result.threshold
            )
    except Exception as pipeline_error:
        try:
            send_operational_alert(
                target_date,
                stage,
                settings.bigquery_project,
                settings.marts_dataset,
                alert_key(
                    f"operations:{stage}",
                    target_date,
                    settings.bigquery_project,
                    settings.marts_dataset,
                    settings.reporting_timezone,
                ),
            )
        except Exception as notification_error:
            # Preserve both failures; notification problems cannot turn the run green.
            raise ExceptionGroup(
                "Pipeline failed and its operational notification also failed",
                [pipeline_error, notification_error],
            ) from None
        raise
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="Reporting date for a manual rerun")
    check_roas_and_alert_flow(target_date=parser.parse_args().date)
