/* Invoice reconciliation queries.
   Source table for the implemented reports: {{request_log_table}}.
   Queries that are not yet defensible from local repo context are left as TODO stubs
   with the correct output columns so the pipeline and CSV templates are ready.
*/


-- QUERY: 1 | Active Subscribers
/*
Active subscriber:
- distinct MSISDNs that generated MO traffic within the report date window
- includes Voice, SMS, and Data
*/
SELECT
    'Active Subscriber' AS service_type,
    'Total Active Subscriber Current' AS charge_type,
    COUNT(DISTINCT t.msisdn)::text AS count_value
FROM {{request_log_table}} t
WHERE t.req_time >= '{{start_date}}'
  AND t.req_time < '{{end_date_exclusive}}'
  AND t.service_type_sub_cd = 'MO'
  AND t.rat_type IN ('VO', 'SM', '4G', '5G')
  AND COALESCE(TRIM(t.msisdn), '') <> '';


-- QUERY: 2 | Domestic A2P SMS TODO placeholder
/*
TODO:
- Replace this placeholder with the real A2P SMS query.
- The sample looks sourced from SMSC CDR data rather than {{request_log_table}}.
*/
SELECT
    CAST(NULL AS text) AS service_type,
    CAST(NULL AS text) AS charge_type,
    CAST(NULL AS text) AS sms_type,
    CAST(NULL AS numeric) AS no_of_sms
WHERE FALSE;


-- QUERY: 3 | Domestic SMS Voice and Data summary
WITH report_rows AS (
    SELECT
        1 AS sort_order,
        'Domestic SMS' AS section,
        'SMS' AS service_type,
        'MO' AS charge_type,
        'On Net' AS usage_type,
        COUNT(*)::numeric AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type IN ('SM')
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87

    UNION ALL

    SELECT
        2 AS sort_order,
        'Domestic SMS' AS section,
        'SMS' AS service_type,
        'MO' AS charge_type,
        'Off Net' AS usage_type,
        COUNT(*)::numeric AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type IN ('SM')
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87

    UNION ALL

    SELECT
        3 AS sort_order,
        'Domestic Voice' AS section,
        'Voice' AS service_type,
        'MO' AS charge_type,
        'On Net' AS usage_type,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 60.0, 2) AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
      AND t.rating_group = 'ONNET'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND t.opposite_number LIKE '60%'

    UNION ALL

    SELECT
        4 AS sort_order,
        'Domestic Voice' AS section,
        'Voice' AS service_type,
        'MO' AS charge_type,
        'Off Net' AS usage_type,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 60.0, 2) AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type = 'VO'
      AND t.service_type_sub_cd = 'MO'
      AND t.rating_group = 'OFFNET'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND t.opposite_number LIKE '60%'

    UNION ALL

    SELECT
        5 AS sort_order,
        'Domestic Data' AS section,
        'Data' AS service_type,
        'MO' AS charge_type,
        '4G' AS usage_type,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 1048576.0, 2) AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type IN ('4G')
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND t.rating_group NOT IN ('500003')

    UNION ALL

    SELECT
        6 AS sort_order,
        'Domestic Data' AS section,
        'Data' AS service_type,
        'MO' AS charge_type,
        '5G' AS usage_type,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 1048576.0, 2) AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type IN ('5G')
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND t.rating_group NOT IN ('500003')
)
SELECT
    section,
    service_type,
    charge_type,
    usage_type,
    value
FROM report_rows
ORDER BY sort_order;


-- QUERY: 4 | International Voice SMS and Data TODO placeholder
/*
TODO:
- Replace this placeholder with the real country-based and itemized query.
- The sample implies destination-country and roaming-country mapping logic.
- That logic likely needs reference tables such as country-code and roaming-destination lookups.
*/
SELECT
    CAST(NULL AS text) AS section,
    CAST(NULL AS text) AS service_type,
    CAST(NULL AS text) AS charge_type,
    CAST(NULL AS text) AS country,
    CAST(NULL AS numeric) AS metric_1,
    CAST(NULL AS numeric) AS metric_2
WHERE FALSE;


-- QUERY: 5 | Premium and Special Numbers
WITH categories AS (
    SELECT 1 AS sort_order, '1 MOCC - 03-8000 8000' AS call_type
    UNION ALL SELECT 2, '1300 Numbers'
    UNION ALL SELECT 3, '1700 Numbers'
    UNION ALL SELECT 4, '1800 Numbers'
    UNION ALL SELECT 5, 'Directory Assistance -Services 103'
    UNION ALL SELECT 6, 'Emergency Numbers'
    UNION ALL SELECT 7, 'Info Services - 100'
    UNION ALL SELECT 8, 'Info Services - 15454'
    UNION ALL SELECT 9, 'Info Services - 15300'
    UNION ALL SELECT 10, 'Info Services - 15353'
    UNION ALL SELECT 11, 'Info Services - 15404'
    UNION ALL SELECT 12, 'Info Services - 15444'
    UNION ALL SELECT 13, 'Info Services - 15777'
),
aggregated AS (
    SELECT
        CASE
            WHEN t.opposite_number = '600380008000' THEN '1 MOCC - 03-8000 8000'
            WHEN t.opposite_number LIKE '601300%' AND LENGTH(t.opposite_number) < 12 THEN '1300 Numbers'
            WHEN t.opposite_number LIKE '601700%' AND LENGTH(t.opposite_number) < 12 THEN '1700 Numbers'
            WHEN t.opposite_number LIKE '601800%' AND LENGTH(t.opposite_number) < 12 THEN '1800 Numbers'
            WHEN t.opposite_number = '60103' THEN 'Directory Assistance -Services 103'
            WHEN t.opposite_number = '60100' THEN 'Info Services - 100'
            WHEN t.opposite_number = '6015454' THEN 'Info Services - 15454'
            WHEN t.opposite_number = '6015300' THEN 'Info Services - 15300'
            WHEN t.opposite_number = '6015353' THEN 'Info Services - 15353'
            WHEN t.opposite_number = '6015404' THEN 'Info Services - 15404'
            WHEN t.opposite_number = '6015444' THEN 'Info Services - 15444'
            WHEN t.opposite_number = '6015777' THEN 'Info Services - 15777'
            ELSE NULL
        END AS call_type,
        COUNT(*)::numeric AS no_of_calls,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 60.0, 2) AS mou
    FROM {{request_log_table}} t
    WHERE t.rat_type = 'VO'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND (
          t.opposite_number = '600380008000'
          OR t.opposite_number = '60103'
          OR t.opposite_number = '60100'
          OR t.opposite_number = '6015454'
          OR t.opposite_number = '6015300'
          OR t.opposite_number = '6015353'
          OR t.opposite_number = '6015404'
          OR t.opposite_number = '6015444'
          OR t.opposite_number = '6015777'
          OR (t.opposite_number LIKE '601300%' AND LENGTH(t.opposite_number) < 12)
          OR (t.opposite_number LIKE '601700%' AND LENGTH(t.opposite_number) < 12)
          OR (t.opposite_number LIKE '601800%' AND LENGTH(t.opposite_number) < 12)
      )
    GROUP BY 1
)
SELECT
    'Voice' AS service_type,
    'Premium and Special Numbers' AS charge_type,
    c.call_type,
    a.no_of_calls,
    a.mou
FROM categories c
LEFT JOIN aggregated a
    ON a.call_type = c.call_type
ORDER BY c.sort_order;
