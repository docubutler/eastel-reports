-- Query 5: Premium and Special Numbers

WITH categories AS (
    SELECT 1 AS sort_order, '1 MOCC - 03-8000 8000' AS call_type
    UNION ALL SELECT 2, '1300 Numbers'
    UNION ALL SELECT 3, '1700 Numbers'
    UNION ALL SELECT 4, '1800 Numbers'
    UNION ALL SELECT 5, 'Directory Assistance -Services 103'
    UNION ALL SELECT 6, 'Emergency Numbers'
    UNION ALL SELECT 7, 'Info Services - 100'
    UNION ALL SELECT 8, 'Info Services - 15454'
    UNION ALL SELECT 9, 'Info Services - 15300'
    UNION ALL SELECT 10, 'Info Services - 15353'
    UNION ALL SELECT 11, 'Info Services - 15404'
    UNION ALL SELECT 12, 'Info Services - 15444'
    UNION ALL SELECT 13, 'Info Services - 15777'
),
aggregated AS (
    SELECT
        CASE
            WHEN t.opposite_number = '600380008000' THEN '1 MOCC - 03-8000 8000'
            WHEN t.opposite_number LIKE '601300%' AND LENGTH(t.opposite_number) < 12 THEN '1300 Numbers'
            WHEN t.opposite_number LIKE '601700%' AND LENGTH(t.opposite_number) < 12 THEN '1700 Numbers'
            WHEN t.opposite_number LIKE '601800%' AND LENGTH(t.opposite_number) < 12 THEN '1800 Numbers'
            WHEN t.opposite_number = '60103' THEN 'Directory Assistance -Services 103'
            WHEN t.opposite_number = '60100' THEN 'Info Services - 100'
            WHEN t.opposite_number = '6015454' THEN 'Info Services - 15454'
            WHEN t.opposite_number = '6015300' THEN 'Info Services - 15300'
            WHEN t.opposite_number = '6015353' THEN 'Info Services - 15353'
            WHEN t.opposite_number = '6015404' THEN 'Info Services - 15404'
            WHEN t.opposite_number = '6015444' THEN 'Info Services - 15444'
            WHEN t.opposite_number = '6015777' THEN 'Info Services - 15777'
            ELSE NULL
        END AS call_type,
        COUNT(*)::numeric AS no_of_calls,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 60.0, 2) AS mou
    FROM {{request_log_table}} t
    WHERE t.rat_type = 'VO'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND (
          t.opposite_number = '600380008000'
          OR t.opposite_number = '60103'
          OR t.opposite_number = '60100'
          OR t.opposite_number = '6015454'
          OR t.opposite_number = '6015300'
          OR t.opposite_number = '6015353'
          OR t.opposite_number = '6015404'
          OR t.opposite_number = '6015444'
          OR t.opposite_number = '6015777'
          OR (t.opposite_number LIKE '601300%' AND LENGTH(t.opposite_number) < 12)
          OR (t.opposite_number LIKE '601700%' AND LENGTH(t.opposite_number) < 12)
          OR (t.opposite_number LIKE '601800%' AND LENGTH(t.opposite_number) < 12)
      )
    GROUP BY 1
)
SELECT
    'Voice' AS service_type,
    'Premium and Special Numbers' AS charge_type,
    c.call_type,
    a.no_of_calls,
    a.mou
FROM categories c
LEFT JOIN aggregated a
    ON a.call_type = c.call_type
ORDER BY c.sort_order;
