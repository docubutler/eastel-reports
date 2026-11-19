# BUG-001 — Sync permanently skips rows excluded by the settle window

| Field | Value |
|---|---|
| Severity | **critical** (silent, permanent data loss) |
| Status | fix-proposed (code written, not deployed) |
| Reported | 2026-11-17 |
| Components | `postgres-to-mongo-usage-sync`, `postgres-to-mongo-request-sync` |
| Reported by | Shoaib |
| Introduced by | `4f76703 Add feature to sync postgres tables with records older then specific time and added backdil fix logic` |

## Summary

Both sync scripts filter source rows with `cr_time <= now() - min_record_age_seconds`
(the "settle window", configured as `7200` seconds = 2 hours) but then advance the
checkpoint to the **highest id among the rows that passed the filter**. Any row
that was excluded by the age filter and whose id is lower than that new checkpoint
is never revisited, because the next query asks for `id > checkpoint`.

The row is therefore lost from MongoDB permanently and silently: no error, no log
line, and no marker. The settle window was meant to delay a row until it stopped
changing; in practice it can drop the row instead.

## Where the defect lives

### Usage sync

`eastel-report-scripts/import-to-mongo/postgres-to-mongo/postgres-to-mongo-usage-sync/postgres_to_mongo_usage_sync.py`

- `:461` `fetch_rows_with_min_age()`
- `:473` `AND cr_time <= %s` — rows newer than the settle window are excluded
- `:478` `cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_record_age_seconds)`
- `:552` `max_usage_log_id = max(max_usage_log_id, usage_log_id)` — derived from fetched rows only
- `:574` `save_last_synced_id(...)` — checkpoint becomes that maximum

### Request sync

`eastel-report-scripts/import-to-mongo/postgres-to-mongo/postgres-to-mongo-request-sync/postgres_to_mongo_request_log_sync.py`

- `:409` `fetch_rows_with_min_age()`
- `:421` `AND cr_time <= %s`
- `:426` `cutoff = datetime.now() - timedelta(seconds=min_record_age_seconds)`
- `:467` `max_request_log_id = max(max_request_log_id, request_log_id)`
- `:484` `save_last_synced_id(...)`

Both are the same shape:

```sql
SELECT *
FROM {source_table}
WHERE usage_log_id > %(checkpoint)s
  AND cr_time <= %(cutoff)s          -- rows inside the settle window are invisible
ORDER BY usage_log_id ASC
LIMIT %(batch_size)s
```

```python
max_id = max(row_id for row in rows)   # only counts rows that passed the filter
save_last_synced_id(max_id)            # everything below max_id is now "done"
```

## When rows are lost

Loss needs an **age inversion**: a row with a *high* id but an *old* `cr_time`
while lower ids are still *inside* the settle window. Then the query returns the
older-dated higher ids, and the checkpoint jumps over the young lower ids.

Sources of inversion seen in this system:

- `cr_time` is not always `CURRENT_TIMESTAMP`. The CDR importers take `cr_time`
  from the input file (`cdrs-to-postgres-request-logs-import.py` maps it from a
  CSV column), so a file loaded late carries old timestamps with new ids.
- Bulk/backfill loads and replays insert historical rows with new ids.
- Any producer that sets `cr_time` explicitly instead of relying on the default.

Note that a *purely* monotonic table is safe: young rows sit above the checkpoint,
the fetch returns nothing, the loop breaks, and they are picked up after they age.
The bug only bites when id order and `cr_time` order disagree.

## Evidence

### Request logs — confirmed loss with a matching source

The live table was rolled over on 2026-10-01 into
`iot_portal_tb_request_log_old20260930`, and the sync only reads the live table:

