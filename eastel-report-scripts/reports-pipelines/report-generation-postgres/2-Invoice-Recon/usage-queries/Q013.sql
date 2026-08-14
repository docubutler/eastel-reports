/*
Copy-paste sample for July 2026:

-- International data destination country cannot be derived from the current usage-log
-- schema because data records have no called-party destination number. This query is
-- intentionally empty until a defensible mapping is available.
SELECT
    CAST(NULL AS text) AS service_type,
    CAST(NULL AS text) AS charge_type,
    CAST(NULL AS text) AS country,
    CAST(NULL AS numeric) AS usage_mbs
WHERE FALSE;
*/

SELECT
    CAST(NULL AS text) AS service_type,
    CAST(NULL AS text) AS charge_type,
    CAST(NULL AS text) AS country,
    CAST(NULL AS numeric) AS usage_mbs
WHERE FALSE;
