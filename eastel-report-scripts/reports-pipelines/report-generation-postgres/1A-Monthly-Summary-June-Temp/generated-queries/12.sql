-- Query 12: Intl Roaming Voice (MT)

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
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MT'
    AND t.roaming_destination_id <> 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rat_type;
