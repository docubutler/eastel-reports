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
Indicates whether the call was outgoing or incoming.

### Values:
- `MO` → Mobile Originated (user makes the call)
- `MT` → Mobile Terminated (user receives the call)

### Examples:

MO → User calls someone
MT → Someone calls the user


---

# 3. roaming_destination_id (Subscriber Location)

### Description:
Identifies the network/location where the subscriber is currently connected/latched. Ideentifies where the SIM is right now.

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

---

# 4. roaming_mccmnc (Operator Code)

### Description:
The Mobile Country Code + Mobile Network Code of the network the subscriber is connected to.

### Plain English:
> “Which telecom network is the SIM using?”

### Examples:

50218 → Malaysia operator
23410 → UK operator


---

# 5. opposite_number (Other Party)

### Description:
The phone number of the other party involved in the call.

### Plain English:
> “Who is the user talking to?”

### Examples:

60123456789 → Malaysia number
447911123456 → UK number


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
Actual duration of the call recorded by the network.

### Plain English:
> “How long did the call really last?”

### Unit:
Usually in **seconds**

### Example:

Call duration = 2 minutes
act_usage_unit = 120


---

# 9. usage_unit (Billed Usage)

### Description:
Duration used for billing after applying charging rules.

### Plain English:
> “What the user is charged for”

### Example (Rounded Billing):

| Actual | Billed |
|--------|--------|
| 70 sec | 120 sec |


act_usage_unit = 70
usage_unit = 120


---

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

### Scenario:
- Subscriber is roaming in UK
- Someone in Malaysia calls them


service_type_sub_cd = MT
roaming_destination_id = 103
opposite_number = 60123456789


### Interpretation:

| Element | Meaning |
|--------|--------|
| Subscriber location | UK |
| Call direction | Incoming |
| Call origin | Malaysia |
| Call destination | UK |

---

# Final Mental Model

Think of the fields like this:

- **roaming_destination_id** → “Where am I?”
- **opposite_number** → “Who am I talking to?”
- **service_type_sub_cd** → “Am I calling or receiving?”

---

# One-Line Summary

> This dataset tracks subscriber activity — showing where the user is, who they interact with, and how long the interaction lasted — not the full telecom routing path.