-- Query 13: Intl Roaming SMS (MO)

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('SM')
	AND t.service_type_sub_cd = 'MO'

    /* No OFFNET / ONNET classification in SMS data */
    -- AND t.rating_group IN ('OFFNET', 'ONNET')

    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date_exclusive}}'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;
