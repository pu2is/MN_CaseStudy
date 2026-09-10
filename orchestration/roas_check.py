"""Query yesterday's fct_marketing_performance row and classify it against the
ROAS alert threshold.

The classification logic (evaluate_roas) is pure and independent of BigQuery so
it can be unit tested directly against the three cases the business cares
about: below threshold, at/above threshold, and unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from enum import Enum
from typing import Any

from google.cloud import bigquery


class RoasStatus(str, Enum):
    BELOW_THRESHOLD = "below_threshold"
    OK = "ok"
    DATA_UNAVAILABLE = "data_unavailable"


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

    A missing row and a row with a null roas are both DATA_UNAVAILABLE --
    treated as a data-quality problem, never as a (misleadingly) low ROAS.
    """
    if row is None or row.get("roas") is None:
        revenue = row.get("revenue") if row else None
        ad_spend = row.get("ad_spend") if row else None
        return RoasCheckResult(
            date=target_date,
            roas=None,
            revenue=revenue,
            ad_spend=ad_spend,
            threshold=threshold,
            status=RoasStatus.DATA_UNAVAILABLE,
        )

    roas = row["roas"]
    status = RoasStatus.BELOW_THRESHOLD if roas < threshold else RoasStatus.OK
    return RoasCheckResult(
        date=target_date,
        roas=roas,
        revenue=row.get("revenue"),
        ad_spend=row.get("ad_spend"),
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
        query_parameters=[
            bigquery.ScalarQueryParameter("target_date", "DATE", target_date)
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    if not rows:
        return None
    return dict(rows[0].items())
