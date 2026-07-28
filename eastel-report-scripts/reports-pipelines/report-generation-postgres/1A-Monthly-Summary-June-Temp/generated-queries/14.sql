-- Query 14: Premium or Special Numbers

WITH usage_logs AS (
    SELECT *
    FROM {{usage_log_old_table}}
    WHERE usage_start_time >= '{{start_date}}'
      AND usage_start_time < '{{end_date_exclusive}}'
      AND account_id = {{account_id}}
    UNION ALL
    SELECT *
    FROM {{usage_log_current_table}}
    WHERE usage_start_time >= '{{start_date}}'
      AND usage_start_time < '{{end_date_exclusive}}'
      AND account_id = {{account_id}}
)
SELECT
    COUNT(*) AS total_transaction,
    SUM(ROUND(t.act_usage_unit, 2)) AS mou,
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type = 'VO'
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
        OR (
            (
                t.opposite_number LIKE '601300%'
                OR t.opposite_number LIKE '601700%'
                OR t.opposite_number LIKE '601800%'
            )
            AND LENGTH(t.opposite_number) < 12
        )
    );
