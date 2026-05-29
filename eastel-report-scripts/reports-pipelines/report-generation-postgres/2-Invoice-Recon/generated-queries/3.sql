-- Query 3: Domestic SMS Voice and Data summary

WITH report_rows AS (
    SELECT
        1 AS sort_order,
        'Domestic SMS' AS section,
        'SMS' AS service_type,
        'MO' AS charge_type,
        'On Net' AS usage_type,
        COUNT(*)::numeric AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type = 'SM'
      AND t.rating_group = 'ONNET'
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
    WHERE t.rat_type = 'SM'
      AND t.rating_group = 'OFFNET'
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
    WHERE t.rat_type = '4G'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND COALESCE(t.rating_group, '') <> '500003'

    UNION ALL

    SELECT
        6 AS sort_order,
        'Domestic Data' AS section,
        'Data' AS service_type,
        'MO' AS charge_type,
        '5G' AS usage_type,
        ROUND(COALESCE(SUM(t.act_update_used_volume), 0) / 1048576.0, 2) AS value
    FROM {{request_log_table}} t
    WHERE t.rat_type = '5G'
      AND t.req_time >= '{{start_date}}'
      AND t.req_time < '{{end_date_exclusive}}'
      AND t.roaming_destination_id = 87
      AND COALESCE(t.rating_group, '') <> '500003'
)
SELECT
    section,
    service_type,
    charge_type,
    usage_type,
    value
FROM report_rows
ORDER BY sort_order;
