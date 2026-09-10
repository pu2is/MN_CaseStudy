{% test not_greater_than(model, column_name, other_column_name) %}

    select *
    from {{ model }}
    where {{ column_name }} > {{ other_column_name }}

{% endtest %}
