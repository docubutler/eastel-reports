/* ReadMe:
   Queries for reconciliation with UMobile.
   All data is extracted from {{request_log_table}}.
*/


-- QUERY: 1 | Voice (Mobile Origination) - On Net

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
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND LENGTH(opposite_number) > 10

GROUP BY
    t.rat_type,
    t.roaming_destination_id;

-- QUERY: 2 | Voice (Mobile Origination) - Off Net

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    SUM(ROUND(act_update_used_volume / 60, 2)) AS mou_minutes,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('OFFNET')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND LENGTH(opposite_number) > 10
    
GROUP BY
    t.rat_type,
    t.roaming_destination_id;


-- QUERY: 3 | SMS (Mobile Origination) On Net
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('SM')

    /* No OFFNET / ONNET classification in SMS data */
    -- AND t.rating_group IN ('OFFNET', 'ONNET')

    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;


-- QUERY: 4 | SMS (Mobile Origination) Off Net
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('SM')

    /* No OFFNET / ONNET classification in SMS data */
    -- AND t.rating_group IN ('OFFNET', 'ONNET')

    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;



-- QUERY: 5 | 4G Data

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume,2)) AS mou,
    SUM(ROUND((act_update_used_volume / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('4G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;




-- QUERY: 6 | 5G Data

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume,2)) AS mou,
    SUM(ROUND((act_update_used_volume / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('5G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;

-- QUERY: 7 | International Voice

SELECT
    t.rating_group,
    COUNT(*) AS total_transaction,
    ROUND(SUM(act_update_used_volume), 2) AS mou,
    ROUND(SUM(act_update_used_volume) / 60, 2) AS mou_minutes

FROM {{request_log_table}} t

WHERE
    t.rat_type = 'VO'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;


-- QUERY: 8 | International SMS

SELECT
    t.rating_group,
    ROUND(SUM(act_update_used_volume), 2) AS mou

FROM {{request_log_table}} t

WHERE
    t.rat_type = 'SM'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;


-- QUERY: 9 | Intl Roaming Data 4G

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume,2)) AS mou,
    SUM(ROUND((act_update_used_volume / 1048576), 2)) AS mou_mbs

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('4G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;


-- QUERY: 10 | Intl Roaming Data 5G
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume,2)) AS mou,
    SUM(ROUND((act_update_used_volume / 1048576), 2)) AS mou_mbs

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('5G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;

-- QUERY: 11 | Intl Roaming Voice (MO)

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    SUM(ROUND(act_update_used_volume / 60, 2)) AS mou_minutes

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MO'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;


-- QUERY: 12 | Intl Roaming Voice (MT)

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(act_update_used_volume, 2)) AS mou,
    SUM(ROUND(act_update_used_volume / 60, 2)) AS mou_minutes

FROM {{request_log_table}} t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MT'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;


-- QUERY: 13 | Intl Roaming SMS (MO)
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

    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;

-- QUERY: 14 | Premium or Special Numbers

SELECT 
    -- opposite_number,
    COUNT(*) AS total_transaction,
	sum(update_used_volume) as mou

FROM {{request_log_table}} t
 
   WHERE 
    t.rat_type = 'VO'

    AND t.req_time >= '2026-04-01'
    AND t.req_time < '2026-05-01'

    AND (
        opposite_number = '600380008000'
        OR opposite_number = '60103'
        OR opposite_number = '60100'
        OR opposite_number = '6015454'
        OR opposite_number = '6015300'
        OR opposite_number = '6015353'
        OR opposite_number = '6015404'
        OR opposite_number = '6015444'
        OR opposite_number = '6015777'

        OR (
            (
                opposite_number LIKE '601300%'
                OR opposite_number LIKE '601700%'
                OR opposite_number LIKE '601800%'
            )
            AND LENGTH(opposite_number) < 12
        )
    );

