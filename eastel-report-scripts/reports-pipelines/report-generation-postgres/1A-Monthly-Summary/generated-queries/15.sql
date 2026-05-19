-- Query 15: Non-Profit A2P

SELECT COUNT(*) AS total_transaction 
FROM {{smsc_cdr_table}} WHERE origination_type = 'SMPP' 
AND delivery_date >= '2026-04-01' 
AND delivery_date < '2026-05-01'
AND (addr_src_digits LIKE ('2%') OR addr_src_digits = '601170337777')
AND message_delivery_status = 'success'
