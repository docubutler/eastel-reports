/* Notes: 
1. roaming_mccmnc is to be called mccmnc for data (i.e. rat_type = '4G' or '5G'), and to be called VLR GT for 'VO' and 'SM'
2. opposite_number will contain called number for MO, and calling number for MT.
*/

-- Query 1:

SELECT service_type_sub_cd, COUNT(*) 
FROM iot_portal_tb_usage_log_rep 
WHERE rat_type = 'VO' 
GROUP BY service_type_sub_cd;

/* Output:
service_type_sub_cd | COUNT(*)
MO | 17684
MT | 23
*/


-- Query 2:

SELECT COUNT(*) 
FROM iot_portal_tb_usage_log_rep 
WHERE rat_type = 'VO' 
AND act_usage_unit > 0 
AND service_type_sub_cd = 'MT';

/*Output:
COUNT(*)
0
*/

-- Query 3:

SELECT service_type_sub_cd, COUNT(*) AS total_records, 
       SUM(act_usage_unit) AS total_act, 
       SUM(usage_unit) AS total_usage 
FROM iot_portal_tb_usage_log_rep 
WHERE rat_type = 'VO' 
AND service_type_sub_cd = 'MT' 
GROUP BY service_type_sub_cd;

/* Output:
service_type_sub_cd | total_records | total_act | total_usage
MT | 23 | 0.0000000000000000 | 0.0000000000000000
*/


-- Query 4:

SELECT rating_group, COUNT(*) 
FROM iot_portal_tb_usage_log_rep 
WHERE rat_type = 'VO' 
AND service_type_sub_cd = 'MT' 
GROUP BY rating_group;

/* 
Output:
rating_group | COUNT(*)
OFFNET | 23
*/

-- Query 5:

SELECT DISTINCT rating_group 
FROM iot_portal_tb_usage_log_rep;

/*
Output:
rating_group
500002
500015
500008
500010
500018
500006
500003
500001
OFFNET
ONNET
SM
*/

-- Query 6:
-- Check what roaming_destination_id contains:

SELECT DISTINCT roaming_destination_id FROM iot_portal_tb_usage_log_rep; 
-- output:
"roaming_destination_id"
"0"
"18"
"62"
"79"
"81"
"87"
"99"
"103"
"506"
"507"
"510"

-- Query 7: 
-- Check what does rating_group contains:

SELECT DISTINCT rating_group FROM iot_portal_tb_usage_log_rep; 
-- output:
"rating_group"
"500002"
"500015"
"500008"
"500010"
"500018"
"500006"
"500003"
"500001"
"OFFNET"
"ONNET"
"SM"
"500004"

-- Query 8:
-- Check what does rating_group contain for voice data i.e. when rat_type = 'MO':

SELECT DISTINCT rating_group, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO' GROUP BY rating_group;

/*
Output:
"rating_group"	"COUNT(*)"
"OFFNET"	       "20894"
"ONNET"	        "5490"
*/

-- Query 9:
-- Check what does DISTINCT service_type_sub_cd contain:

SELECT DISTINCT service_type_sub_cd FROM iot_portal_tb_usage_log_rep; 

/*
Output:
"service_type_sub_cd"
"N/A"
"MO"
"MT"
*/

-- Query 10:
SELECT DISTINCT service_type_sub_cd, COUNT(*) FROM iot_portal_tb_usage_log_rep GROUP BY service_type_sub_cd; 

/*
Output:
"service_type_sub_cd"	"count(*)"
"N/A"	                     "923240"
"MO"	                     "26527"
"MT"	                     "48"
*/

-- Query 11:
SELECT DISTINCT service_type_sub_cd, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO' GROUP BY service_type_sub_cd; 
-- output: for VO (voice) calls only MO / MT is available
/*
Output:
"service_type_sub_cd"	"COUNT(*)"
"MO"	                     "26356"
"MT"	                     "28"
*/

-- Query 12:
-- similar to query 7, but has count has well

SELECT DISTINCT rating_group, COUNT(*) FROM iot_portal_tb_usage_log_rep GROUP BY rating_group;

/*
Output:
"rating_group"	"count(*)"
"500002"	"332344"
"500015"	"143387"
"500008"	"152898"
"500010"	"9848"
"500018"	"4822"
"500006"	"29213"
"500003"	"183"
"500001"	"14298"
"OFFNET"	"21085"
"ONNET"		"5490"
"SM"		"236241"
"500004"	"6"
*/

-- Query 13:
SELECT DISTINCT roaming_mccmnc FROM iot_portal_tb_usage_log_rep;

/*
Output:
"roaming_mccmnc"
"50218"
"52505"
"23420"
"60180000000502"
"60181000018"
"60181000366"
"60181000031"
"60181000019"
\N
"60181000015"
"60180000000000"
"60180000021111"
"60181000014"
"60181000777"
"52003"
"60181000888"
"6598540006"
"8613746268"
"52501"
"52510"
"8613444239"
"65000000052505"
"84920210064"
"45205"
"8613200562"
"628160291000"
"52004"
"45204"
"6593340087"
"46000"
"8615654538"
"60181000356"
"6598540007"
"65000000052510"
"46001"
"60181000355"
"8615644566"
*/

-- Query 14:
SELECT DISTINCT roaming_mccmnc FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO';

/*
Output:
"roaming_mccmnc"
"60180000000502"
"60181000018"
"60181000019"
"60180000000000"
"60180000021111"
"60181000014"
"60181000015"
"8613746268"
"8613444239"
"65000000052505"
"8613200562"
"628160291000"
"6593340087"
"65000000052510"
*/


-- Query 15:
SELECT DISTINCT roaming_mccmnc, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = 'VO' GROUP BY roaming_mccmnc;
/*
Output:
"roaming_mccmnc"	"count(*)"
"60180000000502"	"25878"
"60181000018"	       "143"
"60181000019"	       "99"
"60180000000000"	"119"
"60180000021111"	"99"
"60181000014"	       "6"
"60181000015"	       "12"
"8613746268"	       "7"
"8613444239"	       "1"
"65000000052505"	"1"
"8613200562"	       "1"
"628160291000"	"11"
"6593340087"	       "6"
"65000000052510"	"1"
*/

-- Query 16:

SELECT DISTINCT rat_type FROM iot_portal_tb_usage_log_rep;
/*
Output:"rat_type"
"4G" -- data
"5G" -- data
"VO" -- voice
"SM" -- sms
\N
*/

-- Query 17:

-- Cecking roaming_mccmnc for data i.e. rat_type = '4G' or '5G'
SELECT DISTINCT roaming_mccmnc, COUNT(*) FROM iot_portal_tb_usage_log_rep WHERE rat_type = '4G' OR rat_type = '5G' GROUP BY roaming_mccmnc;

/*
Output:

"roaming_mccmnc"	"COUNT(*)"
"23420"	"8"
"45204"	"43"
"45205"	"30"
"46000"	"1"
"46001"	"1"
"50218"	"686352" -- Malaysian 502: MY, 18: UMobile, 152: Celcom
"52003"	"37"
"52004"	"5"
"52501"	"55"
"52505"	"449"
"52510"	"18"
*/
