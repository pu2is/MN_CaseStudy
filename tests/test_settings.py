"""Reporting dates must be independent of the host timezone."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from orchestration.settings import Settings, load_settings, reporting_today

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


def _settings(reporting_timezone: str = "Europe/Berlin") -> Settings:
    return Settings(
        bigquery_project="p",
        marts_dataset="d",
        roas_alert_threshold=1.5,
        slack_webhook_url="",
        reporting_timezone=reporting_timezone,
    )


def test_late_evening_utc_rolls_over_to_next_day_in_berlin():
    # 23:30 UTC on the 8th is already 01:30 CEST on the 9th in Berlin.
    now = datetime(2026, 9, 8, 23, 30, tzinfo=UTC)

    result = reporting_today(_settings(), now=now)

    assert result == datetime(2026, 9, 9, tzinfo=BERLIN).date()


def test_early_morning_utc_stays_same_day_in_berlin():
    # 00:30 UTC on the 9th is 02:30 CEST on the 9th in Berlin -- no rollover.
    now = datetime(2026, 9, 9, 0, 30, tzinfo=UTC)

    result = reporting_today(_settings(), now=now)

    assert result == datetime(2026, 9, 9, tzinfo=BERLIN).date()


def test_reporting_today_follows_the_configured_timezone_not_utc():
    # Same instant, different configured reporting_timezone -> different date.
    now = datetime(2026, 9, 8, 23, 30, tzinfo=UTC)

    berlin_result = reporting_today(_settings("Europe/Berlin"), now=now)
    utc_result = reporting_today(_settings("UTC"), now=now)

    assert berlin_result == datetime(2026, 9, 9, tzinfo=BERLIN).date()
    assert utc_result == datetime(2026, 9, 8, tzinfo=UTC).date()


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        reporting_today(_settings(), now=datetime(2026, 9, 8, 23, 30))


@pytest.mark.parametrize("threshold", ["nan", "inf", "-0.1", "invalid"])
def test_invalid_threshold_rejected(monkeypatch, threshold):
    monkeypatch.setenv("ROAS_ALERT_THRESHOLD", threshold)
    with pytest.raises(ValueError):
        load_settings()


def test_default_mart_dataset_matches_dbt(monkeypatch):
    monkeypatch.setenv("BIGQUERY_DATASET", "review")
    assert load_settings().marts_dataset == "review_marts"


@pytest.mark.parametrize("override", [None, "America/New_York", "UTC"])
def test_python_uses_dbt_timezone_expression(monkeypatch, override):
    import os

    import yaml
    from dbt.clients.jinja import get_rendered

    from orchestration.settings import REPO_ROOT

    if override is None:
        monkeypatch.delenv("REPORTING_TIMEZONE", raising=False)
    else:
        monkeypatch.setenv("REPORTING_TIMEZONE", override)
    project = yaml.safe_load((REPO_ROOT / "dbt_project.yml").read_text(encoding="utf-8"))
    dbt_value = get_rendered(project["vars"]["reporting_timezone"], {"env_var": os.getenv})
    assert load_settings().reporting_timezone == dbt_value


def test_changing_canonical_default_changes_python_without_code_edit(monkeypatch, tmp_path):
    monkeypatch.delenv("REPORTING_TIMEZONE", raising=False)
    (tmp_path / "dbt_project.yml").write_text(
        "vars:\n  reporting_timezone: \"{{ env_var('REPORTING_TIMEZONE', 'UTC') }}\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("orchestration.settings.REPO_ROOT", tmp_path)
    assert load_settings().reporting_timezone == "UTC"
