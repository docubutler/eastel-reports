/* =====================================================================
   sim_service_plan_distinct_plans.csv  —  snapshot notes

  The CSV alongside this file is just the saved output of this query:

       SELECT DISTINCT service_plan_id, service_plan_code, service_plan_desc
       FROM iot_portal_tb_sim_service_plan
       ORDER BY service_plan_code;

   So the source of truth is the real table: iot_portal_tb_sim_service_plan.
   Do NOT create or reference a `service_plan_lookup` relation.

   ---------------------------------------------------------------------
   How the package name is reached from the usage logs
   ---------------------------------------------------------------------
   The usage tables carry `sim_service_plan_id` (the SIM plan *instance*,
   a large id such as 3332158), not `service_plan_id`. The name lives on
   the same sim service plan row, so ONE join is enough:

       iot_portal_tb_usage_log.sim_service_plan_id
           = iot_portal_tb_sim_service_plan.sim_service_plan_id
       -> iot_portal_tb_sim_service_plan.service_plan_code

   `sim_service_plan_id` is the primary key of
   iot_portal_tb_sim_service_plan, so this join keeps usage rows 1:1.
   ===================================================================== */


/* =====================================================================
   1. Confirm EZ50 exists on the plan table
   ===================================================================== */
SELECT DISTINCT
    service_plan_id,
    service_plan_code,
    service_plan_desc
FROM iot_portal_tb_sim_service_plan
WHERE service_plan_code LIKE 'EZ50%'
ORDER BY service_plan_code;


/* =====================================================================
   2. Top 10 usage-log rows whose plan is EZ50
   ===================================================================== */
SELECT
    u.usage_log_id,
    u.msisdn,
    u.sim_service_plan_id,
    u.last_grant_sim_service_plan_id,
    ssp.service_plan_id,
    ssp.service_plan_code,
    u.rat_type,
    u.roaming_destination_id,
    u.act_usage_unit,
    ROUND(u.act_usage_unit / 1048576.0, 2) AS usage_mb,
    u.usage_start_time
FROM iot_portal_tb_usage_log u
JOIN iot_portal_tb_sim_service_plan ssp
  ON ssp.sim_service_plan_id = u.sim_service_plan_id
WHERE ssp.service_plan_code LIKE 'EZ50%'
ORDER BY u.usage_log_id DESC
LIMIT 10;


/* =====================================================================
   2b. Sanity check: does EZ50 have any real (non-zero) usage, and where?
       Many usage-log rows are session / grant records with
       act_usage_unit = 0, so filter on that before aggregating.
   ===================================================================== */
SELECT
    ssp.service_plan_code,
    u.rat_type,
    CASE WHEN u.roaming_destination_id = 87 THEN 'HOME' ELSE 'ROAMING' END AS location,
    COUNT(*)                                     AS records,
    COUNT(*) FILTER (WHERE u.act_usage_unit > 0) AS records_with_usage,
    ROUND(SUM(u.act_usage_unit) / 1048576.0, 2)  AS total_mb
FROM iot_portal_tb_usage_log u
JOIN iot_portal_tb_sim_service_plan ssp
  ON ssp.sim_service_plan_id = u.sim_service_plan_id
WHERE ssp.service_plan_code LIKE 'EZ50%'
GROUP BY
    ssp.service_plan_code,
    u.rat_type,
    CASE WHEN u.roaming_destination_id = 87 THEN 'HOME' ELSE 'ROAMING' END
ORDER BY
    ssp.service_plan_code, u.rat_type, location;


/* =====================================================================
   3. EZ50 subscribers with >= 100 MB roaming (4G/5G) data usage
      - roaming = roaming_destination_id <> 87  (87 = Malaysia / home)
   ===================================================================== */
SELECT
    u.msisdn,
    COUNT(*)                                     AS total_records,
    COUNT(DISTINCT u.roaming_destination_id)     AS roaming_networks,
    ROUND(SUM(u.act_usage_unit) / 1048576.0, 2)  AS roaming_usage_mb
FROM iot_portal_tb_usage_log u
JOIN iot_portal_tb_sim_service_plan ssp
  ON ssp.sim_service_plan_id = u.sim_service_plan_id
WHERE ssp.service_plan_code LIKE 'EZ50%'
  AND u.rat_type IN ('4G', '5G')
  AND u.roaming_destination_id <> 87
  AND COALESCE(u.act_usage_unit, 0) > 0
GROUP BY u.msisdn
HAVING SUM(u.act_usage_unit) >= 100 * 1024 * 1024   -- >= 100 MiB
ORDER BY roaming_usage_mb DESC;


/* =====================================================================
   4. Same, but from iot_portal_tb_request_log (req_type = 'T')
      Volume column there is act_update_used_volume.
   ===================================================================== */
SELECT
    r.msisdn,
    COUNT(*)                                            AS total_records,
    COUNT(DISTINCT r.roaming_destination_id)            AS roaming_networks,
    ROUND(SUM(r.act_update_used_volume) / 1048576.0, 2) AS roaming_usage_mb
FROM iot_portal_tb_request_log r
JOIN iot_portal_tb_sim_service_plan ssp
  ON ssp.sim_service_plan_id = r.sim_service_plan_id
WHERE ssp.service_plan_code LIKE 'EZ50%'
  AND r.req_type = 'T'
  AND r.rat_type IN ('4G', '5G')
  AND r.roaming_destination_id <> 87
  AND COALESCE(r.act_update_used_volume, 0) > 0
GROUP BY r.msisdn
HAVING SUM(r.act_update_used_volume) >= 100 * 1024 * 1024
ORDER BY roaming_usage_mb DESC;
