from unittest.mock import patch

import httpx
import pytest

from orchestration.delivery import already_sent, database, mark_sent
from orchestration.slack import SlackDeliveryError, send_slack_alert


def deliver(tmp_path, key="day:low-roas"):
    return send_slack_alert(
        "https://hooks.slack.com/services/fake",
        {"text": "alert"},
        delivery_key=key,
        state_path=tmp_path / "delivery.sqlite3",
    )


def test_acknowledged_delivery_survives_reopening_database(tmp_path):
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        assert deliver(tmp_path) is True
        assert deliver(tmp_path) is False
        assert deliver(tmp_path, "next-day:low-roas") is True
    assert post.call_count == 2


def test_failed_delivery_is_not_marked_sent_and_may_be_retried(tmp_path):
    path = tmp_path / "delivery.sqlite3"
    with patch("orchestration.slack.httpx.post", side_effect=httpx.ReadTimeout("secret")):
        with pytest.raises(SlackDeliveryError):
            deliver(tmp_path)
    assert already_sent(path, "day:low-roas") is False


def test_mark_sent_is_idempotent(tmp_path):
    path = tmp_path / "delivery.sqlite3"
    mark_sent(path, "day:low-roas")
    mark_sent(path, "day:low-roas")
    assert already_sent(path, "day:low-roas") is True


def test_ledger_does_not_store_payload_or_webhook(tmp_path):
    path = tmp_path / "delivery.sqlite3"
    with patch("orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")):
        deliver(tmp_path)
    with database(path) as connection:
        row = connection.execute("select * from sent_deliveries").fetchone()
    assert row[0] == "day:low-roas"
    assert "hooks.slack" not in str(row)
