-- Query 7: International Voice

SELECT
    t.rating_group,
    COUNT(*) AS total_transaction,
    ROUND(SUM(update_used_volume), 2) AS mou,
    ROUND(SUM(update_used_volume) / 60, 2) AS mou_minutes

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type = 'VO'
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date}}'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;
