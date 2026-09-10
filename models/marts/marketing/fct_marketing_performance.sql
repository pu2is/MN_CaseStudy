{{ config(partition_by={"field": "date", "data_type": "date"}) }}

-- Grain: one calendar day. These are blended proxies, without order-to-ad attribution.
with shopify as (
    select * from {{ ref('int_shopify_daily') }}
),
meta as (
    select * from {{ ref('int_meta_daily') }}
),
source_dates as (
    select date from shopify
    union distinct
    select date from meta
),
date_spine as (
    -- Include gaps between observed dates; neither missing source implies zero.
    select date
    from unnest(generate_date_array(
        (select min(date) from source_dates),
        (select max(date) from source_dates)
    )) as date
)

select
    date_spine.date,
    shopify.revenue,
    shopify.orders,
    shopify.new_customers,
    meta.ad_spend,
    meta.impressions,
    meta.clicks,
    -- Zero/unknown spend makes ROAS undefined. CAC is zero for zero spend
    -- with known new customers, and undefined for zero/unknown new customers.
    safe_divide(shopify.revenue, meta.ad_spend) as roas,
    safe_divide(meta.ad_spend, shopify.new_customers) as cac
from date_spine
left join shopify using (date)
left join meta using (date)
