from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import httpx
import pytest

from orchestration.delivery import DeliveryUncertain, database, reconcile, reserve
from orchestration.slack import SlackDeliveryError, send_slack_alert


@pytest.fixture
def send(tmp_path):
    def deliver(key="day:low-roas"):
        return send_slack_alert(
            "https://hooks.slack.com/services/fake",
            {"text": "alert"},
            delivery_key=key,
            state_path=tmp_path / "delivery.sqlite3",
        )

    return deliver


def test_acknowledged_delivery_survives_reopening_database(send):
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        assert send() is True
        assert send() is False
        assert send("next-day:low-roas") is True
    assert post.call_count == 2


@pytest.mark.parametrize("error", [httpx.ReadTimeout("secret"), httpx.WriteError("secret")])
def test_ambiguous_delivery_blocks_retries_and_restarts(send, error):
    with patch("orchestration.slack.httpx.post", side_effect=error) as post:
        with pytest.raises(SlackDeliveryError, match="uncertain"):
            send()
        with pytest.raises(DeliveryUncertain):
            send()
    post.assert_called_once()


def test_crash_after_reservation_blocks_resend(tmp_path, send):
    reserve(tmp_path / "delivery.sqlite3", "day:low-roas")
    with patch("orchestration.slack.httpx.post") as post:
        with pytest.raises(DeliveryUncertain):
            send()
    post.assert_not_called()


def test_concurrent_attempts_only_post_once(send):
    entered, release = Event(), Event()

    def respond(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, text="ok")

    with patch("orchestration.slack.httpx.post", side_effect=respond) as post:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(send)
            assert entered.wait(5)
            try:
                with pytest.raises(DeliveryUncertain):
                    executor.submit(send).result(timeout=5)
            finally:
                release.set()
            assert first.result(timeout=5)
    post.assert_called_once()


@pytest.mark.parametrize("outcome, calls", [("sent", 0), ("not-sent", 1)])
def test_operator_reconciliation(tmp_path, send, outcome, calls):
    path = tmp_path / "delivery.sqlite3"
    reserve(path, "day:low-roas")
    reconcile(path, "day:low-roas", outcome)
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        send()
    assert post.call_count == calls


def test_crash_after_remote_success_before_local_ack(send):
    with patch(
        "orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")
    ) as post:
        with patch("orchestration.slack.finish", side_effect=OSError("disk unavailable")):
            with pytest.raises(OSError):
                send()
        with pytest.raises(DeliveryUncertain):
            send()
    post.assert_called_once()


def test_slack_accepts_post_but_response_is_lost(send):
    accepted_messages = []

    def accepted_then_timeout(*args, **kwargs):
        accepted_messages.append(kwargs["json"])
        raise httpx.ReadTimeout("acknowledgement lost")

    with patch("orchestration.slack.httpx.post", side_effect=accepted_then_timeout):
        with pytest.raises(SlackDeliveryError):
            send()
        with pytest.raises(DeliveryUncertain):
            send()
    assert len(accepted_messages) == 1


def test_corrupt_ledger_fails_closed_without_post(tmp_path, send):
    import sqlite3

    (tmp_path / "delivery.sqlite3").write_bytes(b"corrupt database")
    with patch("orchestration.slack.httpx.post") as post:
        with pytest.raises(sqlite3.DatabaseError):
            send()
    post.assert_not_called()


def test_unknown_ledger_status_never_allows_post(tmp_path, send):
    with database(tmp_path / "delivery.sqlite3") as connection:
        connection.execute(
            "insert into deliveries (delivery_key, status) values ('day:low-roas', 'invalid')"
        )
        connection.commit()
    with patch("orchestration.slack.httpx.post") as post:
        with pytest.raises(DeliveryUncertain):
            send()
    post.assert_not_called()


def test_ledger_does_not_store_payload_or_webhook(tmp_path, send):
    with patch("orchestration.slack.httpx.post", return_value=httpx.Response(200, text="ok")):
        send()
    with database(tmp_path / "delivery.sqlite3") as connection:
        row = connection.execute("select * from deliveries").fetchone()
    assert row[:2] == ("day:low-roas", "sent")
    assert "hooks.slack" not in str(row)
