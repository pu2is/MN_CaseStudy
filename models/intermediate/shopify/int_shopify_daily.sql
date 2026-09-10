with orders as (

    select *
    from {{ ref('stg_shopify_orders') }}

),

first_order as (

    select *
    from {{ ref('int_customer_first_order') }}

),

orders_enriched as (

    select
        orders.order_id,
        orders.customer_id,
        orders.order_date,
        orders.total_price,
        orders.total_price_is_invalid,
        first_order.first_order_date

    from orders
    left join first_order
        on orders.customer_id = first_order.customer_id

),

daily as (

    select
        order_date as date,

        -- orders flagged with an invalid (negative) total_price are excluded
        -- from revenue -- a negative price is treated as a data-quality issue
        -- in this mock data, not a legitimate refund/credit, so it is kept out
        -- of the sum rather than allowed to silently reduce daily revenue
        sum(case when not total_price_is_invalid then total_price else 0 end) as revenue,

        -- every order counts here regardless of total_price validity: the
        -- order itself happened, only its price is in question
        count(order_id) as orders,

        -- a customer is "new" on the date that matches their first known
        -- order date; count(distinct ...) with a null-producing case
        -- naturally excludes orders that aren't that customer's first
        count(distinct case
            when order_date = first_order_date then customer_id
        end) as new_customers

    from orders_enriched
    group by order_date

)

select
    date,
    revenue,
    orders,
    new_customers
from daily
order by date
