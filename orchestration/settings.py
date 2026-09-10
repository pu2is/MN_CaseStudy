"""Configuration for the ROAS alert flow, sourced entirely from environment variables.

No secrets or connection details are hard-coded here -- see README.md "Credentials".
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bigquery_project: str
    marts_dataset: str
    roas_alert_threshold: float
    slack_webhook_url: str


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

    return Settings(
        bigquery_project=bigquery_project,
        marts_dataset=marts_dataset,
        roas_alert_threshold=roas_alert_threshold,
        slack_webhook_url=slack_webhook_url,
    )
