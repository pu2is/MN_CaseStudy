"""Slack webhook formatting and delivery for low-ROAS alerts."""

from __future__ import annotations

import httpx

from orchestration.roas_check import RoasCheckResult


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


def send_slack_alert(webhook_url: str, payload: dict, timeout: float = 10.0) -> None:
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set -- cannot send ROAS alert.")

    response = httpx.post(webhook_url, json=payload, timeout=timeout)
    response.raise_for_status()
