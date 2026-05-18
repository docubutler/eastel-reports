/* ================================================================
   TITLE: SMSes Segregation by Opposite Number Prefix and Roaming Status

   DESCRIPTION:
   This query classifies billable Mobile Originated (MO) SMSes
   by roaming status and by opposite number prefix grouping.

   Grouping logic for opposite_number:
   - `STARTS_WITH_60`:
     opposite_number starts with '60'
   - `NON_60`:
     opposite_number does not start with '60'

   Roaming logic:
   - NON_ROAMING: roaming_destination_id = 87
   - ROAMING: roaming_destination_id <> 87

   Notes:
   - Only SMS records are included (rat_type = 'SM')
   - Only billable usage is counted (act_usage_unit > 0)
  
   ================================================================ */

WITH params AS (
    SELECT 
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
)
SELECT
    p.report_start_date,
    p.report_end_date,
    CASE
        WHEN roaming_destination_id = 87 THEN 'NON_ROAMING'
        ELSE 'ROAMING'
    END AS roaming_status,
    CASE
        WHEN opposite_number LIKE '60%' THEN 'STARTS_WITH_60'
        ELSE 'NON_60'
    END AS opposite_number_group,
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM iot_portal_tb_usage_log_rep t
JOIN params p
WHERE rat_type = 'SM' -- for SMS only
  -- AND service_type_sub_cd = 'MO' -- Not required as 'MO' and 'MT' are only applicable for rat_type = 'VO' 
  AND act_usage_unit > 0
  AND usage_start_time >= p.report_start_date
  AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY
    roaming_status,
    opposite_number_group,
    p.report_start_date,
    p.report_end_date
ORDER BY
    roaming_status,
    opposite_number_group;

-- confirming if service_type_sub_cd = 'MO' and 'MT' are only applicable for rat_type = 'VO'
    select count(*) from iot_portal_tb_usage_log_rep
    where rat_type = 'SM' and service_type_sub_cd in ('MO', 'MT'); -- should return 0 records


/* ================================================================
   TITLE: SMS by Destination Country and Roaming Status

   DESCRIPTION:
   This query summarizes SMS traffic by subscriber roaming status
   and destination country using the `opposite_number`.

   Logic:
   - Only SMS records are included (`rat_type = 'SM'`)
   - roaming_status is derived from `roaming_destination_id`:
       87   = NON_ROAMING
       <>87 = ROAMING
   - destination country is identified by matching `opposite_number`
     against `country_code_reference.country_code`
   - because country codes have variable lengths, the query selects
     the longest matching prefix for each number
   - unmatched numbers are labeled as `UNMAPPED`, and the leading
     digits are shown in `unmatched_number_prefix` for investigation

   Output:
   - one aggregated row per roaming_status and destination_country
   - includes total SMS count, actual usage, and billed usage
   ================================================================ */


    WITH params AS (
    SELECT
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
),
country_code_meta AS (
    SELECT MAX(CHAR_LENGTH(country_code)) AS max_country_code_len
    FROM country_code_reference
),
idd_base AS (
    SELECT
        t.usage_log_id,
        t.opposite_number,
        t.act_usage_unit,
        t.usage_unit,
        p.report_start_date,
        p.report_end_date,
        CASE
            WHEN t.roaming_destination_id = 87 THEN 'NON_ROAMING'
            ELSE 'ROAMING'
        END AS roaming_status
    FROM iot_portal_tb_usage_log_rep t
    JOIN params p
    WHERE t.rat_type = 'SM'
      -- AND t.service_type_sub_cd = 'MO' -- Not required as 'MO' and 'MT' are only applicable for rat_type = 'VO'
      AND t.usage_start_time >= p.report_start_date
      AND t.usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
),
idd_ranked AS (
    SELECT
        b.usage_log_id,
        b.report_start_date,
        b.report_end_date,
        b.roaming_status,
        b.opposite_number,
        b.act_usage_unit,
        b.usage_unit,
        c.country,
        c.country_code,
        ROW_NUMBER() OVER (
            PARTITION BY b.usage_log_id
            ORDER BY CHAR_LENGTH(c.country_code) DESC, c.country_code DESC
        ) AS rn
    FROM idd_base b
    LEFT JOIN country_code_reference c
        ON b.opposite_number LIKE CONCAT(c.country_code, '%')
)
SELECT
    report_start_date,
    report_end_date,
    roaming_status,
    COALESCE(country, 'UNMAPPED') AS destination_country,
    COALESCE(country_code, 'UNMAPPED') AS matched_country_code,
    CASE
        WHEN country IS NULL THEN LEFT(
            opposite_number,
            (SELECT max_country_code_len FROM country_code_meta)
        )
        ELSE NULL
    END AS unmatched_number_prefix,
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM idd_ranked
WHERE rn = 1
GROUP BY
    report_start_date,
    report_end_date,
    roaming_status,
    destination_country,
    matched_country_code,
    unmatched_number_prefix
ORDER BY
    roaming_status,
    total_calls DESC,
    destination_country;



/* ========================================================================================
   DESCRIPTION:
   Following query is a test for the query above, it shows all the rows, which 
   are used by the query above to group and show count by destination_country for both 
   Roaming and NON_Roaming, using `opposite_number` matched against country codes.
   Longest-prefix matching is used, and unmatched numbers are flagged.
   ======================================================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
),
country_code_meta AS (
    SELECT MAX(CHAR_LENGTH(country_code)) AS max_country_code_len
    FROM country_code_reference
),
sms_ranked AS (
    SELECT
        t.usage_log_id,
        p.report_start_date,
        p.report_end_date,
        t.msisdn,
        t.roaming_destination_id,
        t.roaming_mccmnc,
        CASE
            WHEN t.roaming_destination_id = 87 THEN 'NON_ROAMING'
            ELSE 'ROAMING'
        END AS roaming_status,
        t.opposite_number,
        t.act_usage_unit,
        t.usage_unit,
        t.usage_start_time,
        c.country,
        c.country_code,
        ROW_NUMBER() OVER (
            PARTITION BY t.usage_log_id
            ORDER BY CHAR_LENGTH(c.country_code) DESC, c.country_code DESC
        ) AS rn
    FROM iot_portal_tb_usage_log_rep t
    JOIN params p
    LEFT JOIN country_code_reference c
        ON t.opposite_number LIKE CONCAT(c.country_code, '%')
    WHERE t.rat_type = 'SM'
      AND t.usage_start_time >= p.report_start_date
      AND t.usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
)
SELECT
    report_start_date,
    report_end_date,
    usage_log_id,
    msisdn,
    roaming_destination_id,
    roaming_mccmnc,
    roaming_status,
    opposite_number,
    COALESCE(country, 'UNMAPPED') AS destination_country,
    COALESCE(country_code, 'UNMAPPED') AS matched_country_code,
    CASE
        WHEN country IS NULL THEN LEFT(
            opposite_number,
            (SELECT max_country_code_len FROM country_code_meta)
        )
        ELSE NULL
    END AS unmatched_number_prefix,
    act_usage_unit,
    usage_unit,
    usage_start_time
FROM sms_ranked
WHERE rn = 1
ORDER BY usage_start_time, usage_log_id;


/* ================================================================
   TITLE: MO SMS Count by Network Type

   DESCRIPTION:
   This query is used to do total SMS MO recon with UMobile.
   This query summarizes SMS usage into two network categories:

   - On Net  : rating_group = 'ONNET'
   - Off Net : rating_group = 'OFFNET'

   Output:
   - Service Type
   - Charge Type
   - SMS Type
   - No. of SMS

   Notes:
   - Only SMS records are included (rat_type = 'SM')
   - SMS is treated as MO in this dataset
   - Date range covers 2026-03-01 through 2026-03-31
   - Uses a half-open date filter for cross-database compatibility
   ================================================================ */

SELECT
    'SMS' AS "Service Type",
    'MO' AS "Charge Type",
    CASE
        WHEN rating_group = 'ONNET' THEN 'On Net'
        WHEN rating_group = 'OFFNET' THEN 'Off Net'
    END AS "SMS Type",
    COUNT(*) AS "No. of SMS"
FROM iot_portal_tb_usage_log_rep
WHERE rat_type = 'SM'
  AND rating_group IN ('ONNET', 'OFFNET')
  AND usage_start_time >= '2026-03-01'
  AND usage_start_time < '2026-04-01'
GROUP BY rating_group
ORDER BY
    CASE
        WHEN rating_group = 'ONNET' THEN 1
        WHEN rating_group = 'OFFNET' THEN 2
    END;


/* ================================================================
   MO SM Domestic, the table only contains MO SMS, so no need to put the MO check 
   ================================================================ */

SELECT
    rating_group, SUM(usage_unit) AS mou
FROM iot_portal_tb_usage_log t
WHERE t.rat_type = 'SM'
  AND t.usage_start_time >= '2026-03-01' 
  AND t.usage_start_time < '2026-04-01'
  AND roaming_destination_id = 87
GROUP BY t.rating_group;



/* ================================================================
    MO Calls dialled from Malaysia to International
    So this query gives Domestically originated MO Voice Calls dialed International numbers
   ================================================================ */

SELECT 
    rating_group, SUM(usage_unit) AS mou, 
    ROUND(SUM(usage_unit) / 60, 2) AS MOUmins 

FROM iot_portal_tb_usage_log t 

WHERE t.rat_type = 'SM' 
    -- AND t.service_type_sub_cd = 'MO' 
    -- AND t.rating_group IN ('ONNET', 'OFFNET') 
    AND t.usage_start_time >= '2026-04-01' 
    AND t.usage_start_time < '2026-05-01' 
    AND roaming_destination_id = 87 -- call originated from Malaysia
    AND opposite_number NOT LIKE '60%' 
GROUP BY t.rating_group;


select * from iot_portal_tb_usage_log_rep t 
where t.rat_type = 'VO' and opposite_number LIKE '1300%'