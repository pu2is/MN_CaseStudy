with source as (

    select *
    from {{ source('shopify', 'src_shopify_orders') }}

),

renamed as (

    select
        -- ids and codes arrive as strings from the API; treat blank strings as null
        nullif(cast(order_id as string), '') as order_id,
        nullif(cast(customer_id as string), '') as customer_id,
        nullif(cast(discount_code as string), '') as discount_code,

        -- Assumption: created_at arrives already normalized to UTC by the
        -- ingestion tool.
        safe_cast(created_at as timestamp) as created_at,

        safe_cast(total_price as float64) as total_price_raw

    from source

),

cleaned as (

    select
        order_id,
        customer_id,
        discount_code,
        created_at,

        -- Calendar date in the shared reporting timezone (see the
        -- `reporting_timezone` var in dbt_project.yml and
        -- orchestration/settings.py's REPORTING_TIMEZONE), not implicit UTC,
        -- so order_date, the Prefect alert's "yesterday", and Meta's
        -- reporting date (see stg_meta_insights.sql) all agree on which
        -- business day an event belongs to. If the real Meta ad account uses
        -- a different timezone in production, its dates must be normalized
        -- to this same reporting_timezone before joining.
        date(created_at, '{{ var("reporting_timezone") }}') as order_date,

        -- staging keeps the original value even when it looks invalid (e.g. a
        -- negative total_price); total_price_is_invalid flags it so downstream
        -- models can decide whether to exclude it, without staging silently
        -- discarding what the source actually sent
        total_price_raw as total_price,
        total_price_raw < 0 as total_price_is_invalid

    from renamed
    -- an order that cannot be identified or dated is not usable by any
    -- downstream model and cannot be deduplicated below
    where order_id is not null
      and created_at is not null

),

deduplicated as (

    select *
    from cleaned
    -- keep one row per order_id; ties broken by the latest created_at seen,
    -- on the assumption that duplicates come from re-ingested/retried loads
    qualify row_number() over (
        partition by order_id
        order by created_at desc
    ) = 1

)

select
    order_id,
    customer_id,
    created_at,
    order_date,
    total_price,
    total_price_is_invalid,
    discount_code
from deduplicated
