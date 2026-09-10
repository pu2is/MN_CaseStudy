-- Grain: one campaign per date. Exact duplicates are safe to remove;
-- conflicting snapshots fail uniqueness rather than assuming max(spend) is latest.
select distinct
    -- The Meta account must use REPORTING_TIMEZONE. A daily date alone cannot
    -- be rebucketed to another timezone; request finer-grained data if it differs.
    safe_cast(date as date) as date,
    nullif(trim(cast(campaign_id as string)), '') as campaign_id,
    safe_cast(spend as numeric) as spend,
    safe_cast(impressions as int64) as impressions,
    safe_cast(clicks as int64) as clicks
from {{ source('meta', 'src_meta_insights') }}
