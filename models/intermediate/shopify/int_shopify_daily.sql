select
    orders.order_date as date,
    -- Orders flagged with an invalid (negative or unknown) total_price are
    -- excluded from revenue; the order itself still counts below.
    sum(case when not orders.total_price_is_invalid then orders.total_price else 0 end) as revenue,
    -- Lets downstream consumers tell a fully valid day apart from one where
    -- some orders were excluded from revenue above.
    countif(orders.total_price_is_invalid) as invalid_revenue_rows,
    count(*) as orders,
    -- Multiple first-day orders still represent one new customer.
    count(distinct case
        when orders.order_date = first_order.first_order_date then orders.customer_id
    end) as new_customers
from {{ ref('stg_shopify_orders') }} as orders
left join {{ ref('int_customer_first_order') }} as first_order
    on orders.customer_id = first_order.customer_id
group by orders.order_date
