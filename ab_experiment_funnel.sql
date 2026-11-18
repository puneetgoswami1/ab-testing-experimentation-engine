

WITH raw_exposures AS (
    SELECT 
        user_id,
        experiment_id,
        variant_name, -- 'control' or 'treatment'
        exposed_at,
        page_load_ms,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, experiment_id 
            ORDER BY exposed_at ASC
        ) AS exposure_seq
    FROM product_events.experiment_assignments
    WHERE experiment_id = 'EXP_2026_CHECKOUT_FLOW'
      AND exposed_at >= CURRENT_DATE - INTERVAL '21 DAYS'
),

clean_assignments AS (
    -- Keep first exposure only to prevent cross-variant contamination
    SELECT 
        user_id,
        variant_name,
        exposed_at,
        page_load_ms
    FROM raw_exposures
    WHERE exposure_seq = 1
),

post_exposure_orders AS (
    SELECT 
        a.user_id,
        a.variant_name,
        a.page_load_ms,
        MAX(CASE WHEN o.order_id IS NOT NULL THEN 1 ELSE 0 END) AS did_convert,
        COALESCE(SUM(o.net_revenue_usd), 0.0) AS user_revenue_usd
    FROM clean_assignments a
    LEFT JOIN core_dw.fct_orders o 
        ON a.user_id = o.user_id
       AND o.order_timestamp BETWEEN a.exposed_at AND a.exposed_at + INTERVAL '48 HOURS'
       AND o.order_status = 'COMPLETED'
    GROUP BY a.user_id, a.variant_name, a.page_load_ms
)

SELECT 
    variant_name,
    COUNT(user_id) AS total_users,
    SUM(did_convert) AS converted_users,
    ROUND((SUM(did_convert) * 100.0) / COUNT(user_id), 3) AS conversion_rate_pct,
    ROUND(AVG(user_revenue_usd), 2) AS revenue_per_user_usd,
    ROUND(AVG(CASE WHEN did_convert = 1 THEN user_revenue_usd END), 2) AS avg_order_value_usd,
    -- Guardrail metric: ensure new UI does not degrade checkout speed
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY page_load_ms), 0) AS p95_latency_ms
FROM post_exposure_orders
GROUP BY variant_name
ORDER BY variant_name;