with orders as (

    select *
    from {{ ref('stg_shopify_orders') }}

),

first_order as (

    select
        customer_id,
        min(order_date) as first_order_date

    from orders
    -- an order without a customer_id cannot be attributed to any customer's
    -- history and is excluded from this model
    where customer_id is not null
    group by customer_id

)

-- Assumption: the Shopify order history available to this model reaches far
-- enough back to contain every customer's actual first order. If history
-- were truncated (e.g. only the last N months loaded), a returning
-- customer's earliest visible order here could be misclassified as their
-- first order, inflating new_customers in downstream models.
select
    customer_id,
    first_order_date
from first_order
