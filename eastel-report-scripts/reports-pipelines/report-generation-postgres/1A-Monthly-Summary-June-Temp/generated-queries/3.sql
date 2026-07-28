-- Query 3: SMS (Mobile Origination) On Net

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
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('SM')

    /* No OFFNET / ONNET classification in SMS data */
    -- AND t.rating_group IN ('OFFNET', 'ONNET')

    AND t.roaming_destination_id = 87
GROUP BY
    t.rat_type,
    t.roaming_destination_id;
