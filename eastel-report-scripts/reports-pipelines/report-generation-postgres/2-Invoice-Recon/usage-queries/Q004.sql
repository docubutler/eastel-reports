/*
Copy-paste sample for July 2026:

SELECT
    ROUND(SUM(CASE WHEN t.rating_group = 'ONNET' THEN COALESCE(t.act_usage_unit, 0) / 60.0 ELSE 0 END), 2) AS onnet_mou,
    ROUND(SUM(CASE WHEN t.rating_group = 'OFFNET' THEN COALESCE(t.act_usage_unit, 0) / 60.0 ELSE 0 END), 2) AS offnet_mou
FROM public.iot_portal_tb_usage_log t
WHERE t.usage_start_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.usage_start_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.rating_group IN ('ONNET', 'OFFNET')
  AND t.roaming_destination_id = 87
  AND t.opposite_number LIKE '60%'
  AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) > 10;
*/

SELECT
    ROUND(SUM(CASE WHEN t.rating_group = 'ONNET' THEN COALESCE(t.act_usage_unit, 0) / 60.0 ELSE 0 END), 2) AS onnet_mou,
    ROUND(SUM(CASE WHEN t.rating_group = 'OFFNET' THEN COALESCE(t.act_usage_unit, 0) / 60.0 ELSE 0 END), 2) AS offnet_mou
FROM {{usage_log_table}} t
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.rating_group IN ('ONNET', 'OFFNET')
  AND t.roaming_destination_id = 87
  AND t.opposite_number LIKE '60%'
  AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) > 10;
