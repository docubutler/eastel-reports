-- Query 15: Non-Profit A2P

SELECT COUNT(*) AS total_transaction
FROM {{smsc_cdr_table}}
WHERE origination_type = 'SMPP'
AND delivery_date >= '{{start_date}}'
AND delivery_date < '{{end_date_exclusive}}'
AND (addr_src_digits LIKE ('2%') OR addr_src_digits = '601170337777')
AND message_delivery_status = 'success';
