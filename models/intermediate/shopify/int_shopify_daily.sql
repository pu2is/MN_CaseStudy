select
    orders.order_date as date,
    sum(orders.total_price) as revenue,
    count(*) as orders,
    -- Multiple first-day orders still represent one new customer.
    count(distinct case
        when orders.order_date = first_order.first_order_date then orders.customer_id
    end) as new_customers
from {{ ref('stg_shopify_orders') }} as orders
left join {{ ref('int_customer_first_order') }} as first_order
    on orders.customer_id = first_order.customer_id
group by orders.order_date
