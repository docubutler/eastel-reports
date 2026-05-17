-- Query 1: Voice (Mobile Origination) - On Net

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    SUM(ROUND(act_update_used_volume / 60, 2)) AS mou_minutes,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('ONNET')
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date_exclusive}}'
    AND t.roaming_destination_id = 87
    AND LENGTH(opposite_number) > 10

GROUP BY
    t.rat_type,
    t.roaming_destination_id;
