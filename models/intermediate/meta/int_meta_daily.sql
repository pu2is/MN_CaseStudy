select
    date,
    sum(spend) as ad_spend,
    sum(impressions) as impressions,
    sum(clicks) as clicks
from {{ ref('stg_meta_insights') }}
group by date
