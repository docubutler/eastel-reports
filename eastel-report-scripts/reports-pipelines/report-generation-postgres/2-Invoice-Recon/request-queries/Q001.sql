/*
Copy-paste sample for July 2026:

SELECT 'Active Subscriber' AS service_type, 'Total Active Subscriber Current' AS charge_type, COUNT(DISTINCT BTRIM(t.msisdn::text)) AS total
FROM public.iot_portal_tb_request_log t
WHERE t.req_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.req_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND COALESCE(t.act_update_used_volume, 0) > 0
  AND BTRIM(COALESCE(t.msisdn::text, '')) <> '';
*/

SELECT 'Active Subscriber' AS service_type, 'Total Active Subscriber Current' AS charge_type, COUNT(DISTINCT BTRIM(t.msisdn::text)) AS total
FROM {{request_log_table}} t
WHERE t.req_time >= '{{start_date}}'
  AND t.req_time < '{{end_date}}'
  AND COALESCE(t.act_update_used_volume, 0) > 0
  AND BTRIM(COALESCE(t.msisdn::text, '')) <> '';
