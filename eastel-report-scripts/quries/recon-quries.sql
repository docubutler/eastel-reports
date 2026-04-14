-- Active: 1774948279850@@127.0.0.1@3212@eastel

/* ==================================================
    VOICE RECONCILIATION QUERY, MO, OFFNET and ONNET
    ================================================== */

WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    CASE 
        WHEN rating_group = 'ONNET' THEN 'ONNET' -- rating_group contains many other values, like ONNET, OFFNET, SM, 500002, 500003, 500001, 500004 etc.
        WHEN rating_group = 'OFFNET' THEN 'OFFNET'
        ELSE 'OTHER'
    END AS network_type,
    CASE 
        WHEN service_type_sub_cd = 'MO' THEN 'MO'
        WHEN service_type_sub_cd = 'MT' THEN 'MT'
        ELSE 'OTHER'
    END AS event_direction

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    rat_type = 'VO' -- Change it to 'SMS' for SMS transactions
    and rating_group = 'OFFNET' -- Change it to OFFNET or OFFNET for Voice transactions and 'SM' for SMS transactions
    and roaming_destination_id = 87 -- Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
 GROUP BY network_type, event_direction;

 
/* ==================================================
    SMS RECONCILIATION QUERY
    ================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'ONNET' AS network_type, -- not sure how to distinguish between ONNET and OFFNET for now
    'MO' AS event_direction -- since all SMS are MO in usage logs table

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    rat_type = 'SM' -- Change it to 'SMS' for SMS transactions
    -- and rating_group = 'ONNET' All SMS in usage logs are MO ,-- Change it to OFFNET or OFFNET for Voice transactions and 'SM' for SMS transactions
    -- and roaming_destination_id = 87 -- Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
 GROUP BY network_type, event_direction;


/* ==================================================
    4G/5G RECONCILIATION QUERY
    ================================================== */

WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    rat_type = '4G' -- Change it to '5G' for 5G transactions
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)



/* ==================================================
    International Voice
    ================================================== */

WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'IDD' AS call_type,
    CASE 
        WHEN service_type_sub_cd = 'MO' THEN 'MO'
        WHEN service_type_sub_cd = 'MT' THEN 'MT'
        ELSE 'OTHER'
    END AS event_direction

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    rat_type = 'VO' -- Change it to 'SMS' for SMS transactions
    -- and rating_group = 'ONNET' -- Change it to OFFNET or OFFNET for Voice transactions and 'SM' for SMS transactions
    and roaming_destination_id = 87 -- Call originating from Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
    AND opposite_number NOT LIKE '60%' -- Call terminating outside Malaysia
 GROUP BY call_type, event_direction;

/* ==================================================
    International SMS
    ================================================== */

WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'IDD' AS call_type,
    CASE 
        WHEN service_type_sub_cd = 'MO' THEN 'MO'
        WHEN service_type_sub_cd = 'MT' THEN 'MT'
        ELSE 'OTHER'
    END AS event_direction

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    rat_type = 'SM' -- Change it to 'SMS' for SMS transactions
    -- and rating_group = 'ONNET' -- Change it to OFFNET or OFFNET for Voice transactions and 'SM' for SMS transactions
    and roaming_destination_id = 87 -- Call originating from Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
    AND opposite_number NOT LIKE '60%' -- Call terminating outside Malaysia
 GROUP BY call_type, event_direction;


 /* ==================================================
     Intl Roaming Data
    ================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'Intl Roaming' AS call_type

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    (rat_type = '4G' OR rat_type = '5G')  -- Change it to 'SM' for SMS or 'VO' for Voice transactions
    and roaming_destination_id <> 87 -- Call originating from outside of Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
 GROUP BY call_type;

 
  /* ==================================================
     Intl Roaming Voice (MO)
    ================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'Intl Roaming Voice (MO)' AS call_type

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    (rat_type = 'VO')  -- Change it to 'SM' for SMS or 'VO' for Voice or '4G'/'5G' for Data transactions
    and roaming_destination_id <> 87 -- Call originating from outside of Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
 GROUP BY call_type;

/* ==================================================
    Intl Roaming Voice (MT)
    MT Call (MT call's cdrs will only be recorded in system when eastel subscriber is roaming i.e. not in MY)
    ================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'Intl Roaming Voice (MT)' AS call_type

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    (rat_type = 'VO')  -- Change it to 'SM' for SMS or 'VO' for Voice or '4G'/'5G' for Data transactions
    AND roaming_destination_id <> 87 -- Call originating from outside of Malaysia. roaming_destination_id = 0 and 435 (some raoaming destination ID assigned by MB to HK), since it will originate multiple IDPs, for 0 it means its a CS call, for non-zero it would mean its s8HR call (the 0 part needs to be confirmed by MB)
    AND service_type_sub_cd = 'MT' -- MT Call (MT call's cdrs will only be recorded in system when eastel subscriber is roaming i.e. not in MY)
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
    -- roaming_mccmnc = fake GT for roaming_destination_id != 0 and != 87, and actual VLR GT when roaming_destination_id = 0
 GROUP BY call_type;


  /* ==================================================
     Intl Roaming SMS (MO)
    ================================================== */
