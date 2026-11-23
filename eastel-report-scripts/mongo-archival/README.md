# Mongo Collection Archival

Moves documents older than a cut-off out of a live MongoDB collection into an
archive collection, in batches, with resumable progress.

Built for `usage_logs -> usage_archive_logs` and
`request_logs -> request_archive_logs`, but any collection that has a uniquely
indexed id field works.

## Safety model

Nothing is deleted before it exists in the archive. Every batch:

1. reads up to `batch_size` documents from the live collection
2. upserts them into the archive by `_id` (so a replay is idempotent)
3. **verifies** that every `_id` is now present in the archive
4. only then deletes those exact `_id`s from the live collection
5. saves the checkpoint (`last_archived_id`)

Any interruption is safe: a crash before the delete leaves documents duplicated
in both collections, and the next run re-copies then deletes them. A crash after
the delete leaves the checkpoint slightly behind, and the next run simply finds
fewer documents. Deletes are always by explicit `_id` list, never by range.

If step 3 fails, the run aborts and **nothing is deleted** for that batch.

## Configuration

Copy the sample and fill in the URI:

```powershell
Copy-Item config-sample.yml config.yml
```

```yaml
mongo:
  uri: ""
  database: "eastel-data"

archive:
  batch_size: 5000
  max_documents_per_run: 0        # 0 = unlimited
  state_collection: "collection_archive_state"
  lock_timeout_seconds: 3600
  assume_yes: false               # true skips the confirmation prompt

collections:
  - source: "usage_logs"
    target: "usage_archive_logs"
    id_field: "usage_log_id"
    time_field: "cr_time"
    before_date: "2026-10-01"
```

Per collection:

- `id_field` — the uniquely indexed field that drives the batching.
- `time_field` — the timestamp used by `before_date`. Defaults to `cr_time`.
- `before_date` — archive documents older than this date. Resolved **once** to an
  id boundary and stored, so re-runs reuse the same cut-off.
- `max_id` — explicit id cut-off, for when you already know the boundary. Wins
  over `before_date`.

## Why the id field drives it and not the date

`cr_time` has no index, so a date filter on every batch is a collection scan that
gets slower as the collection grows. `usage_log_id` / `request_log_id` are
uniquely indexed, so bounding by id is an index range scan and the delete is
exact. A configured `before_date` is only used to resolve the id boundary once,
and then as a guard (`cr_time < before_date`) so an inverted timestamp can never
cause a too-recent document to be archived.

Note the consequence: id order and `cr_time` order do not always agree, so a
document with an old timestamp but a high id stays in the live collection. That is
deliberate — archiving too-new data would break reports.

## Run

```powershell
# see what would move, change nothing
py .\mongo_collection_archiver.py --dry-run

# copy indexes from live to archive once, before the first move
py .\mongo_collection_archiver.py --ensure-indexes --dry-run

# move, with the interactive confirmation
py .\mongo_collection_archiver.py

# unattended
py .\mongo_collection_archiver.py --yes
```

Useful options:

- `--only usage_logs` — one collection from the config.
- `--max-id 481155392` — explicit id cut-off.
- `--before-date 2026-10-01` — override the configured date.
- `--max-documents 100000` — cap this run; re-run to continue.
- `--status` — stored progress plus live and archive document counts.
- `--verify` — shows live/archive counts at the stored cut-off and warns if
  documents at or below it are still in the live collection.
- `--reset-state` — forget progress and the resolved cut-off.
- `--yes` — skip the confirmation prompt.

Press Ctrl+C at any time; re-running the same command resumes from the checkpoint.

## Locking

Each `source->target` pair takes its own lock in the state collection
(`lock::archive::<source>-><target>`), so the two collections can run in parallel
and the archiver does not collide with the Postgres-to-Mongo syncs. Archiving only
touches ids at or below the cut-off, which the syncs have already passed.

## Progress and state

State lives in `collection_archive_state`:

```
_id: "usage_logs->usage_archive_logs"
last_archived_id: 481155392     # progress
cutoff_id: 481155392            # resolved boundary
before_date: "2026-10-01T00:00:00"
```

## Reports will not see archived documents

Reports query `usage_logs` and `request_logs` **by name**. Once documents move,
those reports silently return less data. Before archiving anything a report still
needs, create a view that reads both collections:

```js
db.createView("usage_logs_all", "usage_logs", [
  { $unionWith: { coll: "usage_archive_logs" } }
])
```

and point the report configuration at `usage_logs_all`. The archiver deliberately
does not create these views; run the command above (or ask for a follow-up) when
you are ready.

## Sizing

Roughly `batch_size x average document size` is held in memory per batch. At
5,000 documents of ~2 KB the archiver reads and writes ~10 MB per batch and
typically sustains several thousand documents per second, so ~100M documents is a
few hours. Raise `batch_size` only if the host has memory to spare.
