SELECT 
    msisdn,
    imsi,
    roaming_mccmnc,
    RAT_type, -- VO in case of voice, 4G/5G in case of Data, SM in case of SMS
    opposite_number,
    rating_group AS isOLO,
    
	 CASE 
        WHEN roaming_destination_id != 87 THEN 'Yes' 
        ELSE 'No' 
    END AS isRoaming,                     
    -- Changed OR to AND so it only returns 'YES' if it matches NEITHER value
    CASE 
        WHEN roaming_mccmnc IN ('60181000031', '60181000366') THEN 'Yes' 
        ELSE 'No' 
    END AS isS8HR, 
    usage_start_time, 
    usage_end_time,
    act_usage_unit AS act_MOU,
    usage_unit AS MOU,
    CASE WHEN sim_service_plan_id = 494 THEN 'YES' ELSE 'NO' END AS isPAYG,
    price_amount,
    sim_service_plan_id,
    last_grant_sim_service_plan_bucket_id
FROM 
    usage_logs
WHERE 
    service_type_id = 1 -- data
    AND act_usage_unit > 0
    AND usage_start_time BETWEEN '2026-03-02' AND '2026-03-21'
    -- AND roaming_mccmnc NOT IN ('60181000014', '60181000015', '60181000018', '60181000019','60180000000502')-- hplmn
	-- AND roaming_destination_id != 87 --roaming only
ORDER BY 
    usage_log_id ASC
LIMIT 100;