/*
Copy-paste sample for July 2026:
Requires temp_country_code to be loaded from Mongo country_code by generate_report.py.

SELECT
    'SMS' AS service_type,
    'SMS MO' AS charge_type,
    COALESCE(cc.country, 'UNMAPPED') AS country,
    COUNT(*) AS sms_count
FROM public.iot_portal_tb_usage_log t
LEFT JOIN LATERAL (
    SELECT c.country
    FROM temp_country_code c
    WHERE BTRIM(t.opposite_number::text) LIKE c.country_code || '%'
    ORDER BY CHAR_LENGTH(c.country_code) DESC
    LIMIT 1
) cc ON TRUE
WHERE t.usage_start_time >= TIMESTAMP '2026-07-01 00:00:00'
  AND t.usage_start_time <  TIMESTAMP '2026-08-01 00:00:00'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0
  AND BTRIM(COALESCE(t.opposite_number::text, '')) NOT IN ('', 'None', 'none')
  AND BTRIM(t.opposite_number::text) NOT LIKE '60%'
GROUP BY COALESCE(cc.country, 'UNMAPPED')
ORDER BY country;
*/

SELECT
    'SMS' AS service_type,
    'SMS MO' AS charge_type,
    COALESCE(cc.country, 'UNMAPPED') AS country,
    COUNT(*) AS sms_count
FROM {{usage_log_table}} t
LEFT JOIN LATERAL (
    SELECT c.country
    FROM temp_country_code c
    WHERE BTRIM(t.opposite_number::text) LIKE c.country_code || '%'
    ORDER BY CHAR_LENGTH(c.country_code) DESC
    LIMIT 1
) cc ON TRUE
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0
  AND BTRIM(COALESCE(t.opposite_number::text, '')) NOT IN ('', 'None', 'none')
  AND BTRIM(t.opposite_number::text) NOT LIKE '60%'
GROUP BY COALESCE(cc.country, 'UNMAPPED')
ORDER BY country;
