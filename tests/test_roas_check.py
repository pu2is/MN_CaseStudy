from datetime import date
from unittest.mock import MagicMock

import pytest

from orchestration.roas_check import RoasStatus, evaluate_roas, fetch_fct_marketing_performance_row

TARGET_DATE = date(2026, 9, 9)
THRESHOLD = 1.5


def test_roas_below_threshold_is_flagged():
    row = {"date": TARGET_DATE, "roas": 1.2, "revenue": 1200.0, "ad_spend": 1000.0}

    result = evaluate_roas(row, TARGET_DATE, THRESHOLD)

    assert result.status is RoasStatus.BELOW_THRESHOLD
    assert result.roas == 1.2


def test_roas_at_or_above_threshold_is_ok():
    row = {"date": TARGET_DATE, "roas": 1.8, "revenue": 1800.0, "ad_spend": 1000.0}

    result = evaluate_roas(row, TARGET_DATE, THRESHOLD)

    assert result.status is RoasStatus.OK
    assert result.roas == 1.8


def test_null_roas_is_data_unavailable_not_a_low_roas():
    row = {"date": TARGET_DATE, "roas": None, "revenue": 0.0, "ad_spend": 500.0}

    result = evaluate_roas(row, TARGET_DATE, THRESHOLD)

    assert result.status is RoasStatus.DATA_UNAVAILABLE
    assert result.roas is None


def test_missing_row_is_data_unavailable():
    result = evaluate_roas(None, TARGET_DATE, THRESHOLD)

    assert result.status is RoasStatus.DATA_UNAVAILABLE
    assert result.date == TARGET_DATE
    assert result.roas is None
    assert result.revenue is None
    assert result.ad_spend is None


def test_roas_exactly_at_threshold_is_ok_not_below():
    row = {"date": TARGET_DATE, "roas": 1.5, "revenue": 1500.0, "ad_spend": 1000.0}

    result = evaluate_roas(row, TARGET_DATE, THRESHOLD)

    assert result.status is RoasStatus.OK


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_roas_is_unavailable(value):
    row = {"date": TARGET_DATE, "roas": value, "revenue": 100, "ad_spend": 100}
    assert evaluate_roas(row, TARGET_DATE, THRESHOLD).status is RoasStatus.DATA_UNAVAILABLE


def test_query_parameterizes_date_and_rejects_duplicate_days():
    client = MagicMock()
    client.query.return_value.result.return_value = [{"roas": 1}, {"roas": 2}]
    with pytest.raises(ValueError, match="one marketing performance row"):
        fetch_fct_marketing_performance_row(client, "project", "dataset", TARGET_DATE)
    args, kwargs = client.query.call_args
    assert "where date = @target_date" in args[0]
    assert kwargs["job_config"].query_parameters[0].value == TARGET_DATE


def test_wrong_day_is_unavailable():
    row = {"date": date(2026, 9, 8), "roas": 1, "revenue": 100, "ad_spend": 100}
    assert evaluate_roas(row, TARGET_DATE, THRESHOLD).status is RoasStatus.DATA_UNAVAILABLE
