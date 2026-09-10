"""Fetch one daily mart row and classify performance separately from data availability."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as date_cls
from enum import Enum
from typing import Any

from google.cloud import bigquery


class RoasStatus(str, Enum):
    BELOW_THRESHOLD = "below_threshold"
    OK = "ok"
    DATA_UNAVAILABLE = "data_unavailable"
    NO_SPEND = "no_spend"


@dataclass(frozen=True)
class RoasCheckResult:
    date: date_cls
    roas: float | None
    revenue: float | None
    ad_spend: float | None
    threshold: float
    status: RoasStatus


def evaluate_roas(
    row: dict[str, Any] | None, target_date: date_cls, threshold: float
) -> RoasCheckResult:
    """Classify a fct_marketing_performance row against the ROAS threshold.

    Missing or invalid metrics are DATA_UNAVAILABLE. A zero-spend day, or one
    with no Meta data at all (ad_spend is null after the left join), has
    undefined ROAS and is NO_SPEND, not a data-quality failure.
    """
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold must be finite and non-negative")
    row = row or {}
    roas, revenue, ad_spend = (row.get(key) for key in ("roas", "revenue", "ad_spend"))
    revenue_valid = revenue is not None and math.isfinite(revenue) and revenue >= 0
    ad_spend_valid = ad_spend is None or (math.isfinite(ad_spend) and ad_spend >= 0)
    if row.get("date") != target_date or not revenue_valid or not ad_spend_valid:
        status = RoasStatus.DATA_UNAVAILABLE
    elif ad_spend is None or ad_spend == 0:
        status = RoasStatus.NO_SPEND
    elif roas is None or not math.isfinite(roas) or roas < 0:
        status = RoasStatus.DATA_UNAVAILABLE
    else:
        status = RoasStatus.BELOW_THRESHOLD if roas < threshold else RoasStatus.OK
    return RoasCheckResult(
        date=target_date,
        roas=float(roas) if status in (RoasStatus.OK, RoasStatus.BELOW_THRESHOLD) else None,
        revenue=float(revenue) if revenue is not None else None,
        ad_spend=float(ad_spend) if ad_spend is not None else None,
        threshold=threshold,
        status=status,
    )


def fetch_fct_marketing_performance_row(
    client: bigquery.Client,
    project: str,
    dataset: str,
    target_date: date_cls,
) -> dict[str, Any] | None:
    """Fetch the fct_marketing_performance row for a single date, if it exists."""
    query = f"""
        select date, roas, revenue, ad_spend
        from `{project}.{dataset}.fct_marketing_performance`
        where date = @target_date
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
    )
    rows = list(client.query(query, job_config=job_config).result(timeout=120))
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("Expected one marketing performance row per date")
    return dict(rows[0].items())
