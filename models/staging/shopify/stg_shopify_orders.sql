-- Grain: one order. Remove exact duplicates; conflicting versions fail unique.
-- The mock schema has no updated_at/load timestamp to select a latest version.
with cleaned as (
    select
        nullif(trim(cast(order_id as string)), '') as order_id,
        nullif(trim(cast(customer_id as string)), '') as customer_id,
        nullif(trim(cast(discount_code as string)), '') as discount_code,
        safe_cast(created_at as timestamp) as created_at,
        -- NUMERIC avoids floating-point accumulation for EUR amounts.
        safe_cast(total_price as numeric) as total_price
    from {{ source('shopify', 'src_shopify_orders') }}
)

select distinct
    order_id,
    customer_id,
    created_at,
    date(created_at, '{{ var("reporting_timezone") }}') as order_date,
    total_price,
    discount_code
from cleaned
-- Keep invalid records visible to dbt tests instead of silently losing revenue.
