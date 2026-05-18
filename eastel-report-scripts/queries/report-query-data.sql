/* ================================================================
   FINAL RECON QUERY – DATA 45 & 5G 
   ================================================================ */
WITH params AS (
    SELECT 
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
)
SELECT 
    p.report_start_date,
    p.report_end_date,
    roaming_mccmnc, -- getting which country the data was used
    rat_type, -- whether 4G or 5G was used

    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2)  AS total_act_usage_unit, -- actual usage unit
    ROUND(SUM(usage_unit), 2) AS total_usage_unit -- usage based on package

FROM iot_portal_tb_usage_log_rep 
JOIN params p

WHERE 
    (rat_type = '4G' OR rat_type = '5G') -- for data only 

    AND act_usage_unit > 0

    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
    
GROUP BY
    p.report_start_date,
    p.report_end_date,
    roaming_mccmnc,
    rat_type;


/* ================================================================
   TITLE: Roaming Data Usage by Country 

   DESCRIPTION:
   This query gets 4G/5G data usage grouped by the country where the
   subscriber was latched when the usage happened.

   Matching logic:
   - Only 4G/5G data records
   - Country is derived from `roaming_destination_id` by joining the
     `roaming_destination` reference table
   - `roaming_mccmnc` is kept as supporting network detail for diagnostics
   - `roaming_status` is derived from `roaming_destination_id`

   ================================================================ */

WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
),
roaming_country_ref AS (
    SELECT
        rd.roaming_destination_id,
        rd.country,
        rd.roaming_destination_name,
        rd.mcc
    FROM roaming_destination rd
),
data_base AS (
    SELECT
        t.usage_log_id,
        t.roaming_destination_id,
        t.roaming_mccmnc,
        LEFT(t.roaming_mccmnc, 3) AS visited_mcc,
        t.rat_type,
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
    WHERE t.rat_type IN ('4G', '5G')
      AND t.act_usage_unit > 0
      AND t.usage_start_time >= p.report_start_date
      AND t.usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
),
data_enriched AS (
    SELECT
        b.usage_log_id,
        b.report_start_date,
        b.report_end_date,
        b.roaming_status,
        b.roaming_destination_id,
        b.roaming_mccmnc,
        b.visited_mcc,
        b.rat_type,
        b.act_usage_unit,
        b.usage_unit,
        r.country,
        r.roaming_destination_name,
        r.mcc AS reference_mcc
    FROM data_base b
    LEFT JOIN roaming_country_ref r
        ON r.roaming_destination_id = b.roaming_destination_id
)
SELECT
    report_start_date,
    report_end_date,
    roaming_status,
    rat_type,
    COALESCE(country, 'UNMAPPED') AS usage_country,
    COALESCE(reference_mcc, visited_mcc, 'UNMAPPED') AS matched_mcc,
    roaming_destination_id,
    roaming_destination_name,
    CASE
        WHEN country IS NULL THEN roaming_mccmnc
        ELSE NULL
    END AS unmatched_roaming_mccmnc,
    COUNT(*) AS total_records,
    COUNT(DISTINCT roaming_mccmnc) AS distinct_networks_seen,
    ROUND(SUM(act_usage_unit), 2) AS total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) AS total_billed_usage_unit
FROM data_enriched
GROUP BY
    report_start_date,
    report_end_date,
    roaming_status,
    rat_type,
    usage_country,
    matched_mcc,
    roaming_destination_id,
    roaming_destination_name,
    unmatched_roaming_mccmnc
ORDER BY
    roaming_status,
    total_records DESC,
    usage_country,
    rat_type;

/* ================================================================
   TITLE: Domestic Data Usage Summary 

   DESCRIPTION:
   This query gets 4G/5G data usage for Malaysia grouped by rat_type i.e. 4G or 5G.

   ================================================================ */
    
SELECT
    rat_type, SUM(usage_unit) AS mou, SUM(ROUND((usage_unit / 1048576), 2)) as MBytes,
roaming_destination_id
FROM iot_portal_tb_usage_log t
WHERE  t.rat_type IN ('4G' , '5G')
  AND t.usage_start_time >= '2026-04-01'
  AND t.usage_start_time < '2026-05-01'
  AND roaming_destination_id = 87
GROUP BY t.rat_type,
roaming_destination_id;


/* ====================================================================
    Intl Roaming Data April 2026
   ==================================================================== */
SELECT
    rat_type, SUM(usage_unit) AS mou, SUM(ROUND((usage_unit / 1048576), 2)) as MBytes,
roaming_destination_id
FROM iot_portal_tb_usage_log_rep t
WHERE  t.rat_type IN ('4G' , '5G')
  AND t.usage_start_time >= '2026-04-01'
  AND t.usage_start_time < '2026-05-01'
  AND roaming_destination_id <> 87
GROUP BY t.rat_type,
roaming_destination_id;


