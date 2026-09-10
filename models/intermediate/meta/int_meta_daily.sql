with insights as (

    select *
    from {{ ref('stg_meta_insights') }}

),

daily as (

    select
        date,

        -- a row flagged with an invalid negative value is excluded entirely
        -- (not just the negative field) since a bad measurement on one metric
        -- puts the reliability of the whole reported row in question for this
        -- simplified case study
        sum(case when not has_invalid_negative_value then spend else 0 end) as ad_spend,
        sum(case when not has_invalid_negative_value then impressions else 0 end) as impressions,
        sum(case when not has_invalid_negative_value then clicks else 0 end) as clicks

    from insights
    group by date

)

select
    date,
    ad_spend,
    impressions,
    clicks
from daily
order by date
