/* ====================================================
   ReadMe:
    - Quries for reconciliation with UMobile, all data is extracted from iot_portal_tb_request_log table
   ==================================================== */


/* =========================================================
   1. Voice (Mobile Origination) - On Net
   ========================================================= */

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
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;

/* =========================================================
   2. Voice (Mobile Origination) - Off Net
   ========================================================= */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    SUM(ROUND(update_used_volume / 60, 2)) AS mou_minutes,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('VO')
    AND t.rating_group IN ('OFFNET')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;


/* =========================================================
   3. SMS (Mobile Origination) On Net
   ========================================================= */
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

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


/* =========================================================
   4. SMS (Mobile Origination) On Net
   ========================================================= */
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

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



/* ====================================================
   5. 4G Data
   ==================================================== */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume,2)) AS mou,
    SUM(ROUND((update_used_volume / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('4G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;




/* ====================================================
   6. 5G Data
   ==================================================== */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume,2)) AS mou,
    SUM(ROUND((update_used_volume / 1048576), 2)) AS mou_mbs,
    t.roaming_destination_id

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('5G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87

GROUP BY
    t.rat_type,
    t.roaming_destination_id;

/* ====================================================
   7. International Voice
   ==================================================== */

SELECT
    t.rating_group,
    COUNT(*) AS total_transaction,
    ROUND(SUM(update_used_volume), 2) AS mou,
    ROUND(SUM(update_used_volume) / 60, 2) AS mou_minutes

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type = 'VO'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;


/* ====================================================
   8. International SMS
   ==================================================== */

SELECT
    t.rating_group,
    ROUND(SUM(update_used_volume), 2) AS mou

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type = 'SM'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id = 87
    AND t.opposite_number NOT LIKE '60%'

GROUP BY
    t.rating_group;


/* ====================================================
    9. Intl Roaming Data 4G
    ==================================================== */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume,2)) AS mou,
    SUM(ROUND((update_used_volume / 1048576), 2)) AS mou_mbs

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('4G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;


    /* ====================================================
    10. Intl Roaming Data 5G
    ==================================================== */
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume,2)) AS mou,
    SUM(ROUND((update_used_volume / 1048576), 2)) AS mou_mbs

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('5G')
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87

GROUP BY
    t.rat_type;

/* ====================================================
11. Intl Roaming Voice (MO)
==================================================== */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    SUM(ROUND(update_used_volume / 60, 2)) AS mou_minutes

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MO'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;


/* ====================================================
12. Intl Roaming Voice (MT)
==================================================== */

SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou,
    SUM(ROUND(update_used_volume / 60, 2)) AS mou_minutes

FROM iot_portal_tb_request_log t

WHERE
    t.rat_type IN ('VO')
    AND t.service_type_sub_cd = 'MT'
    AND t.req_time >= '2026-05-11'
    AND t.req_time < '2026-05-12'
    AND t.roaming_destination_id <> 87
	AND opposite_number NOT LIKE '60%' 

GROUP BY
    t.rat_type;


/* ====================================================
13. Intl Roaming SMS (MO)
==================================================== */
SELECT
    t.rat_type,
    COUNT(*) AS total_transaction,
    SUM(ROUND(update_used_volume, 2)) AS mou

FROM iot_portal_tb_request_log t

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

