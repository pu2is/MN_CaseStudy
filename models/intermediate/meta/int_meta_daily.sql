select
    date,
    -- A row flagged with an invalid negative value is excluded entirely (not
    -- just the negative field), since a bad measurement on one metric puts
    -- the reliability of the whole reported row in question.
    sum(case when not has_invalid_negative_value then spend else 0 end) as ad_spend,
    sum(case when not has_invalid_negative_value then impressions else 0 end) as impressions,
    sum(case when not has_invalid_negative_value then clicks else 0 end) as clicks,
    -- Lets downstream consumers tell a fully valid day apart from one where
    -- some rows were excluded above -- the sums alone can't show that.
    countif(has_invalid_negative_value) as invalid_rows
from {{ ref('stg_meta_insights') }}
group by date
