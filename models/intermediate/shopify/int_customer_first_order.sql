-- Requires complete order history: a truncated history overstates new customers.
select
    customer_id,
    min(order_date) as first_order_date
from {{ ref('stg_shopify_orders') }}
where customer_id is not null
group by customer_id
