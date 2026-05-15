-- Query 8: International SMS

SELECT
    t.rating_group,
    ROUND(SUM(update_used_volume), 2) AS mou

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type = 'SM'
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date}}'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;
