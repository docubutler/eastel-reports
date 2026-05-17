-- Query 14: Premium or Special Numbers

SELECT 
    -- opposite_number,
    COUNT(*) AS total_transaction,
	sum(update_used_volume) as mou

FROM {{request_log_table}} t
 
   WHERE 
    t.rat_type = 'VO'

    AND t.req_time >= '{{start_date}}'
    AND t.req_time < '{{end_date_exclusive}}'

    AND (
        opposite_number = '600380008000'
        OR opposite_number = '60103'
        OR opposite_number = '60100'
        OR opposite_number = '6015454'
        OR opposite_number = '6015300'
        OR opposite_number = '6015353'
        OR opposite_number = '6015404'
        OR opposite_number = '6015444'
        OR opposite_number = '6015777'

        OR (
            (
                opposite_number LIKE '601300%'
                OR opposite_number LIKE '601700%'
                OR opposite_number LIKE '601800%'
            )
            AND LENGTH(opposite_number) < 12
        )
    );
