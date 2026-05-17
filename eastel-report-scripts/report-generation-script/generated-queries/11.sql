-- Query 11: Intl Roaming Voice (MO)

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    SUM(ROUND(act_update_used_volume / 60, 2)) AS mou_minutes

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MO'
    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date_exclusive}}'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;
