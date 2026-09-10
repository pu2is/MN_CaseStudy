from datetime import date

from orchestration.roas_check import RoasStatus, evaluate_roas

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
