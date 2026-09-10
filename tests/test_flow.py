"""Acceptance tests for the ROAS check -> Slack alert flow.

Covers the three cases from Issue 06's verification checklist: ROAS below
threshold (alert), ROAS at/above threshold (no alert), and ROAS unavailable
(no alert, since missing data is a data-quality issue, not a low-ROAS one).
The HTTP call to Slack is mocked -- no real network traffic.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from prefect.testing.utilities import prefect_test_harness

from orchestration.flow import (
    check_roas_and_alert_flow,
    send_roas_alert,
    validate_slack_webhook_url,
)
from orchestration.roas_check import RoasStatus


@pytest.fixture(autouse=True, scope="module")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@pytest.fixture(autouse=True)
def skip_dbt_steps():
    with (
        patch("orchestration.flow.run_dbt", MagicMock()),
        patch("orchestration.flow.run_dbt_tests", MagicMock()),
    ):
        yield


def _row_for(roas):
    return {"date": date(2026, 9, 9), "roas": roas, "revenue": 1200.0, "ad_spend": 1000.0}


@patch("orchestration.slack.httpx.post")
@patch("orchestration.flow.bigquery.Client")
@patch("orchestration.flow.fetch_fct_marketing_performance_row")
def test_roas_below_threshold_sends_slack_alert(
    mock_fetch, mock_client, mock_post, monkeypatch
):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/fake")
    mock_fetch.return_value = _row_for(1.2)
    mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

    result = check_roas_and_alert_flow()

    assert result.status is RoasStatus.BELOW_THRESHOLD
    mock_post.assert_called_once()


@patch("orchestration.slack.httpx.post")
@patch("orchestration.flow.bigquery.Client")
@patch("orchestration.flow.fetch_fct_marketing_performance_row")
def test_roas_above_threshold_sends_no_alert(mock_fetch, mock_client, mock_post):
    mock_fetch.return_value = _row_for(1.8)

    result = check_roas_and_alert_flow()

    assert result.status is RoasStatus.OK
    mock_post.assert_not_called()


@patch("orchestration.slack.httpx.post")
@patch("orchestration.flow.bigquery.Client")
@patch("orchestration.flow.fetch_fct_marketing_performance_row")
def test_null_roas_sends_no_misleading_alert(mock_fetch, mock_client, mock_post):
    mock_fetch.return_value = _row_for(None)

    result = check_roas_and_alert_flow()

    assert result.status is RoasStatus.DATA_UNAVAILABLE
    mock_post.assert_not_called()


@patch("orchestration.slack.httpx.post")
@patch("orchestration.flow.bigquery.Client")
@patch("orchestration.flow.fetch_fct_marketing_performance_row")
def test_missing_slack_webhook_fails_flow_immediately(
    mock_fetch, mock_client, mock_post, monkeypatch
):
    """Issue 12, case 1: a missing SLACK_WEBHOOK_URL is a permanent
    configuration error -- it must fail the flow immediately, without going
    through send_roas_alert's retried HTTP call at all."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    mock_fetch.return_value = _row_for(1.2)

    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        check_roas_and_alert_flow()

    mock_post.assert_not_called()


def test_validate_slack_webhook_url_task_has_no_retries():
    """Issue 12: configuration validation must not be retried -- retrying a
    permanent error only delays the inevitable failure."""
    assert validate_slack_webhook_url.retries == 0


def test_send_roas_alert_task_keeps_retries_for_transient_failures():
    """Issue 12, case 2: once configuration is valid, transient HTTP/network
    failures sending to Slack must still be retried."""
    assert send_roas_alert.retries == 3
