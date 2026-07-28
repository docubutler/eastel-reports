-- Query 7: International Voice

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
    t.rating_group,
    COUNT(*) AS total_transaction,
    ROUND(SUM(t.act_usage_unit), 2) AS mou,
    ROUND(SUM(t.act_usage_unit) / 60, 2) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type = 'VO'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rating_group;
