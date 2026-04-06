/* ================================================================
   TITLE: A2P SMSes originated from Eastel Shortcodes with Success Delivery Status

   DESCRIPTION:
    This query identifies A2P SMSes that were originated from Eastel shortcodes 
    (specifically '22200Eastel' and '22200') and had a successful delivery status.
    The query filters records based on the following criteria:
    - message_type = 'message' (to focus on actual SMS messages)
    - addr_src_digits = '22200Eastel' OR '22200' (to target specific shortcodes)
    - message_delivery_status IN ('success', 'success_esme') (to include only successfully delivered messages)
    - delivery_date within the specified report date range (2026-03-02 to 2026-03-15)
    ================================================================ */

WITH params AS (
    SELECT
        DATE('2026-03-02') AS report_start_date,
        DATE('2026-03-15') AS report_end_date
)
SELECT
    p.report_start_date,
    p.report_end_date,
    t.addr_src_digits,
    COALESCE(t.message_delivery_status, 'UNKNOWN') AS message_delivery_status,
    COUNT(*) AS total_sms
FROM eastel.smsc_record_parsed t
JOIN params p
WHERE t.message_type = 'message'
   -- AND addr_src_digits NOT LIKE '60%' -- only including records sent from shortcodes
  AND (t.addr_src_digits = '22200Eastel' OR t.addr_src_digits = '22200')
  AND message_delivery_status IN ('success', 'success_esme'/*, 'temp_failed', 'failed', 'partial', , 'temp_failed_esme', 'ocs_rejected'*/)
  AND t.delivery_date >= p.report_start_date
  AND t.delivery_date < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY
    p.report_start_date,
    p.report_end_date,
    t.addr_src_digits,
    message_delivery_status
ORDER BY
    message_delivery_status;


/* ================================================================
   TITLE: Distinct Source Address Grouping for SMSC Records

   DESCRIPTION:
   This query identifies distinct source address groupings in the
   `smsc_record_parsed` table, categorizing any source address that
   starts with '60' as '60xxxx' to facilitate analysis of patterns
   related to Malaysian numbers and also giving the counts as well

   ================================================================ */
SELECT
    CASE
        WHEN COALESCE(t.addr_src_digits, '') LIKE '60%' THEN '60xxxx'
        ELSE t.addr_src_digits
    END AS addr_src_digits_grouped,
    COUNT(*) AS total_count
FROM 
    eastel.smsc_record_parsed t
GROUP BY
    CASE
        WHEN COALESCE(t.addr_src_digits, '') LIKE '60%' THEN '60xxxx'
        ELSE t.addr_src_digits
    END
ORDER BY total_count DESC;
/* Output:
"addr_src_digits_grouped"	"total_count"
"60xxxx"	                "967770"
"22200Eastel"	            "50669"
"22200"	                    "18191"
"1131940167"	            "181"
"67027"	                    "13"
"84342222874"	            "2"
"23599"	                    "1"
"62033"	                    "1"
"68833"	                    "1"
*/

select count(*) from eastel.smsc_record_parsed where addr_src_digits != addr_dst_digits; -- almost all records i.e. 1,036,753

select count(*) from eastel.smsc_record_parsed where addr_src_digits = addr_dst_digits; -- only 76

select count(DISTINCT addr_src_digits) from smsc_record_parsed; -- 19,869
select count(*) from smsc_record_parsed; -- 1,036,829

select DISTINCT (message_delivery_status) from smsc_record_parsed;
/* Output:
"message_delivery_status"
"temp_failed"
"success"
"success_esme"
"ocs_rejected"
"failed"
"temp_failed_esme"
"partial"
*/

select * from smsc_record_parsed limit 1;
/* Output:
"id"	"raw_id"	"delivery_date"	"addr_src_digits"	"addr_src_ton"	"addr_src_npi"	"addr_dst_digits"	"addr_dst_ton"	"addr_dst_npi"	"message_delivery_status"	"origination_type"	"message_type"	"orig_system_id"	"message_id"	"dvl_message_id"	"receipt_local_message_id"	"nnn_digits"	"imsi"	"corr_id"	"originator_sccp_address"	"mt_service_center_address"	"orig_network_id"	"network_id"	"mproc_notes"	"msg_parts"	"char_numbers"	"processing_time"	"delivery_delay"	"schedule_delivery_delay"	"delivery_count"	"sms_text"	"reason_for_failure"
"1"	"1"	"2026-02-28 22:38:58"	"22200"	"0"	"1"	"601176009633"	"1"	"1"	"temp_failed"	"SMPP"	"message"	"MCN1"	"32340"	\N	\N	"60181000417"	"502181971083208"	\N	\N	"60181000220"	"200"	"0"	\N	"0"	"0"	\N	\N	\N	\N	"You received 1 misse"	"onDialogTimeout after MtForwardSM Request"
*/


select addr_src_digits, addr_dst_digits, message_delivery_status, 
origination_type, message_type, nnn_digits, imsi, mt_service_center_address, sms_text  
from smsc_record_parsed where addr_src_digits LIKE '60%' limit 100

