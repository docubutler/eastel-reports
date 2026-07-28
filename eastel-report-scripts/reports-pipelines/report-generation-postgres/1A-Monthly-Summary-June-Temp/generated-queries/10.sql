-- Query 10: Intl Roaming Data 5G

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
    SUM(ROUND((t.act_usage_unit / 1048576), 2)) AS mou_mbs
FROM usage_logs t
WHERE
    t.rat_type IN ('5G')
    AND t.roaming_destination_id <> 87
GROUP BY
    t.rat_type;
