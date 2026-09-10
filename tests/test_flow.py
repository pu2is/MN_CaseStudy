"""Exercise Prefect flow control with BigQuery, dbt and Slack mocked."""

from datetime import date
from unittest.mock import patch

import httpx
import pytest
from prefect import flow
from prefect.testing.utilities import prefect_test_harness

from orchestration.flow import (
    build_dbt,
    check_roas_and_alert_flow,
)
from orchestration.roas_check import RoasStatus
from orchestration.slack import SlackDeliveryError

TARGET = date(2026, 9, 9)


@pytest.fixture(autouse=True, scope="module")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("ALERT_STATE_DB", str(tmp_path / "alerts.sqlite3"))
    monkeypatch.delenv("OPS_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("BIGQUERY_PROJECT", "mellow-noir-test")
    monkeypatch.setenv("ROAS_ALERT_THRESHOLD", "1.5")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/fake")
    with patch("orchestration.flow.reporting_today", return_value=date(2026, 9, 10)):
        yield


@pytest.fixture
def services():
    with (
        patch("orchestration.flow.build_dbt") as build,
        patch("orchestration.flow.bigquery.Client"),
        patch("orchestration.flow.fetch_fct_marketing_performance_row") as fetch,
        patch("orchestration.slack.httpx.post") as post,
    ):
        post.return_value = httpx.Response(200, text="ok")
        yield build, fetch, post


@pytest.mark.parametrize(
    "roas, status, sends",
    [
        (0, RoasStatus.BELOW_THRESHOLD, 1),
        (1.2, RoasStatus.BELOW_THRESHOLD, 1),
        (1.5, RoasStatus.OK, 0),
        (1.8, RoasStatus.OK, 0),
    ],
)
def test_performance_alert_boundary(services, roas, status, sends):
    build, fetch, post = services
    fetch.return_value = {"date": TARGET, "roas": roas, "revenue": roas * 1000, "ad_spend": 1000}
    result = check_roas_and_alert_flow()
    assert result.status is status
    build.assert_called_once()
    assert fetch.call_args.args[-1] == TARGET
    assert post.call_count == sends


@pytest.mark.parametrize(
    "row", [None, {"date": TARGET, "roas": None, "revenue": None, "ad_spend": 50}]
)
def test_missing_data_sends_operational_alert_and_fails(services, row):
    _, fetch, post = services
    fetch.return_value = row
    with pytest.raises(RuntimeError, match="unavailable"):
        check_roas_and_alert_flow()
    post.assert_called_once()
    assert "pipeline failure" in post.call_args.kwargs["json"]["text"]


def test_zero_spend_is_success_without_alert(services):
    _, fetch, post = services
    fetch.return_value = {"date": TARGET, "roas": None, "revenue": 100, "ad_spend": 0}
    assert check_roas_and_alert_flow().status is RoasStatus.NO_SPEND
    post.assert_not_called()


def test_repeated_runs_query_fresh_data(services):
    _, fetch, post = services
    fetch.side_effect = [
        {"date": TARGET, "roas": 1.2, "revenue": 120, "ad_spend": 100},
        {"date": TARGET, "roas": 2, "revenue": 200, "ad_spend": 100},
    ]
    assert check_roas_and_alert_flow().status is RoasStatus.BELOW_THRESHOLD
    assert check_roas_and_alert_flow().status is RoasStatus.OK
    assert fetch.call_count == 2
    post.assert_called_once()


def test_failed_dbt_blocks_query_and_alert(services):
    build, fetch, post = services
    build.side_effect = RuntimeError("dbt build failed")
    with pytest.raises(RuntimeError, match="dbt build failed"):
        check_roas_and_alert_flow()
    fetch.assert_not_called()
    post.assert_called_once()
    assert "dbt-build" in post.call_args.kwargs["json"]["text"]


def test_missing_webhook_fails_without_http_call(services, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL")
    _, fetch, post = services
    fetch.return_value = {"date": TARGET, "roas": 1.2, "revenue": 120, "ad_spend": 100}
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        check_roas_and_alert_flow()
    post.assert_not_called()


def test_repeated_low_roas_runs_do_not_duplicate_alert(services):
    _, fetch, post = services
    fetch.return_value = {"date": TARGET, "roas": 1.2, "revenue": 120, "ad_spend": 100}
    check_roas_and_alert_flow()
    check_roas_and_alert_flow()
    post.assert_called_once()


def test_failed_low_roas_alert_triggers_operational_notification_and_is_retried(services):
    """A failed low-ROAS Slack delivery must not vanish silently: it has to
    surface as an operational failure, and a later run must still be able to
    deliver it since it was never marked sent."""
    _, fetch, post = services
    fetch.return_value = {"date": TARGET, "roas": 1.2, "revenue": 120, "ad_spend": 100}
    post.side_effect = httpx.ReadTimeout("response lost")
    with pytest.raises(ExceptionGroup) as error:
        check_roas_and_alert_flow()
    assert len(error.value.exceptions) == 2
    assert all(isinstance(exc, SlackDeliveryError) for exc in error.value.exceptions)
    assert post.call_count == 2  # the failed low-ROAS alert, then the operational alert

    post.side_effect = None
    post.return_value = httpx.Response(200, text="ok")
    result = check_roas_and_alert_flow()
    assert result.status is RoasStatus.BELOW_THRESHOLD
    assert post.call_count == 3  # the low-ROAS alert retried and delivered


def test_operational_notification_failure_preserves_both_errors(services):
    build, _, post = services
    build.side_effect = RuntimeError("invalid source values")
    post.side_effect = httpx.ReadTimeout("lost response")
    with pytest.raises(ExceptionGroup) as error:
        check_roas_and_alert_flow()
    assert len(error.value.exceptions) == 2
    assert str(error.value.exceptions[0]) == "invalid source values"
    assert isinstance(error.value.exceptions[1], SlackDeliveryError)
    post.assert_called_once()


def test_separate_operations_webhook_and_incident_dedup(services, monkeypatch):
    monkeypatch.setenv("OPS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/ops-fake")
    build, _, post = services
    build.side_effect = RuntimeError("private source detail")
    for _ in range(2):
        with pytest.raises(RuntimeError, match="private source detail"):
            check_roas_and_alert_flow()
    post.assert_called_once()
    assert post.call_args.args[0].endswith("ops-fake")
    assert "private source detail" not in post.call_args.kwargs["json"]["text"]


def test_query_failure_notifies_operations(services):
    _, _, post = services
    with patch("orchestration.flow.check_roas", side_effect=RuntimeError("warehouse unavailable")):
        with pytest.raises(RuntimeError, match="warehouse unavailable"):
            check_roas_and_alert_flow()
    post.assert_called_once()
    assert "roas-query" in post.call_args.kwargs["json"]["text"]


def test_data_quality_notification_does_not_suppress_later_business_alert(services):
    _, fetch, post = services
    fetch.side_effect = [
        None,
        {"date": TARGET, "roas": 1.2, "revenue": 120, "ad_spend": 100},
    ]
    with pytest.raises(RuntimeError, match="unavailable"):
        check_roas_and_alert_flow()
    check_roas_and_alert_flow()
    assert post.call_count == 2
    assert "pipeline failure" in post.call_args_list[0].kwargs["json"]["text"]
    assert "Low ROAS" in post.call_args_list[1].kwargs["json"]["text"]


def test_explicit_date_allows_recovery_after_calendar_rollover(services):
    _, fetch, post = services
    target = date(2026, 9, 1)
    fetch.return_value = {"date": target, "roas": 1.2, "revenue": 120, "ad_spend": 100}
    assert check_roas_and_alert_flow(target_date=target).date == target
    assert fetch.call_args.args[-1] == target
    assert "2026-09-01" in post.call_args.kwargs["json"]["text"]


def test_dbt_failure_does_not_automatically_rebuild():
    import subprocess

    with patch("orchestration.flow.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(1, "dbt")

        @flow
        def build():
            build_dbt()

        with pytest.raises(subprocess.CalledProcessError):
            build()
    run.assert_called_once()


def test_dbt_subprocess_uses_current_environment_and_propagates_failure():
    import subprocess
    import sys

    with patch("orchestration.flow.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(1, "dbt")
        with pytest.raises(subprocess.CalledProcessError):
            build_dbt.fn()
        args, kwargs = run.call_args
        assert args[0] == [sys.executable, "-m", "dbt.cli.main", "build"]
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 1800
