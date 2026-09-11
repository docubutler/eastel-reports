## Staging vs Production

For staging env customer_id will be cust_test% and all the rest of the cdrs/data will be considered as Production


## When to consider a record fully complete:
 in iot_portal_tb_request_log table is the req_type column, which currently has the following unique values: [U, T, C, E].

C: Create
U: Update
T: Terminate
E: Event  

C/U/T are used for voice and data, C means the start of data session or voice call;  U means continuing the session and report the usage;  T means session terminated / finished, and usage of consumed will be reported also.

E is used for sending one SMS. 


## Reference

- `report-generation-postgres/QUERY-NOTES.md` — living notes for writing report queries: confirmed tables/columns, how to resolve a subscriber's package, EZ50 plan ids, data caveats, and a running change log. Append new findings there.