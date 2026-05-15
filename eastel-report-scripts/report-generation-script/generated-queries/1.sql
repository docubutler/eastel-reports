-- Query 1: Voice (Mobile Origination) - On Net

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    SUM(ROUND(update_used_volume / 60, 2)) AS mou_minutes,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('ONNET')
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date}}'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;
