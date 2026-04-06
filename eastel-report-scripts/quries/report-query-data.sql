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
