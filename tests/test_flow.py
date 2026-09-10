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

from orchestration.flow import check_roas_and_alert_flow
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
