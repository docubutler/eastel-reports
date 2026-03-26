-- Report Query for Voice Usage Logs

SELECT 
    log.msisdn,
    log.imsi,
	log.iccid,
    log.roaming_mccmnc,
    log.service_type_sub_cd AS leg, -- MO or MT
    log.opposite_number AS calledparty,
    log.rating_group AS isOLO, -- On-net, Off-net
	
    -- Identifies if the destination is NOT the home network (87), since roaming_destination_id = 87 is for Umobile Malaysia
	CASE 
        WHEN roaming_destination_id != 87 THEN 'Yes' 
        ELSE 'No' 
    END AS isRoaming,                     
    
	CASE 
        WHEN roaming_mccmnc IN ('60181000031', '60181000366') THEN 'Yes' 
        ELSE 'No' 
    END AS isS8HR, 
    
	log.usage_start_time, 
    log.usage_end_time,
    log.act_usage_unit AS act_MOU, -- actual Minutes of Usage in seconds for (reconciliation with UM)
    log.usage_unit AS MOU, -- Minutes of Usage according to charging Blocks size
    
--	CASE 
--        WHEN plan.service_plan_code = 'PAYG' THEN 'YES' 
--        ELSE 'NO' 
--    END AS isPAYG,  --  Yes if charged in Monetary Value
	log.price_amount,
    log.sim_service_plan_id,
    log.last_grant_sim_service_plan_bucket_id
FROM 
    usage_logs LOG
-- LEFT JOIN 
   -- public.iot_portal_tb_sim_service_plan plan 
    -- ON log.sim_service_plan_id = plan.sim_service_plan_id
WHERE 
    log.rat_type = 'VO'
    AND log.act_usage_unit > 0
    -- AND log.msisdn = '601175900078'
     AND log.usage_start_time BETWEEN '2026-03-02' AND '2026-03-18'
    AND log.roaming_mccmnc NOT IN ('60181000014', '60181000015', '60181000018', '60181000019')
    AND log.roaming_destination_id != 87 -- roaming_destination_id = 87 is for Umobile Malaysia
    
ORDER BY 
    log.usage_end_time DESC
LIMIT 100;
