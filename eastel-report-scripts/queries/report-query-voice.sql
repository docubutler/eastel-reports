/* ================================================================
   FINAL RECON QUERY – VOICE (BILLABLE ONLY)

   NOTE:
   MT is excluded because:
   - All MT records have 0 usage

   ================================================================ */

SELECT 

    CAST('2026-03-02' AS DATE) AS report_start_date,
    CAST('2026-03-15' AS DATE) AS report_end_date,
    service_type_sub_cd AS direction,

    CASE 
        WHEN rating_group = 'ONNET' THEN 'ONNET' -- rating_group contains many other values, like ONNET, OFFNET, SM, 500002, 500003, 500001, 500004 etc.
        ELSE 'OTHER'
    END AS charging_type,

    CASE
        WHEN roaming_mccmnc LIKE '60%'
          -- OR log.roaming_mccmnc LIKE '502%' -- 50218 is not for rat_type = 'VO'
        THEN 'MY_ORIGIN'
        ELSE 'NON_MY_ORIGIN'
    END AS origin_type,

     CASE
        WHEN opposite_number NOT LIKE '60%' THEN 'IDD' -- LOCAL, HOME, IDD depends on originating number i.e. msisdn as well
        ELSE 'LOCAL'
    END AS destination_type,

    CASE 
        WHEN roaming_destination_id = 87 THEN 'DOMESTIC'
        ELSE 'ROAMING'
    END AS location_type,

    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2)  AS total_act_mou,
    ROUND(SUM(usage_unit), 2) AS total_mou

FROM iot_portal_tb_usage_log_rep 

WHERE 
    rat_type = 'VO' -- for voice only 

    AND act_usage_unit > 0

    AND usage_start_time BETWEEN '2026-03-02' AND '2026-03-16'

GROUP BY 
    service_type_sub_cd,

    CASE 
        WHEN rating_group = 'ONNET' THEN 'ONNET'
        ELSE 'OTHER'
    END,

    CASE
        WHEN roaming_mccmnc LIKE '60%' THEN 'MY_ORIGIN'
        ELSE 'NON_MY_ORIGIN'
    END,

    CASE
        WHEN opposite_number NOT LIKE '60%' THEN 'IDD'
        ELSE 'LOCAL'
    END,

    CASE 
        WHEN roaming_destination_id = 87 THEN 'DOMESTIC'
        ELSE 'ROAMING'
    END

ORDER BY 
    charging_type;



/* ================================================================
 MT query
    ================================================================ */

    SELECT 
    msisdn, 
    roaming_destination_id, 
    roaming_mccmnc,

    CASE 
        WHEN roaming_destination_id = 0 THEN 'CS'
        WHEN roaming_destination_id = 87 THEN 'Domestic'
        ELSE 'S8HR'
    END AS call_type

FROM iot_portal_tb_usage_log_rep 

WHERE 
    -- msisdn = '601176061125' AND
    rat_type = 'VO'
    AND service_type_sub_cd = 'MT'
    AND usage_start_time BETWEEN '2026-03-30' AND '2026-04-01';