```sql
-- archive: the historical rows
SELECT count(*) FROM public.iot_portal_tb_request_log_old20260930
WHERE request_log_id BETWEEN 459028531 AND 460110283;   -- 1,081,599

-- live table: rows are gone
SELECT count(*) FROM public.iot_portal_tb_request_log
WHERE request_log_id BETWEEN 459028531 AND 460110283;   -- 0

-- archive totals for the whole rolled-over range
SELECT count(*) FROM public.iot_portal_tb_request_log_old20260930;
-- 340,575,434 rows, ids 284,481,998 .. 625,114,047
```

MongoDB `eastel-data.request_logs`, same id range:

```js
db.request_logs.countDocuments({
  request_log_id: { $gte: NumberDecimal("284481998"), $lte: NumberDecimal("625114047") }
})   // 122,470,002   -> 218,105,432 rows missing (64%)
```

Gaps are blocky, not random, and the edges bracket a short time window:

```
382,813,041 -> 383,171,235   hole    358,194 ids
459,028,530 -> 460,110,284   hole  1,081,754 ids  (cr_time Aug 14 01:01 -> Aug 13 23:21)
542,823,588 -> 543,648,117   hole    824,529 ids
572,017,812 -> 573,221,607   hole  1,203,795 ids
623,708,181 -> 625,114,048   hole  1,405,867 ids  (rollover boundary)
```

The 1,081,754-id hole sits inside ~1h40m of traffic (~649k ids/hour), which is
the same order as the 2-hour settle window — consistent with a block of rows being
excluded while the checkpoint stepped over them.

`request_synced` has **0** markers in that range and all 2,000 sampled markers
have a matching `request_logs` document, so the backfill marker collection is not
masking anything: the sync genuinely never recorded those rows.

### Usage logs — same defect, impact indicated

`eastel-data.usage_logs`: 210,021,518 docs, ids 31,438,253 .. 526,569,101,
span 495,130,849 -> density **42.4%**. Density collapses to 0/1000 in three
sampled windows (237M, 279M, 320M), and gaps with backwards `cr_time` at the
edges appear in the same way as the request-log gaps:

```
340,645,800 (cr_time 2026-09-03 22:50:21) -> 341,213,622 (cr_time 2026-09-02 17:28:44)  hole 567,822
382,131,940 (cr_time 2026-09-22 19:18:55) -> 382,164,431 (cr_time 2026-09-22 19:18:03)  hole  32,491
```

In both cases the id increases while `cr_time` moves *backwards*, i.e. the skipped
block has timestamps between the two edges — the signature this bug predicts.

## Impact

- Reports built from MongoDB under-count and miss subscribers/records with no error.
- The loss is silent: the sync logs "synced N rows" and advances normally.
- It compounds with monthly table rollovers: once the source table is replaced,
  rows the sync never copied cannot be recovered from the live table at all
  (they must be re-read from the archive table).

## Reproduction (no writes)

Verified by simulation of the exact query predicate and checkpoint rule:

1. Seed a source table with ids 1..3 where id 1 and 2 have `cr_time = now()`
   and id 3 has `cr_time = now() - 3 hours`.
2. Run the sync with `min_record_age_seconds = 7200`.
3. First batch returns only id 3 (ids 1 and 2 fail the age filter). Checkpoint
   becomes 3.
4. Ids 1 and 2 are never fetched again, even after they age past the window.

Observed result of the simulation:

```
rows in source   : [1, 2, 3]
rows synced      : [3]
final checkpoint : 3
LOST             : [1, 2]
```

Control case — a table where `cr_time` rises with the id (the normal case) loses
nothing: the young row stays above the checkpoint, the fetch returns no rows, the
loop exits, and the row is copied on a later cycle once it ages.

```sql
-- Direct check on any live source table: are id order and cr_time order aligned?
SELECT count(*) AS inversions
FROM (
    SELECT cr_time < lag(cr_time) OVER (ORDER BY request_log_id) AS inverted
    FROM public.iot_portal_tb_request_log
    WHERE request_log_id > 400000000
    LIMIT 2000000
) t
WHERE inverted;
```

## Suggested fix (not implemented)

