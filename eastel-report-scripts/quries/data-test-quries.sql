/* ================================================================
   TEST 1: DIRECTION DISTRIBUTION (MO vs MT)

   PURPOSE:
   --------
   Check how many records exist for each call direction.

   WHY:
   - Ensures MT exists in dataset
   - Detects imbalance (e.g. mostly MO)

   EXPECTATION:
   - MO >> MT (normal)
   - MT should NOT be zero

   INTERPRETATION:
   - If MT = 0 → upstream data issue
   - If MT very small → normal depending on system
   ================================================================ */

SELECT 
    service_type_sub_cd,
    COUNT(*) 
FROM iot_portal_tb_usage_log_rep
WHERE rat_type = 'VO'
GROUP BY service_type_sub_cd;


/* ================================================================
   TEST 2: MT AFTER BILLABLE FILTER

   PURPOSE:
   --------
   Check if MT survives billable condition (act_usage_unit > 0)

   WHY:
   - Determines if MT is actually billed

   EXPECTATION:
   - Likely 0 (as seen in your dataset)

   INTERPRETATION:
   - 0 → MT is non-billable in this system
   - >0 → MT participates in billing
   ================================================================ */

SELECT COUNT(*) 
FROM iot_portal_tb_usage_log_rep
WHERE 
    rat_type = 'VO'
    AND act_usage_unit > 0
    AND service_type_sub_cd = 'MT';


/* ================================================================
   TEST 3: MT USAGE ANALYSIS

   PURPOSE:
   --------
   Check whether MT has any actual or billed usage.

   WHY:
   - Confirms whether MT contributes to reconciliation

   INTERPRETATION:
   - act_usage_unit = 0 AND usage_unit = 0
     → MT is purely non-billable (your case)

   - If non-zero → MT must be included in recon
   ================================================================ */

SELECT 
    service_type_sub_cd,
    COUNT(*) AS total_records,
    SUM(act_usage_unit) AS total_act,
    SUM(usage_unit) AS total_usage
FROM iot_portal_tb_usage_log_rep
WHERE 
    rat_type = 'VO'
    AND service_type_sub_cd = 'MT'
GROUP BY service_type_sub_cd;


/* ================================================================
   TEST 4: MT RATING GROUP ANALYSIS

   PURPOSE:
   --------
   Check how MT calls are classified commercially.

   WHY:
   - Ensures MT falls under ONNET/OFFNET or not

   INTERPRETATION:
   - If NOT ONNET/OFFNET → your filter may exclude MT
   ================================================================ */

SELECT 
    rating_group,
    COUNT(*) 
FROM iot_portal_tb_usage_log_rep
WHERE 
    rat_type = 'VO'
    AND service_type_sub_cd = 'MT'
GROUP BY rating_group;


/* ================================================================
   TEST 5: ALL RATING GROUP VALUES

   PURPOSE:
   --------
   Understand all possible rating_group values.

   WHY:
   - Helps define filtering rules
   - Identifies non-voice or special categories

   YOUR FINDING:
   - ONNET / OFFNET → relevant
   - 500xxx, SM → ignore for now
   ================================================================ */

SELECT DISTINCT rating_group 
FROM iot_portal_tb_usage_log_rep;



/* ================================================================
   TEST 6: ROAMING CALLS TERMINATING IN MALAYSIA

   PURPOSE:
   --------
   Identify calls where:
   - Subscriber is roaming
   - Destination is Malaysia

   LOGIC:
   - roaming_destination_id != 87 → roaming
   - opposite_number LIKE '60%' → Malaysia

   INTERPRETATION:
   - If usage = 0 → not billed locally (your case)
   ================================================================ */

SELECT 
    log.service_type_sub_cd AS direction,
    COUNT(*) AS total_calls,
    SUM(log.act_usage_unit) AS total_act_mou,
    SUM(log.usage_unit) AS total_mou

FROM iot_portal_tb_usage_log_rep log

WHERE 
    log.rat_type = 'VO'
    AND log.roaming_destination_id != 87
    AND log.opposite_number LIKE '60%'

