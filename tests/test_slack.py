from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

from orchestration.roas_check import RoasCheckResult, RoasStatus
from orchestration.slack import build_slack_payload, send_slack_alert

RESULT = RoasCheckResult(
    date=date(2026, 9, 9),
    roas=1.2,
    revenue=1200.0,
    ad_spend=1000.0,
    threshold=1.5,
    status=RoasStatus.BELOW_THRESHOLD,
)


def test_slack_payload_contains_expected_context_fields():
    payload = build_slack_payload(RESULT)
    text = payload["text"]

    assert "2026-09-09" in text
    assert "1.20" in text  # roas
    assert "1.50" in text  # threshold
    assert "1,200.00" in text  # revenue
    assert "1,000.00" in text  # ad spend


@patch("orchestration.slack.httpx.post")
def test_send_slack_alert_posts_payload_to_webhook_url(mock_post):
    mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

    send_slack_alert("https://hooks.slack.com/services/fake", {"text": "hi"})

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://hooks.slack.com/services/fake"
    assert kwargs["json"] == {"text": "hi"}


@patch("orchestration.slack.httpx.post")
def test_send_slack_alert_raises_on_webhook_error(mock_post):
    response = MagicMock(status_code=500)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=response
    )
    mock_post.return_value = response

    with pytest.raises(httpx.HTTPStatusError):
        send_slack_alert("https://hooks.slack.com/services/fake", {"text": "hi"})


def test_send_slack_alert_requires_webhook_url():
    with pytest.raises(RuntimeError):
        send_slack_alert("", {"text": "hi"})
