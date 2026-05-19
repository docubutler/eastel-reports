select '2026-04-01' as report_start_date, '2026-04-30' as report_end_date,  count(*), 
	sum(update_used_volume), rating_group from iot_portal_tb_request_log t

 where t.req_time >= '2026-04-01'
    AND t.req_time < '2026-05-01'
	
	group by rating_group;