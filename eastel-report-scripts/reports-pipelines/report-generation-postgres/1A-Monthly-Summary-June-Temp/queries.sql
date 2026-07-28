/* ReadMe:
   Temporary June 2026 1A monthly summary.
   Usage-log rows are read from both June split tables and filtered by {{account_id}}.
   SMSC CDR rows do not have account_id and are intentionally not account-filtered.
*/


-- QUERY: 1 | Voice (Mobile Origination) - On Net

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
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes,
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('ONNET')
    AND t.roaming_destination_id = 87
    AND LENGTH(t.opposite_number) > 10
GROUP BY
    t.rat_type,
    t.roaming_destination_id;

-- QUERY: 2 | Voice (Mobile Origination) - Off Net

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
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes,
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('OFFNET')
    AND t.roaming_destination_id = 87
    AND LENGTH(t.opposite_number) > 10
    AND t.opposite_number LIKE '60%'
GROUP BY
    t.rat_type,
    t.roaming_destination_id;


-- QUERY: 3 | SMS (Mobile Origination) On Net

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


-- QUERY: 4 | SMS (Mobile Origination) Off Net

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


-- QUERY: 5 | 4G Data

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
    SUM(ROUND((t.act_usage_unit / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('4G')
    AND t.roaming_destination_id = 87
    AND t.rating_group NOT IN ('500003')
GROUP BY
    t.rat_type,
    t.roaming_destination_id;


-- QUERY: 6 | 5G Data

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
    SUM(ROUND((t.act_usage_unit / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id
FROM usage_logs t
WHERE
    t.rat_type IN ('5G')
    AND t.roaming_destination_id = 87
    AND t.rating_group NOT IN ('500003')
GROUP BY
    t.rat_type,
    t.roaming_destination_id;

-- QUERY: 7 | International Voice

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
    t.rating_group,
    COUNT(*) AS total_transaction,
    ROUND(SUM(t.act_usage_unit), 2) AS mou,
    ROUND(SUM(t.act_usage_unit) / 60, 2) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type = 'VO'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rating_group;


-- QUERY: 8 | International SMS

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
    t.rating_group,
    ROUND(SUM(t.act_usage_unit), 2) AS mou
FROM usage_logs t
WHERE
    t.rat_type = 'SM'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rating_group;


-- QUERY: 9 | Intl Roaming Data 4G

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
    SUM(ROUND((t.act_usage_unit / 1048576), 2)) AS mou_mbs
FROM usage_logs t
WHERE
    t.rat_type IN ('4G')
    AND t.roaming_destination_id <> 87
GROUP BY
    t.rat_type;


-- QUERY: 10 | Intl Roaming Data 5G

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
    SUM(ROUND((t.act_usage_unit / 1048576), 2)) AS mou_mbs
FROM usage_logs t
WHERE
    t.rat_type IN ('5G')
    AND t.roaming_destination_id <> 87
GROUP BY
    t.rat_type;

-- QUERY: 11 | Intl Roaming Voice (MO)

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
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MO'
    AND t.roaming_destination_id <> 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rat_type;


-- QUERY: 12 | Intl Roaming Voice (MT)

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
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MT'
    AND t.roaming_destination_id <> 87
    AND t.opposite_number NOT LIKE '60%'
GROUP BY
    t.rat_type;


-- QUERY: 13 | Intl Roaming SMS (MO)

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
    SUM(ROUND(t.act_usage_unit, 2)) AS mou
FROM usage_logs t
WHERE
    t.rat_type IN ('SM')
    AND t.service_type_sub_cd = 'MO'

    /* No OFFNET / ONNET classification in SMS data */
    -- AND t.rating_group IN ('OFFNET', 'ONNET')

    AND t.roaming_destination_id <> 87
GROUP BY
    t.rat_type;

-- QUERY: 14 | Premium or Special Numbers

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
    COUNT(*) AS total_transaction,
    SUM(ROUND(t.act_usage_unit, 2)) AS mou,
    SUM(ROUND(t.act_usage_unit / 60, 2)) AS mou_minutes
FROM usage_logs t
WHERE
    t.rat_type = 'VO'
    AND (
        t.opposite_number = '600380008000'
        OR t.opposite_number = '60103'
        OR t.opposite_number = '60100'
        OR t.opposite_number = '6015454'
        OR t.opposite_number = '6015300'
        OR t.opposite_number = '6015353'
        OR t.opposite_number = '6015404'
        OR t.opposite_number = '6015444'
        OR t.opposite_number = '6015777'
        OR (
            (
                t.opposite_number LIKE '601300%'
                OR t.opposite_number LIKE '601700%'
                OR t.opposite_number LIKE '601800%'
            )
            AND LENGTH(t.opposite_number) < 12
        )
    );

-- QUERY: 15 | Non-Profit A2P

SELECT COUNT(*) AS total_transaction
FROM {{smsc_cdr_table}}
WHERE origination_type = 'SMPP'
AND delivery_date >= '{{start_date}}'
AND delivery_date < '{{end_date_exclusive}}'
AND (addr_src_digits LIKE ('2%') OR addr_src_digits = '601170337777')
AND message_delivery_status = 'success';


-- QUERY: 16 | Commercial A2P

SELECT COUNT(*) AS total_transaction
FROM {{smsc_cdr_table}}
WHERE origination_type = 'SMPP'
AND delivery_date >= '{{start_date}}'
AND delivery_date < '{{end_date_exclusive}}'
AND addr_src_digits LIKE ('6%')
AND message_delivery_status = 'success';
