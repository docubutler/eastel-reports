/* Daily 4G / 5G domestic data usage.

   One row per calendar day in the report window, in the shape agreed with
   Finance for the U Mobile CDR reconciliation:

       Date | 4G Usage (MBYTE) | 5G Usage (MBYTE) | Total Usage

   The row definition is deliberately identical to the Invoice Recon data
   queries (2-Invoice-Recon/usage-queries/Q006.sql and Q007.sql) so that the
   month total here ties back to that report:

     - data records only : rat_type IN ('4G', '5G')
     - domestic only     : roaming_destination_id = 87
     - 500003 excluded   : COALESCE(rating_group, '') <> '500003'
     - actual bytes      : act_usage_unit (not usage_unit, which is billed volume)
     - MB                : bytes / 1048576 (MiB)

   Days with no qualifying records are kept as 0.00 by the day spine so the
   reconciliation always shows all 30/31 dates.

   Parameters (bound, never interpolated): start_date, end_date_exclusive.
   Table name is substituted by generate_report.py after identifier validation.
*/
WITH params AS (
    SELECT
        %(start_date)s::timestamp AS window_start,
        %(end_date_exclusive)s::timestamp AS window_end
),
day_spine AS (
    -- A plain integer series plus date arithmetic, rather than interval
    -- generate_series, so the spine is a normal FROM item.
    SELECT p.window_start::date + g.generate_series::integer AS usage_date
    FROM params p
    CROSS JOIN generate_series(0, 366) AS g
    WHERE g.generate_series < (p.window_end::date - p.window_start::date)
),
daily AS (
    SELECT
        u.usage_start_time::date AS usage_date,
        SUM(CASE WHEN u.rat_type = '4G' THEN COALESCE(u.act_usage_unit, 0) ELSE 0 END) AS bytes_4g,
        SUM(CASE WHEN u.rat_type = '5G' THEN COALESCE(u.act_usage_unit, 0) ELSE 0 END) AS bytes_5g
    FROM {{usage_log_table}} u
    CROSS JOIN params p
    WHERE u.usage_start_time >= p.window_start
      AND u.usage_start_time <  p.window_end
      AND u.rat_type IN ('4G', '5G')
      AND u.roaming_destination_id = 87
      AND COALESCE(u.rating_group, '') <> '500003'
    GROUP BY 1
)
SELECT
    s.usage_date AS "Date",
    ROUND(COALESCE(d.bytes_4g, 0) / 1048576.0, 2) AS "4G Usage (MBYTE)",
    ROUND(COALESCE(d.bytes_5g, 0) / 1048576.0, 2) AS "5G Usage (MBYTE)",
    ROUND((COALESCE(d.bytes_4g, 0) + COALESCE(d.bytes_5g, 0)) / 1048576.0, 2) AS "Total Usage"
FROM day_spine s
LEFT JOIN daily d ON d.usage_date = s.usage_date
ORDER BY s.usage_date;
