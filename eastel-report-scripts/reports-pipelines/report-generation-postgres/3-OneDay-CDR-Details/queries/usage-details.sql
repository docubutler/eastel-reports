-- Same first-match category precedence as the Mongo OneDay CDR report.
-- %% is escaped for psycopg2's parameter binding, not a second wildcard.
WITH categorized AS (
    SELECT
        CASE
            WHEN rat_type = '4G' AND roaming_destination_id = 87
                 AND rating_group IS DISTINCT FROM '500003' THEN 1
            WHEN rat_type = '5G' AND roaming_destination_id = 87
                 AND rating_group IS DISTINCT FROM '500003' THEN 2
            WHEN rat_type = 'SM' AND roaming_destination_id = 87 THEN 3
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MO'
                 AND (
                     opposite_number IN (
                         '600380008000', '60103', '60100', '6015454',
                         '6015300', '6015353', '6015404', '6015444', '6015777'
                     )
                     OR (
                         (opposite_number LIKE '601300%%'
                          OR opposite_number LIKE '601700%%'
                          OR opposite_number LIKE '601800%%')
                         AND LENGTH(COALESCE(opposite_number, '')) < 12
                     )
                 ) THEN 12
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MO'
                 AND rating_group = 'ONNET' AND roaming_destination_id = 87
                 AND LENGTH(COALESCE(opposite_number, '')) > 10 THEN 4
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MO'
                 AND rating_group = 'OFFNET' AND roaming_destination_id = 87
                 AND LENGTH(COALESCE(opposite_number, '')) > 10
                 AND COALESCE(opposite_number, '') LIKE '60%%' THEN 5
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MO'
                 AND roaming_destination_id = 87
                 AND COALESCE(opposite_number, '') NOT LIKE '60%%' THEN 6
            -- Domestic SMS has already matched category 3, as in Mongo.
            WHEN rat_type = 'SM' AND roaming_destination_id = 87
                 AND COALESCE(opposite_number, '') NOT LIKE '60%%' THEN 7
            WHEN rat_type IN ('4G', '5G')
                 AND roaming_destination_id IS DISTINCT FROM 87 THEN 8
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MT'
                 AND roaming_destination_id IS DISTINCT FROM 87 THEN 9
            WHEN rat_type = 'VO' AND service_type_sub_cd = 'MO'
                 AND roaming_destination_id IS DISTINCT FROM 87
                 AND COALESCE(opposite_number, '') NOT LIKE '60%%' THEN 10
            WHEN rat_type = 'SM'
                 AND roaming_destination_id IS DISTINCT FROM 87 THEN 11
        END AS category_no,
        usage_start_time AS event_time,
        act_usage_unit AS usage_value,
        msisdn AS msisdn_a,
        opposite_number AS msisdn_b,
        imsi,
        usage_log_id AS source_record_id,
        usage_log_id AS postgres_record_id
    FROM {{usage_log_table}}
    WHERE usage_start_time >= %(start_date)s
      AND usage_start_time < %(end_date_exclusive)s
      AND rat_type IN ('VO', 'SM', '4G', '5G')
      {{msisdn_filter}}
      {{volume_filter}}
)
SELECT * FROM categorized
WHERE category_no IS NOT NULL
ORDER BY category_no, event_time, postgres_record_id;
