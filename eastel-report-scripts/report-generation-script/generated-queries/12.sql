-- Query 12: Intl Roaming Voice (MT)

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    SUM(ROUND(update_used_volume / 60, 2)) AS mou_minutes

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MT'
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date}}'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;
