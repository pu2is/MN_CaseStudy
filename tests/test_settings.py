"""Verifies REPORTING_TIMEZONE governs "today"/"yesterday" independently of
the host timezone -- Issue 11's verification scenarios.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from orchestration.settings import Settings, reporting_today

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
    # 23:30 UTC on the 8th is already 00:30 CEST on the 9th in Berlin.
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
