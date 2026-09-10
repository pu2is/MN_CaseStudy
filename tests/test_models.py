"""Execute the repository SQL against local fixtures via SQLGlot and DuckDB.

This checks business results without credentials. It does not replace a native
BigQuery dbt build (adapter behavior, permissions and materializations differ).
"""

from datetime import date
from pathlib import Path

import duckdb
import pytest
import sqlglot
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
MODEL_ORDER = [
    "stg_shopify_orders",
    "stg_meta_insights",
    "int_customer_first_order",
    "int_shopify_daily",
    "int_meta_daily",
    "fct_marketing_performance",
]


def execute_models(connection):
    environment = Environment(undefined=StrictUndefined)
    for name in MODEL_ORDER:
        path = next((ROOT / "models").rglob(f"{name}.sql"))
        rendered = environment.from_string(path.read_text(encoding="utf-8")).render(
            ref=lambda name: name,
            source=lambda source, table: table,
            var=lambda name: "Europe/Berlin",
            config=lambda **kwargs: "",
        )
        query = sqlglot.transpile(rendered, read="bigquery", write="duckdb")[0]
        connection.execute(f"create or replace table {name} as {query}")


@pytest.fixture
def warehouse():
    with duckdb.connect() as connection:
        connection.execute("""
            create table src_shopify_orders (
                order_id varchar, created_at varchar, total_price double,
                customer_id varchar, discount_code varchar
            );
            create table src_meta_insights (
                date varchar, campaign_id varchar, spend double,
                impressions bigint, clicks bigint
            );
        """)
        yield connection


def test_daily_metrics_deduplication_and_new_customers(warehouse):
    warehouse.execute("""
        insert into src_shopify_orders values
        ('old', '2026-09-01 12:00:00+00', 10, 'returning', null),
        ('1', '2026-09-08 23:30:00+00', 100, 'new', '  SALE  '),
        ('1', '2026-09-08 23:30:00+00', 100, 'new', '  SALE  '),
        ('2', '2026-09-09 12:00:00+00', 50, 'new', null),
        ('3', '2026-09-09 12:00:00+00', 100, 'returning', null),
        ('4', '2026-09-09 12:00:00+00', 50, '  ', null);
        insert into src_meta_insights values
        ('2026-09-09', 'a', 80, 800, 8),
        ('2026-09-09', 'a', 80, 800, 8),
        ('2026-09-09', 'b', 20, 200, 2);
    """)
    execute_models(warehouse)
    row = warehouse.execute("""
        select revenue, orders, new_customers, ad_spend, impressions, clicks, roas, cac
        from fct_marketing_performance where date = '2026-09-09'
    """).fetchone()
    assert row == (300, 4, 1, 100, 1000, 10, 3, 100)
    assert warehouse.execute(
        "select discount_code from stg_shopify_orders where order_id='1'"
    ).fetchone() == ("SALE",)


def test_missing_sources_calendar_gaps_and_zero_denominators(warehouse):
    warehouse.execute("""
        insert into src_shopify_orders values
        ('1', '2026-09-01 12:00:00+00', 100, 'c', null),
        ('2', '2026-09-03 12:00:00+00', 100, 'c', null),
        ('3', '2026-09-04 12:00:00+00', 0, 'd', null),
        ('4', '2026-09-05 12:00:00+00', 100, 'e', null);
        insert into src_meta_insights values
        ('2026-09-01', 'a', 0, 0, 0),
        ('2026-09-03', 'a', 50, 100, 10),
        ('2026-09-04', 'a', 20, 100, 10),
        ('2026-09-06', 'a', 50, 100, 10);
    """)
    execute_models(warehouse)
    rows = warehouse.execute(
        "select date, roas, cac from fct_marketing_performance order by date"
    ).fetchall()
    assert rows == [
        (date(2026, 9, 1), None, 0),
        (date(2026, 9, 2), None, None),
        (date(2026, 9, 3), 2, None),
        (date(2026, 9, 4), 0, 20),
        (date(2026, 9, 5), None, None),
        (date(2026, 9, 6), None, None),
    ]


def test_conflicting_versions_remain_visible_to_uniqueness_tests(warehouse):
    warehouse.execute("""
        insert into src_shopify_orders values
        ('1', '2026-09-01 12:00:00+00', 100, 'c', null),
        ('1', '2026-09-01 12:00:00+00', 80, 'c', null);
        insert into src_meta_insights values
        ('2026-09-01', 'a', 50, 100, 10),
        ('2026-09-01', 'a', 40, 100, 10);
    """)
    execute_models(warehouse)
    for model in ("stg_shopify_orders", "stg_meta_insights"):
        assert warehouse.execute(f"select count(*) from {model}").fetchone() == (2,)


@pytest.mark.parametrize("amount", [None, -1, float("nan"), float("inf")])
def test_invalid_amounts_are_not_silently_dropped_or_zeroed(warehouse, amount):
    warehouse.execute(
        "insert into src_shopify_orders values ('1', '2026-09-01', ?, 'c', null)",
        [amount],
    )
    execute_models(warehouse)
    value = warehouse.execute("select total_price from stg_shopify_orders").fetchone()[0]
    assert value is None or value < 0  # not_null/non_negative must reject this row.


def test_empty_sources_produce_no_fabricated_metrics(warehouse):
    execute_models(warehouse)
    assert warehouse.execute("select count(*) from fct_marketing_performance").fetchone() == (0,)
