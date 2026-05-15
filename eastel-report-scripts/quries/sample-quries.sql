/* ================================================================
 Getting data usage of a particular msisdn for a specific period
 Postgres SQL syntax
 ================================================================ */
 WITH params AS (
    SELECT 
        DATE('2026-04-09') AS report_start_date,
        DATE('2026-05-05') AS report_end_date
)
SELECT 
	msisdn,
    p.report_start_date,
    p.report_end_date,
    roaming_mccmnc, -- getting which country the data was used
    rat_type, -- whether 4G or 5G was used

    COUNT(*) AS total_calls,
    ROUND(SUM(act_usage_unit), 2)  AS total_act_usage_unit, -- actual usage unit
    ROUND(SUM(usage_unit), 2) AS total_usage_unit -- usage based on package

FROM iot_portal_tb_usage_log_rep 
cross JOIN params p

WHERE 
    (rat_type = '4G' OR rat_type = '5G') -- for data only 

    AND act_usage_unit > 0

    AND usage_start_time >= p.report_start_date
    AND usage_start_time < p.report_end_date + INTERVAL '1 DAY'
    
    AND msisdn = '601176258424'
    
GROUP BY
	msisdn,
    p.report_start_date,
    p.report_end_date,
    roaming_mccmnc,
    rat_type;


/* ================================================================
   Count total rows between a provided start and end date
   MySQL + PostgreSQL compatible syntax

   Notes:
   - Replace the dates in the `params` CTE as needed
   - Uses DATE(usage_start_time) so the same query runs on both MySQL
     and PostgreSQL
   - The end date is inclusive
   ================================================================ */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-04-01') AS report_end_date
)
SELECT
    p.report_start_date,
    p.report_end_date,
    COUNT(*) AS total_rows
FROM iot_portal_tb_usage_log_rep t
CROSS JOIN params p
WHERE DATE(t.usage_start_time) BETWEEN p.report_start_date AND p.report_end_date
GROUP BY
    p.report_start_date,
    p.report_end_date;



SELECT MAX(usage_log_id) FROM iot_portal_tb_usage_log_rep WHERE report_start_date = '2026-03-01' AND report_end_date < '2026-04-01';


SELECT DISTINCT roaming_mccmnc, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO' 
and service_type_sub_cd = 'MO' GROUP BY roaming_mccmnc order by roaming_mccmnc;

SELECT DISTINCT roaming_destination_id, COUNT(*), sum(usage_unit) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO' 
and service_type_sub_cd = 'MO' GROUP BY roaming_destination_id order by roaming_destination_id;




