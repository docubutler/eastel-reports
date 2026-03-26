SELECT 
    log.msisdn,
    log.imsi,
    log.iccid,
    log.roaming_mccmnc,
    log.opposite_number AS calledparty,
    
    -- Identifies if the destination is NOT the home network (87), since roaming_destination_id = 87 is for Umobile Malaysia
    CASE 
        WHEN log.roaming_destination_id != 87 THEN 'Yes' 
        ELSE 'No' 
    END AS isRoaming,
    
    log.usage_start_time, 
    log.usage_end_time,
    log.act_usage_unit AS act_MOU,
    log.usage_unit AS MOU,
    
    -- Efficiently checks the plan code from the joined table
    /*    
    CASE 
        WHEN plan.service_plan_code = 'PAYG' THEN 'YES' 
        ELSE 'NO' 
    END AS isPAYG,
    */
    log.price_amount,
    log.sim_service_plan_id,
    log.last_grant_sim_service_plan_bucket_id
FROM 
    -- public.iot_portal_tb_usage_log_rep log
    usage_logs LOG
/*LEFT JOIN 
    public.iot_portal_tb_sim_service_plan plan 
    ON log.sim_service_plan_id = plan.sim_service_plan_id
*/
WHERE 
    log.rat_type = 'SM'
    AND log.act_usage_unit > 0
    -- AND log.msisdn = '601175900078'
    AND log.usage_start_time BETWEEN '2026-03-02' AND '2026-03-18'
    AND log.roaming_mccmnc NOT IN ('60181000014', '60181000015', '60181000018', '60181000019')
    AND log.roaming_destination_id != 87 
    
ORDER BY 
    log.usage_end_time DESC
LIMIT 100;