# Voice Usage Logs – Key Column Definitions

## Overview
This document explains the key columns used in the voice usage logs dataset.  
The goal is to clearly understand:
- What each field represents
- How it should be interpreted
- How it is used in reconciliation and analysis

---

# 1. msisdn

### Description:
The subscriber’s phone number (SIM/user identifier).

---

# 2. service_type_sub_cd (Call Direction)

### Description:
Indicates whether the call was outgoing or incoming, only applicable for rat_type = 'VO'

 select count(*) from iot_portal_tb_usage_log_rep
    where rat_type = 'SM' and service_type_sub_cd in ('MO', 'MT'); -- returns 0 records as for rat_type = 'SM' the service_type_sub_cd is not effective

### Values:
- `MO` → Mobile Originated (user makes the call)
- `MT` → Mobile Terminated (user receives the call)

### Examples:

MO → User calls someone
MT → Someone calls the user


---

# 3. roaming_destination_id (Subscriber Location)

### Description:
Identifies the network/location where the subscriber is currently connected/latched. Identifies where the SIM is right now.

### Key Rule:
- `87` → Malaysia (Home Network)
- Any other value → Roaming (Abroad)

### Examples:

87 → Subscriber is in Malaysia
103 → Subscriber is roaming (e.g. other than Malaysia)


### Important Note:
This field does **NOT** indicate:
- Call origin
- Call destination

It only shows:
> Subscriber’s current network location

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

---

# 4. roaming_mccmnc (Operator Code)

### Description:
The Mobile Country Code + Mobile Network Code of the network the subscriber is connected to.
Malaysian 502: MY, 18: UMobile, 152: Celcom

for rat_type = 'VO' and 'SM' roaming_mccmnc contains the GT, for data it contains the mccmnc 

### Plain English:
> “Which telecom network is the SIM using?”

### Examples:

50218 → Malaysia operator
23410 → UK operator

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


---

# 5. opposite_number (Other Party)

### Description:
The phone number of the other party involved in the call. opposite_number will contain called number for MO, and calling number for MT.



---

# 6. IDD Classification (Derived Logic)

### Rule:

If number starts with '60' → LOCAL (Malaysia)
Else → IDD (International)


### Examples:

| opposite_number | Type |
|----------------|------|
| 60123456789    | LOCAL |
| 447911123456   | IDD |

---

# 7. rating_group (Charging Type)

### Description:
Indicates how the call is categorized for billing.

### Relevant Values (Voice):
- `ONNET` → Same network
- `OFFNET` → Other operator (OLO)

### Examples:

ONNET → Same telco call
OFFNET → Call to another telco


---

# 8. act_usage_unit (Actual Usage)

### Description:
Actual duration of the call recorded by the network in seconds.

### Unit:
Usually in **seconds**

### Example:

Call duration = 2 minutes
act_usage_unit = 120


---

# 9. usage_unit (Billed Usage)

### Description:
Duration used for billing might be more than act_usage_unit. Will depend upon the buckets etc.

### Plain English:
> “What the user is charged for”

### Example (Rounded Billing):

| Actual | Billed |
|--------|--------|
| 70 sec | 120 sec |


act_usage_unit = 70
usage_unit = 120


---
# 10. rat_type

### Description:
Determines if its a voice (VO), SMS (SM) or Data (4G, 5G) record

SELECT DISTINCT rat_type FROM iot_portal_tb_usage_log_rep;
/*
Output:"rat_type"
"4G" -- data
"5G" -- data
"VO" -- voice
"SM" -- sms
\N
*/

# Key Difference

| Field | Meaning |
|------|--------|
| act_usage_unit | Real usage |
| usage_unit     | Charged usage |

---

# Call Interpretation Model (VERY IMPORTANT)

To understand any call, use these three fields together:

| Field | Meaning |
|------|--------|
| service_type_sub_cd | Call direction (MO/MT) |
| roaming_destination_id | Subscriber location |
| opposite_number | Call destination/origin |


---

# Example Scenario

### Scenario 1 voice MT Call:
- MT Call (MT call's cdrs will only be recorded in system when eastel subscriber is roaming i.e. not in MY)
- Subscriber is roaming in HK
- Someone in Pakistan calls them

rat_type = 'VO'
service_type_sub_cd = MT
roaming_destination_id = 0 and 435 (some raoaming destination ID assigned by MB to HK), since it will originate multiple IDPs, for 0 it means its a CS call, for non-zero it would mean its s8HR call (the 0 part needs to be confirmed by MB)
roaming_mccmnc = fake GT for roaming_destination_id != 0 and != 87, and actual VLR GT when roaming_destination_id = 0
opposite_number = 923xxx, this will be the calling number in case of MT, not the destination subscriber number.

### Scenario 2 voice MO Call (Domestic):
- MO Call (Domestic)
- Subscriber is in MY
- Subscriber is calling someone in MY

rat_type = 'VO'
service_type_sub_cd = MO

opposite_number = called party number

raoming_destination_id = 87
roaming_mccmnc = VLR GT

### Scenario 3 voice MO Call (IDD):
- MO Call (IDD)
- Subscriber is in MY
- Subscriber is calling someone who is not in MY

rat_type = 'VO'
service_type_sub_cd = MO
raoming_destination_id != 87
roaming_mccmnc = VLR GT
opposite_number = called party number which ofcourse shouldn't be MY number


## Report extraction
Following reports are to be extracted based on the above data:
1. MO calls group by roaming and non-roaming (raoaming/non-roaming to be identified through roaming_destination_id being 87 or not)
then by VLR GT (VLR GT not required in group by for non-roaming subs. VLR GT will determin where is the subscriber roaming)
then by oppostie number's CC, first segregate by MY (60) and non-MY (non-60)
then breakup of non-MY (non-60)

