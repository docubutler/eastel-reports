# BUG-003 — Settle cutoff was computed in UTC while `cr_time` is stored in server-local time

| Field | Value |
|---|---|
| Severity | **critical** (sync stalls for hours, then bursts; drives rows into rollover) |
| Status | fix-proposed (code written, not deployed) |
| Reported | 2026-11-19 |
| Components | `postgres-to-mongo-usage-sync`, `postgres-to-mongo-request-sync` |
| Related | [BUG-001](BUG-001-sync-skips-rows-inside-settle-window.md) |

## Summary

Both syncs computed the settle cutoff in Python as
`datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=min_record_age_seconds)`
and compared it against `cr_time`, a `timestamp without time zone` column that is
written in the **database server's local time** (UTC+8, Malaysia). The comparison
was therefore off by the timezone offset: every row looked `offset` hours younger
than it really was, so nothing was eligible until it was `offset + window` old.

With `min_record_age_seconds = 7200` and an 8-hour offset, the effective delay was
**10 hours**. The checkpoint advanced only in bursts, and during the extra 8 hours
rows stayed exposed to the monthly rollover — a plausible contributor to the
218M-row shortfall in `request_logs` and the gaps in `usage_logs`.

## Evidence

Measured on 2026-11-19:

```
UTC now                      : 2026-11-19 16:32
SELECT max(cr_time) FROM iot_portal_tb_usage_log
                             : 2026-11-20 00:32:38   -> exactly UTC + 8h
mongo state checkpoint       : 532,537,656   (last written 2026-11-19 13:19:50 UTC)
last written doc cr_time     : 2026-11-19 11:18:56   (just under the 11:19:50 cutoff)
next rows after the checkpoint:
  532,537,659                : cr_time 2026-11-19 19:15:18
max usage_log_id             : 533,230,266
```

The sync wrote its last batch at 13:19:50 UTC because the cutoff was then
`11:19:50`. The very next rows carry `cr_time 19:15:18`, which stays above the
cutoff until UTC reaches `21:15` — hence a multi-hour stall while the process sat
in its poll loop refreshing its lock (observed: lock refreshed every cycle, state
`updated_at` frozen for 3 hours).

Two sub-observations:

- The jump from `cr_time 11:18:56` to `19:15:18` across three ids is itself an
  id/time inversion — the same precondition described in BUG-001.
- `cr_time` values are consistently ahead of UTC by 8h, so the column is
  server-local (MYT), not UTC. Any consumer that assumes UTC is wrong.

## Why the old code did not catch it

`cr_time` is `timestamp without time zone`, so PostgreSQL performs no conversion
for a client-supplied parameter; the mismatch is silent. Nothing validates that
the client clock and the server clock agree on a timezone.

## Fix applied to the code (waiting on deployment)

Both syncs now let PostgreSQL compute the cutoff from its own clock, in the same
type and reference frame as `cr_time`:

```sql
AND cr_time <= (statement_timestamp()::timestamp) - make_interval(secs => %s)
```

`statement_timestamp()` rather than `now()` on purpose: the sync connection is not
autocommit and stays inside one transaction for the whole run, so `now()` would be
frozen at transaction start and the window would never advance.

## How to verify after deployment

1. Startup log should show the first batch advancing again.
2. On a quiet install, compare a freshly inserted row:

   ```sql
   SELECT now() AS server_now, now()::timestamp AS server_local,
          current_setting('TimeZone') AS tz,
          (SELECT max(cr_time) FROM iot_portal_tb_usage_log) AS max_cr_time;
   ```

   `server_local` should be within seconds of `max_cr_time` once ingestion settles.
3. Confirm the sync never reports `waiting for settlement` for more than
   `min_record_age_seconds` plus normal ingestion delay.

## Open questions

- Is the 8-hour offset a deliberate server configuration (e.g. `TimeZone = Asia/Kuala_Lumpur`)
  or an accident? If the column is later migrated to `timestamptz`, the fix still
  holds, but any other consumer comparing UTC will break.
- Does any report already compensate for the offset? Reports that filter
  `usage_start_time` against dates given as local dates may be correct or doubled
  depending on how the boundaries were chosen.
