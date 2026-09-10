-- Grain: 1 row per calendar date.
--
-- Business limitation: the mock Shopify and Meta datasets contain no
-- attribution key linking an order to the campaign that drove it. roas and
-- cac here are therefore simplified BLENDED metrics -- daily Shopify revenue
-- against daily Meta spend, and daily Meta spend against all new Shopify
-- customers that day -- not true Meta-attributed ROAS/CAC. They must not be
-- presented as campaign-level attribution.

with shopify as (

    select *
    from {{ ref('int_shopify_daily') }}

),

meta as (

    select *
    from {{ ref('int_meta_daily') }}

),

-- the date spine is the union of dates either source reports, so a date with
-- only Shopify or only Meta data still gets a row instead of being dropped by
-- an inner join
date_spine as (

    select date from shopify
    union distinct
    select date from meta

),

joined as (

    select
        date_spine.date,
        shopify.revenue,
        shopify.orders,
        shopify.new_customers,
        meta.ad_spend,
        meta.impressions,
        meta.clicks

    from date_spine
    left join shopify using (date)
    left join meta using (date)

)

select
    date,
    revenue,
    orders,
    new_customers,
    ad_spend,
    impressions,
    clicks,

    -- safe_divide returns NULL (not 0) whenever the denominator is 0 or NULL,
    -- so a day with no ad spend or no Meta data reports an undefined roas/cac
    -- instead of a misleading 0 -- see the file header for the blended-metric
    -- limitation these ratios carry
    safe_divide(revenue, ad_spend) as roas,
    safe_divide(ad_spend, new_customers) as cac

from joined
order by date
