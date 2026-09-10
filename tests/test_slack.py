from datetime import date
from unittest.mock import patch

import httpx
import pytest

from orchestration.roas_check import RoasCheckResult, RoasStatus
from orchestration.slack import SlackDeliveryError, build_slack_payload, send_slack_alert

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


@pytest.fixture
def send(tmp_path):
    def deliver(url="https://hooks.slack.com/services/fake"):
        return send_slack_alert(
            url, {"text": "hi"}, delivery_key="test", state_path=tmp_path / "alerts.sqlite3"
        )

    return deliver


def test_send_posts_payload_and_timeout(send):
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        send()
    assert post.call_args.kwargs["json"] == {"text": "hi"}
    assert post.call_args.kwargs["timeout"] == 10


def test_missing_webhook_does_not_reserve_delivery(send):
    with pytest.raises(RuntimeError, match="configured"):
        send("")
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        send()
    post.assert_called_once()


@pytest.mark.parametrize("status", [400, 403, 429, 500])
def test_rejected_or_unexpected_responses_allow_later_manual_rerun(send, status):
    with patch("orchestration.slack.httpx.post", return_value=httpx.Response(status)):
        with pytest.raises(SlackDeliveryError, match=f"HTTP {status}") as error:
            send()
    assert "hooks.slack.com" not in str(error.value)
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        send()
    post.assert_called_once()


def test_unexpected_200_body_is_not_recorded_as_sent(send):
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="unexpected")
    ):
        with pytest.raises(SlackDeliveryError, match="HTTP 200"):
            send()
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        send()
    post.assert_called_once()


def test_connection_failure_before_sending_allows_later_rerun(send):
    with patch("orchestration.slack.httpx.post", side_effect=httpx.ConnectError("secret-url")):
        with pytest.raises(SlackDeliveryError) as error:
            send()
    assert "secret-url" not in str(error.value)
    with patch("orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")):
        assert send()


def test_ambiguous_timeout_does_not_block_the_next_run(send):
    """A response lost to a timeout is not distinguished from any other
    failure -- the key is simply retried next run, at the cost of a rare
    duplicate Slack message rather than a silently dropped alert."""
    with patch("orchestration.slack.httpx.post", side_effect=httpx.ReadTimeout("response lost")):
        with pytest.raises(SlackDeliveryError):
            send()
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        assert send() is True
    post.assert_called_once()
