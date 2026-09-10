-- Grain: one order. An order without an identifiable order_id or created_at
-- cannot be deduplicated or dated and is excluded here -- one bad historical
-- row must not block the daily pipeline from reaching check_yesterday_roas.
-- Conflicting order_id versions keep the most recent by created_at; the mock
-- schema has no separate load timestamp to pick a true "latest" version.
with cleaned as (
    select
        nullif(trim(cast(order_id as string)), '') as order_id,
        nullif(trim(cast(customer_id as string)), '') as customer_id,
        nullif(trim(cast(discount_code as string)), '') as discount_code,
        safe_cast(created_at as timestamp) as created_at,
        -- NUMERIC avoids floating-point accumulation for EUR amounts.
        safe_cast(total_price as numeric) as total_price
    from {{ source('shopify', 'src_shopify_orders') }}
    where nullif(trim(cast(order_id as string)), '') is not null
      and safe_cast(created_at as timestamp) is not null
)

select
    order_id,
    customer_id,
    created_at,
    date(created_at, '{{ var("reporting_timezone") }}') as order_date,
    total_price,
    -- Kept visible rather than dropped: a refund/adjustment could plausibly
    -- produce a negative value. int_shopify_daily excludes it from revenue,
    -- not the order -- see non_negative warn test below.
    coalesce(total_price < 0, true) as total_price_is_invalid,
    discount_code
from cleaned
qualify row_number() over (partition by order_id order by created_at desc) = 1
