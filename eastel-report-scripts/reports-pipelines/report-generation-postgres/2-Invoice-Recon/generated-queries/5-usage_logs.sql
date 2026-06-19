-- Query 5: Premium and Special Numbers (usage_logs version)

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
    UNION ALL SELECT 14, 'Info Services - 15555'
    UNION ALL SELECT 15, 'Info Services - 15999'
    UNION ALL SELECT 16, 'Info Services - 13504'
    UNION ALL SELECT 17, 'Info Services - 15511'
    UNION ALL SELECT 18, 'Info Services - 15800'
    UNION ALL SELECT 19, 'Info Services - 15995'
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
            WHEN t.opposite_number = '6015555' THEN 'Info Services - 15555'
            WHEN t.opposite_number = '6015999' THEN 'Info Services - 15999'
            WHEN t.opposite_number = '6013504' THEN 'Info Services - 13504'
            WHEN t.opposite_number = '6015511' THEN 'Info Services - 15511'
            WHEN t.opposite_number = '6015800' THEN 'Info Services - 15800'
            WHEN t.opposite_number = '6015995' THEN 'Info Services - 15995'
            ELSE NULL
        END AS call_type,
        COUNT(*)::numeric AS no_of_calls,
        ROUND(COALESCE(SUM(t.act_usage_unit), 0) / 60.0, 2) AS mou
    FROM {{usage_log_table}} t
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
      AND t.usage_start_time >= '{{start_date}}'
      AND t.usage_start_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND t.act_usage_unit > 0
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
          OR t.opposite_number = '6015555'
          OR t.opposite_number = '6015999'
          OR t.opposite_number = '6013504'
          OR t.opposite_number = '6015511'
          OR t.opposite_number = '6015800'
          OR t.opposite_number = '6015995'
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
