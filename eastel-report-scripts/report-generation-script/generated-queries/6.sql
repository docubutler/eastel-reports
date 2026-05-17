-- Query 6: 5G Data

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume,2)) AS mou,
    SUM(ROUND((act_update_used_volume / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('5G')
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date_exclusive}}'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;