GROUP BY 
    log.service_type_sub_cd;


    /* ================================================================
   TEST 7: SAMPLE RECORD INSPECTION

   PURPOSE:
   --------
   Inspect raw records for roaming → MY

   WHY:
   - Validate number format
   - Confirm direction logic
   - Observe actual data behavior

   ================================================================ */

SELECT 
    log.msisdn,
    log.service_type_sub_cd,
    log.roaming_mccmnc,
    log.opposite_number,
    log.act_usage_unit,
    log.usage_unit

FROM iot_portal_tb_usage_log_rep log

WHERE 
    log.rat_type = 'VO'
    AND log.roaming_destination_id != 87
    AND log.opposite_number LIKE '60%'

LIMIT 20;


/* ================================================================
   TEST 8: DOMESTIC (87) vs ROAMING (NOT 87)

   PURPOSE:
   --------
   Compare billing behavior between:
   - Domestic calls (home network)
   - Roaming calls

   KEY INSIGHT:
   - 87 → billed locally
   - !=87 → usually NOT billed in this table

   INTERPRETATION:
   - If only 87 has usage → system is domestic-rating only
   ================================================================ */

SELECT 
    roaming_destination_id,
    COUNT(*) AS total_calls,
    SUM(act_usage_unit) AS total_act_mou,
    SUM(usage_unit) AS total_mou

FROM iot_portal_tb_usage_log_rep

WHERE rat_type = 'VO'

GROUP BY roaming_destination_id
ORDER BY roaming_destination_id;


/* ================================================================
   TEST 9: FULL FILTER IMPACT ON MT

   PURPOSE:
   --------
   Check if your full WHERE clause removes MT entirely

   WHY:
   - Helps debug missing categories in final query

   INTERPRETATION:
   - If result = 0 → filters are too restrictive for MT
   ================================================================ */

SELECT COUNT(*) 
FROM iot_portal_tb_usage_log_rep
WHERE 
    rat_type = 'VO'
    AND act_usage_unit > 0
    AND rating_group IN ('ONNET', 'OFFNET')
    AND service_type_sub_cd = 'MT';


/* ================================================================
 Face time number quries, these users have to be refunded 
    ================================================================ */
-- 'aparty, date time, charged amount

    WITH params AS (
        SELECT
            DATE('2026-04-09') AS report_start_date,
            DATE('2026-04-11') AS report_end_date
    )
    SELECT 
         p.report_start_date,
        p.report_end_date,
        msisdn, count(*) AS face_time_calls,
        SUM(act_cost_amount) AS total_charged_amount,
        SUM(act_price_amount) AS total_price_amount,
        SUM(act_usage_unit) AS total_act_usage_unit,
        SUM(usage_unit) AS total_usage_unit
        FROM iot_portal_tb_usage_log_rep

    JOIN params p

    WHERE opposite_number in ('447786205094') -- face time number, iOS sends SMS to this number before activating facetime
    
    AND usage_start_time >= p.report_start_date

    AND act_usage_unit > 0 -- only considering actual billable records
    
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)

    GROUP BY 
    p.report_start_date,
    p.report_end_date,
    msisdn
    
    ORDER BY face_time_calls DESC
    ;
/* ================================================================
 Face time number quries, these users have to be refunded non grouped
    ================================================================ */

     WITH params AS (
        SELECT
            DATE('2026-04-09') AS report_start_date,
            DATE('2026-04-11') AS report_end_date
    )
    SELECT 
        msisdn, 
        usage_start_time, act_cost_amount, act_price_amount, act_usage_unit, usage_unit,
        roaming_destination_id, roaming_mccmnc, service_type_sub_cd, rating_group, rat_type
        FROM iot_portal_tb_usage_log_rep
    JOIN params p

    WHERE opposite_number in ('447786205094') -- face time number, iOS sends SMS to this number before activating facetime
    
    AND usage_start_time >= p.report_start_date

    AND act_usage_unit > 0 -- only considering actual billable records
    
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY);