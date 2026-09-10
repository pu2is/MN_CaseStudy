"""Environment configuration; dbt reads the same reporting timezone and destination."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[1]


def reporting_timezone() -> str:
    """Render dbt's canonical timezone expression with the same environment lookup."""
    project = yaml.safe_load((REPO_ROOT / "dbt_project.yml").read_text(encoding="utf-8"))
    expression = project["vars"]["reporting_timezone"]
    value = Environment(undefined=StrictUndefined).from_string(expression).render(env_var=os.getenv)
    ZoneInfo(value)
    return value


def alert_state_path() -> Path:
    path = Path(os.environ.get("ALERT_STATE_DB", str(REPO_ROOT / ".state" / "alerts.sqlite3")))
    return path if path.is_absolute() else REPO_ROOT / path


@dataclass(frozen=True)
class Settings:
    bigquery_project: str
    marts_dataset: str
    roas_alert_threshold: float
    slack_webhook_url: str
    reporting_timezone: str


def load_settings() -> Settings:
    project = os.environ.get("BIGQUERY_PROJECT", "mellow-noir-dev")
    dataset = os.environ.get("BIGQUERY_DATASET", "mellow_noir")
    # dbt's default custom-schema naming is <target_dataset>_marts.
    marts = f"{dataset}_marts"
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("BIGQUERY_PROJECT must be a valid Google Cloud project ID")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,1024}", marts):
        raise ValueError("BIGQUERY_DATASET must produce a valid BigQuery dataset ID")
    threshold = float(os.environ.get("ROAS_ALERT_THRESHOLD", "1.5"))
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("ROAS_ALERT_THRESHOLD must be finite and non-negative")
    timezone = reporting_timezone()
    return Settings(
        bigquery_project=project,
        marts_dataset=marts,
        roas_alert_threshold=threshold,
        # Required only when sending an alert.
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL", "").strip(),
        reporting_timezone=timezone,
    )


def reporting_today(settings: Settings, *, now: datetime | None = None) -> date_cls:
    """Return the reporting date; an injected test instant must be timezone-aware."""
    zone = ZoneInfo(settings.reporting_timezone)
    current = now if now is not None else datetime.now(zone)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(zone).date()
