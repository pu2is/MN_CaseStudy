"""Slack webhook formatting and delivery for low-ROAS alerts."""

from __future__ import annotations

from pathlib import Path

import httpx

from orchestration.delivery import already_sent, mark_sent
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
    """Send once per durable key.

    Return False for a key already confirmed sent. A failed or ambiguous
    attempt is not recorded, so the next run for the same key retries it --
    at most a rare duplicate Slack message on a network hiccup, never a
    silently dropped alert.
    """
    if not webhook_url:
        raise RuntimeError("Slack webhook is not configured; cannot send alert")
    if already_sent(state_path, delivery_key):
        return False
    try:
        response = httpx.post(webhook_url, json=payload, timeout=timeout)
    except httpx.RequestError:
        raise SlackDeliveryError("Slack delivery failed before confirmation") from None
    if response.status_code == 200 and response.text.strip() == "ok":
        mark_sent(state_path, delivery_key)
        return True
    raise SlackDeliveryError(f"Slack delivery failed (HTTP {response.status_code})")
