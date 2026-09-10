with source as (

    select *
    from {{ source('meta', 'src_meta_insights') }}

),

renamed as (

    select
        safe_cast(date as date) as date,
        nullif(cast(campaign_id as string), '') as campaign_id,
        safe_cast(spend as float64) as spend_raw,
        safe_cast(impressions as int64) as impressions_raw,
        safe_cast(clicks as int64) as clicks_raw

    from source

),

cleaned as (

    select
        date,
        campaign_id,

        -- staging keeps the original values even when they look invalid (e.g.
        -- negative spend/impressions/clicks); has_invalid_negative_value flags
        -- it so downstream models can decide whether to exclude it, without
        -- staging silently discarding what the source actually sent. Zero is
        -- a legitimate value (e.g. a paused campaign) and is never flagged.
        spend_raw as spend,
        impressions_raw as impressions,
        clicks_raw as clicks,

        coalesce(spend_raw < 0, false)
            or coalesce(impressions_raw < 0, false)
            or coalesce(clicks_raw < 0, false) as has_invalid_negative_value

    from renamed
    -- a row without a date or a campaign cannot be placed at this model's
    -- grain and is not usable by any downstream model
    where date is not null
      and campaign_id is not null

),

deduplicated as (

    select *
    from cleaned
    -- keep one row per (date, campaign_id); ties broken by the most complete
    -- record (highest reported spend), on the assumption that duplicates come
    -- from partial/retried API pages rather than two genuinely different facts
    qualify row_number() over (
        partition by date, campaign_id
        order by spend desc nulls last, impressions desc nulls last, clicks desc nulls last
    ) = 1

)

select
    date,
    campaign_id,
    spend,
    impressions,
    clicks,
    has_invalid_negative_value
from deduplicated