/* ================================================================
   TITLE: MO Voice Calls Segregation by Roaming Status

   DESCRIPTION:
   This query classifies all billable Mobile Originated (MO) voice calls
   into two consolidated groups based on subscriber location:

   - NON_ROAMING:
     Calls where roaming_destination_id = 87
     This means the subscriber is on the home network in Malaysia.

   - ROAMING:
     Calls where roaming_destination_id <> 87
     This means the subscriber is outside Malaysia / on a roaming network.

   Notes:
   - Only voice records are included (rat_type = 'VO')
   - Only MO calls are included (service_type_sub_cd = 'MO')
   - Only billable usage is counted (act_usage_unit > 0)
   - Non-roaming is kept fully consolidated and not split further

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
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM iot_portal_tb_usage_log_rep t
JOIN params p
WHERE rat_type = 'VO'
  AND service_type_sub_cd = 'MO'
  AND act_usage_unit > 0
  AND usage_start_time >= p.report_start_date
  AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY roaming_status, p.report_start_date, p.report_end_date
ORDER BY roaming_status;


/* ================================================================
 Quries segregated by Roaming / Non-Roaming
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
    roaming_destination_id,
    roaming_mccmnc,
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM iot_portal_tb_usage_log_rep t
JOIN params p
WHERE rat_type = 'VO'
  AND service_type_sub_cd = 'MO'
  AND act_usage_unit > 0
  AND usage_start_time >= p.report_start_date
  AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY
    roaming_status,
    roaming_destination_id,
    roaming_mccmnc,
    p.report_start_date,
    p.report_end_date
ORDER BY
    roaming_status,
    roaming_destination_id,
    roaming_mccmnc;


/* ================================================================
   TITLE: MO Voice Calls Segregation by Opposite Number Prefix and Roaming Status

   DESCRIPTION:
   This query classifies billable Mobile Originated (MO) voice calls
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
   - Only voice records are included (rat_type = 'VO')
   - Only MO calls are included (service_type_sub_cd = 'MO')
   - Only billable usage is counted (act_usage_unit > 0)
   - Uses the same parameterized date range structure as the latest query

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
        WHEN opposite_number LIKE '60%' THEN 'MY_NUMBERS'
        ELSE 'NON_MY_NUMBERS'
    END AS opposite_number_group,
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM iot_portal_tb_usage_log_rep t
JOIN params p
WHERE rat_type = 'VO'
  AND service_type_sub_cd = 'MO'
  -- AND act_usage_unit > 0
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


    select 
    
     CASE
        WHEN roaming_destination_id = 87 THEN 'NON_ROAMING'
        ELSE 'ROAMING'
    END AS sub_roaming_status,

    CASE
        WHEN opposite_number LIKE '60%' THEN 'MY_NUMBERS'
        ELSE 'NON_MY_NUMBERS'
    END AS opposite_number_group ,
    count(*) as total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec

    from iot_portal_tb_usage_log_rep 

    where rat_type = 'VO'
    AND service_type_sub_cd = 'MO'
    -- AND act_usage_unit > 0
    
    group by 
     sub_roaming_status,
     opposite_number_group;


/* ================================================================
   TITLE: IDD Report for NON_MY_NUMBERS by Country Code

   DESCRIPTION:
   This report breaks only the `NON_MY_NUMBERS` MO voice calls into
   country buckets using the `country_code_reference` table.

   Matching logic:
   - Only MO voice calls are included
   - Only opposite_number values that do NOT start with `60` are included
   - The destination country is identified by prefix match against
     `country_code_reference.country_code`
   - Because country codes have variable lengths, the query chooses the
     longest matching prefix for each opposite_number
   - Numbers with no match are grouped as `UNMAPPED`

   Notes:
   - This is the IDD breakdown of the `NON_MY_NUMBERS` slice from the
     previous query
   - No Python script or stored procedure is required for this report
     as long as the reference table is populated

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
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
      AND t.opposite_number NOT LIKE '60%'
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
    CROSS JOIN country_code_meta m
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
        WHEN country IS NULL THEN LEFT(opposite_number, (SELECT max_country_code_len FROM country_code_meta))
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


/* ================================================================
   TITLE: ROAMING MO Voice Calls by Destination Country

   DESCRIPTION:
   This report uses the same country-code matching logic as the IDD
   report above, but keeps only `ROAMING` MO voice calls.

   Scope:
   - Subscriber is roaming: roaming_destination_id <> 87
   - MO voice only
   - Grouped by destination country using longest-prefix country-code match
   - Unmatched numbers are surfaced with a diagnostic prefix

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
roaming_base AS (
    SELECT
        t.usage_log_id,
        t.opposite_number,
        t.act_usage_unit,
        t.usage_unit,
        p.report_start_date,
        p.report_end_date
    FROM iot_portal_tb_usage_log_rep t
    JOIN params p
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
      AND t.roaming_destination_id <> 87
      AND t.usage_start_time >= p.report_start_date
      AND t.usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
),
roaming_ranked AS (
    SELECT
        b.usage_log_id,
        b.report_start_date,
        b.report_end_date,
        b.opposite_number,
        b.act_usage_unit,
        b.usage_unit,
        c.country,
        c.country_code,
        ROW_NUMBER() OVER (
            PARTITION BY b.usage_log_id
            ORDER BY CHAR_LENGTH(c.country_code) DESC, c.country_code DESC
        ) AS rn
    FROM roaming_base b
    CROSS JOIN country_code_meta m
    LEFT JOIN country_code_reference c
        ON b.opposite_number LIKE CONCAT(c.country_code, '%')
)
SELECT
    report_start_date,
    report_end_date,
    'ROAMING' AS roaming_status,
    COALESCE(country, 'UNMAPPED') AS destination_country,
    COALESCE(country_code, 'UNMAPPED') AS matched_country_code,
    CASE
        WHEN country IS NULL THEN LEFT(opposite_number, (SELECT max_country_code_len FROM country_code_meta))
        ELSE NULL
    END AS unmatched_number_prefix,
    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_sec,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_sec
FROM roaming_ranked
WHERE rn = 1
GROUP BY
    report_start_date,
    report_end_date,
    destination_country,
    matched_country_code,
    unmatched_number_prefix
ORDER BY
    total_calls DESC,
    destination_country;

/* ================================================================
   TEST query to verify if ROAMING subscriber is calling IDD or not
   unncomment the CASE statement in select list to see the difference between ROAMING vs NON_ROAMING
   ================================================================ */

   SELECT
    usage_log_id,
    msisdn,
    roaming_destination_id,
    roaming_mccmnc,
    opposite_number,
    'ROAMING' AS roaming_status,
    -- CASE
    --    WHEN roaming_destination_id = 87 THEN 'NON_ROAMING'
    --    ELSE 'ROAMING'
    -- END AS roaming_status, -- this case is irrelevant becuase already we have a filter of <> 87
    act_usage_unit,
    usage_unit,
    usage_start_time
