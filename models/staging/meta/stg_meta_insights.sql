-- Grain: one campaign per date. A row without a date or campaign_id cannot be
-- placed at this grain and is excluded -- one bad historical row must not
-- block the daily pipeline from reaching check_yesterday_roas. Conflicting
-- (date, campaign_id) snapshots keep the version with the highest reported
-- spend, on the assumption that duplicates come from partial/retried API
-- pages rather than two genuinely different facts.
with cleaned as (
    select
        -- The Meta account must use REPORTING_TIMEZONE. A daily date alone
        -- cannot be rebucketed to another timezone; request finer-grained
        -- data if it differs.
        safe_cast(date as date) as date,
        nullif(trim(cast(campaign_id as string)), '') as campaign_id,
        safe_cast(spend as numeric) as spend,
        safe_cast(impressions as int64) as impressions,
        safe_cast(clicks as int64) as clicks
    from {{ source('meta', 'src_meta_insights') }}
    where safe_cast(date as date) is not null
      and nullif(trim(cast(campaign_id as string)), '') is not null
)

select
    date,
    campaign_id,
    spend,
    impressions,
    clicks,
    -- A bad measurement on one field puts the whole reported row in question;
    -- int_meta_daily excludes all three metrics for such a row.
    coalesce(spend < 0, true)
        or coalesce(impressions < 0, true)
        or coalesce(clicks < 0, true) as has_invalid_negative_value
from cleaned
qualify row_number() over (
    partition by date, campaign_id
    order by spend desc nulls last, impressions desc nulls last, clicks desc nulls last
) = 1