> **Update 2026-11-19:** implemented in both sync scripts as the "settled prefix"
> design — see *Fix implemented* below. BUG-003 was fixed at the same time.

Pick one; all three remove the "checkpoint jumps over unseen rows" behaviour:

1. **Advance the checkpoint only over a contiguous, complete prefix.** Stop the
   batch at the first row whose `cr_time` is inside the settle window, instead of
   filtering those rows out of the result set. Simple and preserves the intent:

   ```sql
   WHERE id > %(checkpoint)s
     AND cr_time <= %(cutoff)s
     AND NOT EXISTS (
       SELECT 1 FROM {source_table} b
       WHERE b.id > %(checkpoint)s AND b.id <= {source_table}.id
         AND b.cr_time > %(cutoff)s
     )
   ```

   Cheaper variant: fetch `WHERE id > checkpoint ORDER BY id LIMIT n` **without**
   the age filter, and stop writing at the first row younger than the cutoff,
   setting the checkpoint to the id just before it.

2. **Two-phase copy.** Copy rows regardless of age, then re-read recently written
   ids on the next cycle (age filter used only for the re-read), which also fixes
   BUG-002.

3. **Track a high-water mark by id *and* a pending set.** Keep the checkpoint at
   `min(id)` of anything still inside the settle window; store the deferred ids
   and revisit them.

Whichever option is chosen, the same change is needed in **both** sync scripts,
and the MSISDN backfill (`postgres-to-mongo-msisdn-backfill`) already applies no
age filter, so it is unaffected.

## Fix implemented (2026-11-19, awaiting deployment)

Option 1, the "settled prefix", in both sync scripts:

- `fetch_settled_rows()` — `SELECT * WHERE id > checkpoint AND cr_time <= (statement_timestamp()::timestamp) - make_interval(secs => window) ORDER BY id LIMIT batch`
- `find_settle_barrier()` — `SELECT min(id) ... WHERE id > checkpoint AND id <= max_fetched AND cr_time > cutoff`, the first row that is still settling
- `trim_to_settled_prefix()` — drops fetched rows at or above the barrier; the
  checkpoint becomes the max id of what remains, and never moves backwards

Result: the checkpoint only ever advances over a contiguous run of settled rows.
When the sync is caught up, the fetch returns just the rows that have crossed the
window, so only those are written regardless of `batch_size`, and the log shows
`blocked_at=<id>` while it waits.

The cutoff is computed by PostgreSQL (see
[BUG-003](BUG-003-settle-cutoff-timezone-mismatch.md)), which was the second half
of the problem: the client-side UTC cutoff was 8 hours out of step with `cr_time`.

Verified by simulation (fake PG/Mongo) for: nothing settled, all settled, barrier
mid-batch, barrier at the first id, resume at a barrier, continuation after the
barrier ages, caught-up steady state with `batch_size=2000`, multi-batch backlog,
and checkpoint monotonicity. Not yet verified against the live database.

## Open questions

- How much of the 218M request-log shortfall comes from this bug versus rows that
  were deleted/rolled over before the sync reached them? Needs a time-based
  comparison of MongoDB against the archive table, e.g.:

  ```sql
  SELECT count(*) FROM public.iot_portal_tb_request_log_old20260930
  WHERE cr_time >= '2026-08-01' AND cr_time < '2026-09-01';
  ```

  versus `db.request_logs.countDocuments({cr_time: {$gte: ISODate("2026-08-01"), $lt: ISODate("2026-09-01")}})`.
- Same comparison for `usage_logs` against
  `iot_portal_tb_usage_log` / `iot_portal_tb_usage_log_old20260930`, to quantify
  the usage-side loss separately from source-table gaps.
- Do any producers insert explicit `cr_time` values (CDR importers do) in a way
  that creates the age inversion? This determines how often the bug actually fires.

## Related

- [BUG-002](BUG-002-settle-window-never-covers-late-updates.md) — the settle window
  never causes updates to be re-read, so "let rows settle" never worked as intended.
