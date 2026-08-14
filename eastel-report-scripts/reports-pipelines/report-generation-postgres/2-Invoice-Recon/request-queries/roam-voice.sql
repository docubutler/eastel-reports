/*
Copy-paste sample for July 2026:
Requires temp_roaming_destination to be loaded from Mongo roaming_destination by generate_report.py.

SELECT 'Voice Roaming' AS service_type, 'MO' AS charge_type, COALESCE(NULLIF(REPLACE(REPLACE(BTRIM(rd.roaming_destination_name), ': ', '-'), ':', '-'), ''), NULLIF(BTRIM(rd.country), ''), 'UNMAPPED-' || t.roaming_destination_id::text) AS country, COUNT(*) AS call_count, ROUND(SUM(COALESCE(t.act_update_used_volume, 0)) / 60.0, 2) AS mou
FROM public.iot_portal_tb_request_log t
LEFT JOIN temp_roaming_destination rd ON rd.roaming_destination_id = t.roaming_destination_id
WHERE t.req_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.req_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.roaming_destination_id <> 87
  AND COALESCE(t.act_update_used_volume, 0) > 0
GROUP BY country
ORDER BY country;
*/

SELECT 'Voice Roaming' AS service_type, 'MO' AS charge_type, COALESCE(NULLIF(REPLACE(REPLACE(BTRIM(rd.roaming_destination_name), ': ', '-'), ':', '-'), ''), NULLIF(BTRIM(rd.country), ''), 'UNMAPPED-' || t.roaming_destination_id::text) AS country, COUNT(*) AS call_count, ROUND(SUM(COALESCE(t.act_update_used_volume, 0)) / 60.0, 2) AS mou
FROM {{request_log_table}} t
LEFT JOIN temp_roaming_destination rd ON rd.roaming_destination_id = t.roaming_destination_id
WHERE t.req_time >= '{{start_date}}'
  AND t.req_time < '{{end_date}}'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.roaming_destination_id <> 87
  AND COALESCE(t.act_update_used_volume, 0) > 0
GROUP BY country
ORDER BY country;
