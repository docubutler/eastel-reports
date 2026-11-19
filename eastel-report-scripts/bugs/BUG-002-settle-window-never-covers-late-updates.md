# BUG-002 — Settle window delays the only copy, so late updates are never synced

| Field | Value |
|---|---|
| Severity | **high** (stale data in reports, silent) |
| Status | open |
| Reported | 2026-11-17 |
| Components | `postgres-to-mongo-usage-sync`, `postgres-to-mongo-request-sync` |
| Related | [BUG-001](BUG-001-sync-skips-rows-inside-settle-window.md) |

## Summary

`min_record_age_seconds` exists to let a row settle before it is copied, on the
assumption that the row may still change shortly after insert. But the sync copies
each row **exactly once**: the checkpoint only moves forward
(`WHERE id > checkpoint`), and nothing ever revisits an id that has already been
copied.

So the settle window only delays the single copy. If a row is updated after that
copy — or even before it, but again afterwards — MongoDB keeps the old values
forever, because the sync will never read that id again.

## Evidence in code

Request sync, `postgres-to-mongo-request-sync/postgres_to_mongo_request_log_sync.py`:

- `:409` `fetch_rows_with_min_age()` — the only fetch path used by `sync_once`
- `:421` `AND cr_time <= %s` — the age gate
- `:467` checkpoint derived from fetched rows, monotonically increasing
- `:484` `save_last_synced_id(...)`

Usage sync, `postgres-to-mongo-usage-sync/postgres_to_mongo_usage_sync.py`:
`:461`, `:473`, `:552`, `:574` — identical structure.

There is no `up_time`-based pass, no re-read of recent ids, and no "dirty" set.

## Why this matters

The source tables carry an `up_time` column that changes when a row is updated
(the `backfill_request_logs.py` tool documents this: it recommends repairing stale
rows by `up_time` precisely because rows are updated after insert). The main sync
never uses `up_time`, so those updates never reach MongoDB through it.

The practical result: rows copied inside a settling state permanently carry
stale values, and any report reading them is wrong with no indication.

## Suggested fix (not implemented)

Add a second, time-based pass that re-reads recently changed rows instead of
relying on a delay:

```sql
SELECT * FROM {source_table}
WHERE up_time >= %(window_start)s
  AND up_time <  %(window_end)s
ORDER BY up_time ASC, id ASC
```

run on a rolling window (for example the last 24-48 hours, overlapping each run),
upserting by id. This gives idempotent correction of updates and makes the settle
window meaningful instead of lossy. The same `up_time` window mechanism already
exists in `request-log-backfill/backfill_request_logs.py` (`--mode time
--time-field up_time`) and can be reused rather than written from scratch.

Alternative: drop `min_record_age_seconds` from the primary copy path (copy every
row immediately, per BUG-001 option 1) and let the rolling `up_time` pass handle
corrections.

## Open questions

- Does `iot_portal_tb_usage_log` actually update rows after insert (does `up_time`
  ever differ from `cr_time`)? If never, usage-side impact is limited to BUG-001.
  Check with:

  ```sql
  SELECT count(*) FROM public.iot_portal_tb_usage_log WHERE up_time <> cr_time;
  SELECT count(*) FROM public.iot_portal_tb_request_log WHERE up_time <> cr_time;
  ```

- How far behind is MongoDB for rows that were updated in place? Needs a comparison
  of a sample of ids against both sources.
