/*
Copy-paste sample for July 2026:

SELECT
    'SMS' AS service_type,
    'MO' AS charge_type,
    'On Net / Off Net' AS sms_type,
    COUNT(*) AS total
FROM public.iot_portal_tb_usage_log t
WHERE t.usage_start_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.usage_start_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0;
*/

SELECT
    'SMS' AS service_type,
    'MO' AS charge_type,
    'On Net / Off Net' AS sms_type,
    COUNT(*) AS total
FROM {{usage_log_table}} t
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0;
