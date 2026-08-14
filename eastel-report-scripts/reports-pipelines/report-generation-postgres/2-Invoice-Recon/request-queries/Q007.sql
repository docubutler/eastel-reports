/*
Copy-paste sample for July 2026:

SELECT 'Data' AS service_type, 'Data MO' AS charge_type, '5G' AS data_type, ROUND(SUM(COALESCE(t.act_update_used_volume, 0)) / 1048576.0, 2) AS mou_mbs
FROM public.iot_portal_tb_request_log t
WHERE t.req_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.req_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND t.rat_type = '5G'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.rating_group, '') <> '500003';
*/

SELECT 'Data' AS service_type, 'Data MO' AS charge_type, '5G' AS data_type, ROUND(SUM(COALESCE(t.act_update_used_volume, 0)) / 1048576.0, 2) AS mou_mbs
FROM {{request_log_table}} t
WHERE t.req_time >= '{{start_date}}'
  AND t.req_time < '{{end_date}}'
  AND t.rat_type = '5G'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.rating_group, '') <> '500003';