WITH params AS (
    SELECT
        DATE('2026-03-01') AS report_start_date,
        DATE('2026-03-31') AS report_end_date
)
select 
    count(*) as total_transaction_count,
    ROUND(SUM(act_usage_unit), 2) as total_act_usage_unit,
    ROUND(SUM(usage_unit), 2) as total_usage_unit,
    'Intl Roaming SMS (MO)' AS call_type

 from iot_portal_tb_usage_log_rep 
 JOIN params p

 WHERE
    (rat_type = 'SM')  -- Change it to 'SM' for SMS or 'VO' for Voice or '4G'/'5G' for Data transactions
    and roaming_destination_id <> 87 -- Call originating from outside of Malaysia
    AND usage_start_time >= p.report_start_date
    AND usage_start_time < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
 GROUP BY call_type;

  /* ==================================================
     Commercial A2P SMS (MT)
    ================================================== */


WITH params AS (
    SELECT
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
)
SELECT
    p.report_start_date,
    p.report_end_date,
    -- t.addr_src_digits,
    COALESCE(t.message_delivery_status, 'UNKNOWN') AS message_delivery_status,
    COUNT(*) AS total_sms
FROM eastel.smsc_record_parsed t
JOIN params p
WHERE t.message_type = 'message'
   -- AND addr_src_digits NOT LIKE '60%' -- only including records sent from shortcodes
  AND (t.addr_src_digits = '22200Eastel' OR t.addr_src_digits = '22200' OR t.addr_src_digits = '601170337777') -- '22200Eastel' and '22200' are shortcodes and '601170337777' is long code used to send A2P messages
  AND message_delivery_status IN ('success', 'success_esme'/*, 'temp_failed', 'failed', 'partial', , 'temp_failed_esme', 'ocs_rejected'*/)
  AND t.delivery_date >= p.report_start_date
  AND t.delivery_date < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
  -- AND t.delivery_date < p.report_end_date + INTERVAL '1 day' -- to include the end date in the filter
GROUP BY
    p.report_start_date,
    p.report_end_date,
    -- t.addr_src_digits,
    message_delivery_status
ORDER BY
    message_delivery_status;



select max(usage_start_time) from iot_portal_tb_usage_log_rep; -- 2026-03-31 12:51:52.556648


SELECT DISTINCT roaming_mccmnc, roaming_destination_id, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'SM' 
GROUP BY 
roaming_mccmnc,
roaming_destination_id;


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
    (rat_type = '4G') -- OR rat_type = '5G'

GROUP BY
    p.report_start_date,
    p.report_end_date,
    roaming_mccmnc,
    rat_type;


    -- only need to consider SMPP and LCOAL_ORIG as A2P
    
    -- AND (t.addr_src_digits = '22200Eastel' OR t.addr_src_digits = '22200' OR t.addr_src_digits = '601170337777')

        -- if destination id <>>87 it is roaming data



    -- Non Profit A2P SMS: 22200, 22200Eastel Need to confirm in PreLaunch
    
    -- Do not Need to extract P2A because charging is already there in SMS report

    -- AND (t.addr_src_digits = '22200Eastel' OR t.addr_src_digits = '22200' OR t.addr_src_digits = '601170337777')