FROM iot_portal_tb_usage_log_rep
WHERE rat_type = 'VO' -- it is a voice call
  AND service_type_sub_cd = 'MO' -- it is an outbound call
  AND roaming_destination_id <> 87 -- means subscriber (calling party) is not in MY
  AND usage_start_time >= '2026-03-02'
  AND usage_start_time < '2026-03-16'
ORDER BY usage_start_time, usage_log_id;


/* ================================================================
   TITLE: MO Voice Calls by Destination Country and Roaming Status

   DESCRIPTION:
   This query summarizes Mobile Originated (MO) voice calls by:
   - subscriber roaming status: ROAMING / NON_ROAMING
   - destination country, derived from opposite_number

   Logic:
   - Only voice records are included (rat_type = 'VO')
   - Only MO calls are included (service_type_sub_cd = 'MO')
   - roaming_status is derived from roaming_destination_id:
       87   = NON_ROAMING
       <>87 = ROAMING
   - destination country is identified by matching opposite_number
     against country_code_reference.country_code
   - because country codes have variable lengths, the query chooses
     the longest matching prefix for each opposite_number
   - if no match is found, the row is labeled as:
       destination_country = 'UNMAPPED'
       matched_country_code = 'UNMAPPED'
     and unmatched_number_prefix shows the leading digits for review

   Output:
   - one aggregated row per roaming_status + destination_country
   - includes total calls, total actual usage, and total billed usage

   Purpose:
   - provides a single report showing where MO voice traffic was
     terminated, split between roaming and non-roaming subscribers
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
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
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


/* ================================================================
   TITLE: MO Voice MOU Summary based on On Net vs Off Net

   DESCRIPTION:

   This query is used to do total Voice MO recon with UMobile.
   This query summarizes billed Mobile Originated (MO) voice usage
   into two categories:

   - On Net  : rating_group = 'ONNET'
   - Off Net : rating_group = 'OFFNET'

   Output:
   - Service Type
   - Charge Type
   - Call Type
   - MOUs

   Notes:
   - Only voice records are included (rat_type = 'VO')
   - Only MO calls are included (service_type_sub_cd = 'MO')
   - MOUs are calculated from billed usage_unit
   - usage_unit is converted from seconds to minutes by dividing by 60
   - Date filter is inclusive of report_start_date and report_end_date
   ================================================================ */


WITH params AS (
    SELECT
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
)
SELECT
    'Voice' AS `Service Type`,
    'MO' AS `Charge Type`,
    CASE
        WHEN rating_group = 'ONNET' THEN 'On Net'
        WHEN rating_group = 'OFFNET' THEN 'Off Net'
    END AS `Call Type`,
    ROUND(SUM(usage_unit) / 60, 2) AS `MOUs`
FROM iot_portal_tb_usage_log_rep t
JOIN params p
WHERE t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.rating_group IN ('ONNET', 'OFFNET')
  AND t.usage_start_time >= p.report_start_date
  AND t.usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY t.rating_group
ORDER BY
    CASE
        WHEN rating_group = 'ONNET' THEN 1
        WHEN rating_group = 'OFFNET' THEN 2
    END;

/* ================================================================
    MO Calls dialled from Malaysia to International
    So this query gives Domestically originated MO Voice Calls dialed International numbers
   ================================================================ */

SELECT 
    rating_group, SUM(usage_unit) AS mou, 
    ROUND(SUM(usage_unit) / 60, 2) AS MOUmins 

FROM iot_portal_tb_usage_log t 

WHERE t.rat_type = 'VO' 
    -- AND t.service_type_sub_cd = 'MO' 
    -- AND t.rating_group IN ('ONNET', 'OFFNET') 
    AND t.usage_start_time >= '2026-04-01' 
    AND t.usage_start_time < '2026-05-01' 
    AND roaming_destination_id = 87 -- call originated from Malaysia
    AND opposite_number NOT LIKE '60%' 
GROUP BY t.rating_group;


/* ================================================================
 Domestic VOICE MO Calls
   ================================================================ */
SELECT 
    rating_group, SUM(usage_unit) AS mou, 
    ROUND(SUM(usage_unit) / 60, 2) AS MOUmins 

FROM iot_portal_tb_usage_log t 

WHERE t.rat_type = 'VO' 
    AND t.service_type_sub_cd = 'MO' 
    AND t.rating_group IN ('ONNET', 'OFFNET') 
    AND t.usage_start_time >= '2026-04-01' 
    AND t.usage_start_time < '2026-05-01' 
    AND roaming_destination_id = 87 
    AND LENGTH(opposite_number) >= 11 
    AND opposite_number LIKE '60%' 
GROUP BY t.rating_group;

/* 
 Checking if a session has multiple rows, but it turns out that a session has only one row
*/
  select * from iot_portal_tb_usage_log_rep 
  where session_id = '1770272991390_12482_555249416' order by usage_start_time;