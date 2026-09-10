"""Slack webhook formatting and delivery for low-ROAS alerts."""

from __future__ import annotations

from pathlib import Path

import httpx

from orchestration.delivery import finish, reserve
from orchestration.roas_check import RoasCheckResult


class SlackDeliveryError(RuntimeError):
    """Delivery error without the secret webhook URL in its message."""


def build_slack_payload(result: RoasCheckResult) -> dict:
    """Build a Slack incoming-webhook payload for a below-threshold ROAS result.

    Only meaningful for RoasStatus.BELOW_THRESHOLD -- callers decide whether to
    send an alert at all; this just formats one.
    """
    revenue = f"EUR {result.revenue:,.2f}" if result.revenue is not None else "unknown"
    ad_spend = f"EUR {result.ad_spend:,.2f}" if result.ad_spend is not None else "unknown"

    text = (
        f":rotating_light: *Low ROAS alert -- {result.date}*\n"
        f"ROAS: *{result.roas:.2f}* (threshold: {result.threshold:.2f})\n"
        f"Revenue: {revenue}\n"
        f"Ad spend: {ad_spend}\n"
        f"_Simplified blended metric -- see fct_marketing_performance docs._"
    )
    return {"text": text}


def send_slack_alert(
    webhook_url: str,
    payload: dict,
    *,
    delivery_key: str,
    state_path: Path,
    timeout: float = 10.0,
) -> bool:
    """Send once per durable key; ambiguous outcomes require operator reconciliation.

    Return False for an already acknowledged delivery. No automatic HTTP retries.
    """
    if not webhook_url:
        raise RuntimeError("Slack webhook is not configured; cannot send alert")
    if not reserve(state_path, delivery_key):
        return False
    try:
        response = httpx.post(webhook_url, json=payload, timeout=timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        finish(state_path, delivery_key, "failed")
        raise SlackDeliveryError("Slack connection failed before sending") from None
    except httpx.RequestError:
        finish(state_path, delivery_key, "uncertain")
        raise SlackDeliveryError(
            "Slack delivery outcome uncertain; reconcile before resending"
        ) from None
    # Only Slack's explicit acknowledgement establishes delivery. A 5xx or an
    # unexpected response can follow a committed side effect, so do not resend.
    if response.status_code == 200 and response.text.strip() == "ok":
        finish(state_path, delivery_key, "sent")
        return True
    rejected = response.status_code in (400, 403, 404, 410, 429)
    finish(state_path, delivery_key, "failed" if rejected else "uncertain")
    raise SlackDeliveryError(
        f"Slack delivery failed (HTTP {response.status_code}); "
        + ("request rejected" if rejected else "outcome uncertain; reconcile before resending"),
    )
