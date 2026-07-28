-- Query 1: Voice (Mobile Origination) - On Net

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
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(t.act_usage_unit, 2)) AS mou,
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes,
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('ONNET')
    AND t.roaming_destination_id = 87
    AND LENGTH(t.opposite_number) > 10
GROUP BY
    t.rat_type,
    t.roaming_destination_id;
