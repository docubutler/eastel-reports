"""Move old documents from a live MongoDB collection into an archive collection.

The cut-off is driven by the collection's indexed id field (``usage_log_id`` /
``request_log_id``); a ``before_date`` can be supplied instead and is resolved once
to an id boundary. Nothing is ever deleted before it exists in the archive: each
batch is copied, verified and only then removed from the live collection, so an
interrupted run resumes safely and a replay is idempotent.

Reports that query the live collection by name will no longer see archived
documents. Create a view that unions live and archive before archiving data that
reports still need.
"""

import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from bson.decimal128 import Decimal128
from pymongo import MongoClient, ReplaceOne
from pymongo.errors import BulkWriteError, DuplicateKeyError, OperationFailure, PyMongoError


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
DEFAULT_STATE_COLLECTION = "collection_archive_state"
DEFAULT_BATCH_SIZE = 5000
DEFAULT_LOCK_TIMEOUT_SECONDS = 3600
LOCK_LABEL = "archive"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--only", default="", help="Run only this source collection.")
    parser.add_argument("--batch-size", type=int, default=0, help="Override archive.batch_size.")
    parser.add_argument(
        "--max-id",
        type=int,
        default=None,
        help="Archive documents with id <= this value. Overrides before_date.",
    )
    parser.add_argument(
        "--before-date",
        default="",
        help="Archive documents older than YYYY-MM-DD. Resolved to an id boundary once.",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=None,
        help="Stop after moving this many documents per collection (0 = unlimited).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would move. Deletes nothing.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt before deleting.")
    parser.add_argument("--status", action="store_true", help="Print stored progress and exit.")
    parser.add_argument("--verify", action="store_true", help="Compare archive and live counts and exit.")
    parser.add_argument(
        "--ensure-indexes",
        action="store_true",
        help="Copy the live collection's index definitions onto the archive collection.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Forget stored progress and resolved cut-offs before starting.",
    )
    return parser.parse_args()


def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}. Copy config-sample.yml first.")
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("Config must contain a YAML mapping.")
    return config


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not uri:
        raise ValueError("Missing MongoDB setting: set MONGO_URI or mongo.uri.")
    return MongoClient(str(uri), serverSelectionTimeoutMS=20000)


def as_int(value: Any) -> int:
    if isinstance(value, Decimal128):
        return int(value.to_decimal())
    return int(value)


def parse_date(text: str) -> datetime:
    """Naive datetime, matching how cr_time values are stored."""
    return datetime.fromisoformat(text.strip())


def state_key(source: str, target: str) -> str:
    return f"{source}->{target}"


def lock_key(source: str, target: str) -> str:
    return f"lock::{LOCK_LABEL}::{state_key(source, target)}"


def acquire_lock(state_collection, source: str, target: str, owner_id: str, timeout: int) -> None:
    key = lock_key(source, target)
    now = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(now.timestamp() + timeout, tz=timezone.utc)
    try:
        doc = state_collection.find_one_and_update(
            {
                "_id": key,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"owner_id": owner_id},
                    {"expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "owner_id": owner_id,
                    "source": source,
                    "target": target,
                    "updated_at": now,
                    "expires_at": expires,
                }
            },
            upsert=True,
            return_document=True,
        )
    except DuplicateKeyError as exc:
        raise RuntimeError(
            f"Another archiver run already holds the lock for {source}->{target}."
        ) from exc
    if not doc or doc.get("owner_id") != owner_id:
        raise RuntimeError(f"Another archiver run already holds the lock for {source}->{target}.")


def refresh_lock(state_collection, source: str, target: str, owner_id: str, timeout: int) -> None:
    now = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(now.timestamp() + timeout, tz=timezone.utc)
    result = state_collection.update_one(
        {"_id": lock_key(source, target), "owner_id": owner_id},
        {"$set": {"updated_at": now, "expires_at": expires}},
    )
    if result.matched_count != 1:
        raise RuntimeError("Archive lock was lost during execution.")


def release_lock(state_collection, source: str, target: str, owner_id: str) -> None:
    state_collection.delete_one({"_id": lock_key(source, target), "owner_id": owner_id})


def load_state(state_collection, key: str) -> dict[str, Any] | None:
    return state_collection.find_one({"_id": key})


def save_state(state_collection, key: str, source: str, target: str, **fields: Any) -> None:
    fields.update(
        {"source": source, "target": target, "updated_at": datetime.now(timezone.utc)}
    )
    state_collection.update_one({"_id": key}, {"$set": fields}, upsert=True)


def resolve_cutoff_id(
    collection,
    id_field: str,
    time_field: str,
    before_date: datetime,
) -> int | None:
    """Highest id whose time_field is older than before_date.

    A plain ``find(...).sort(id).limit(1)`` is not usable here: with no index on
    time_field, MongoDB can only satisfy it by reading every document above the
    boundary, which is most of the collection. Binary search over the id index
    costs one document read per probe (about 30 for 200M ids) and relies on time
    rising roughly with id — after which the exact ``time_field`` guard applied
    during the move keeps the result safe even where the two disagree.

    The search converges exactly: stopping short would leave eligible documents in
    the live collection, which then look like an incomplete run.
    """
    first = collection.find_one({}, {id_field: 1}, sort=[(id_field, 1)])
    last = collection.find_one({}, {id_field: 1}, sort=[(id_field, -1)])
    if not first or not last:
        return None
    lo = as_int(first[id_field]) - 1  # lo is always known to be below the boundary
    hi = as_int(last[id_field])       # hi is always at or above it

    def probe(log_id: int) -> tuple[int, Any] | None:
        """First document at or above log_id."""
        doc = collection.find_one(
            {id_field: {"$gte": log_id}},
            {id_field: 1, time_field: 1},
            sort=[(id_field, 1)],
        )
        if not doc:
            return None
        return as_int(doc[id_field]), doc.get(time_field)

    lowest = probe(lo + 1)
    if lowest is None:
        return None
    highest = probe(hi)
    # Everything is old enough: the whole collection qualifies.
    if highest is not None and (highest[1] is not None and highest[1] < before_date):
        return hi
    # The oldest document is already too new: nothing qualifies.
    if lowest[1] is None or lowest[1] >= before_date:
        return None

    while hi - lo > 1:
        mid = (lo + hi) // 2
        found = probe(mid)
        if found is None:
            hi = mid  # no documents at or above mid, so the boundary is lower
            continue
        doc_id, value = found
        if value is not None and value < before_date:
            lo = doc_id  # this document qualifies, so nothing above it is the boundary
        else:
            hi = mid  # no qualifying document at or above mid
    return lo


def ensure_archive_indexes(live, archive) -> list[str]:
    """Recreate the live collection's secondary indexes on the archive collection."""
    created = []
    for name, info in live.index_information().items():
        if name == "_id_":
            continue
        options: dict[str, Any] = {"name": name}
        for option in ("unique", "sparse", "partialFilterExpression", "expireAfterSeconds"):
            if option in info:
                options[option] = info[option]
        archive.create_index(info["key"], **options)
        created.append(name)
    return created


def describe_bulk_error(exc: BulkWriteError) -> str:
    details = exc.details or {}
    errors = details.get("writeErrors") or []
    if not errors:
        return f"archive bulk write failed: {details}"
    first = errors[0]
    return (
        f"{len(errors)} archive write error(s); first: code={first.get('code')} "
        f"index={first.get('index')} keyValue={first.get('keyValue')} "
        f"errmsg={first.get('errmsg')}"
    )


def archive_collection(
    live,
    archive,
    state_collection,
    source: str,
    target: str,
    id_field: str,
    time_field: str,
    cutoff_id: int,
    before_date: datetime | None,
    batch_size: int,
    max_documents: int,
    owner_id: str,
    lock_timeout_seconds: int,
) -> tuple[int, int]:
    """Move documents with id <= cutoff_id. Returns (moved, batches)."""
    key = state_key(source, target)
    state = load_state(state_collection, key) or {}
    checkpoint = as_int(state.get("last_archived_id") or 0)
    moved = 0
    batches = 0

    while True:
        refresh_lock(state_collection, source, target, owner_id, lock_timeout_seconds)

        query: dict[str, Any] = {
            id_field: {"$gt": checkpoint, "$lte": cutoff_id},
        }
        # Documents above the id boundary are left alone; this guard only ever makes
        # the selection narrower, so it can never archive something too recent.
        if before_date is not None:
            query[time_field] = {"$lt": before_date}

        docs = list(
            live.find(query).sort(id_field, 1).limit(batch_size)
        )
        if not docs:
            break

        batch_max = as_int(docs[-1][id_field])
        if max_documents and moved + len(docs) > max_documents:
            docs = docs[: max_documents - moved]
            batch_max = as_int(docs[-1][id_field])
        if not docs:
            break

        ids = [doc["_id"] for doc in docs]
        operations = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs]
        try:
            archive.bulk_write(operations, ordered=False)
        except BulkWriteError as exc:
            raise RuntimeError(describe_bulk_error(exc)) from exc

        archived = archive.count_documents({"_id": {"$in": ids}})
        if archived != len(ids):
            raise RuntimeError(
                f"archive verification failed for ids {ids[0]}..{ids[-1]}: "
                f"expected {len(ids)}, found {archived}. Nothing was deleted."
            )

        deleted = live.delete_many({"_id": {"$in": ids}}).deleted_count
        if deleted != len(ids):
            raise RuntimeError(
                f"deleted {deleted} of {len(ids)} documents from {source}; "
                f"archive already holds them, so a re-run is safe."
            )

        checkpoint = batch_max
        moved += len(ids)
        batches += 1
        save_state(
            state_collection,
            key,
            source,
            target,
            last_archived_id=checkpoint,
            cutoff_id=cutoff_id,
        )
        print(
            f"  moved {len(ids):>6,} docs  ids ...{batch_max:,}  "
            f"total={moved:,}  batches={batches}",
            flush=True,
        )

        if max_documents and moved >= max_documents:
            print(f"  stopped at --max-documents {max_documents:,}", flush=True)
            break
        if len(ids) < batch_size:
            break

    return moved, batches


def resolve_cutoff(
    live,
    state_collection,
    key: str,
    source: str,
    target: str,
    id_field: str,
    time_field: str,
    cli_max_id: int | None,
    entry_max_id: int | None,
    before_date: datetime | None,
    persist: bool = True,
) -> tuple[int | None, datetime | None]:
    """Pick the id cut-off for this run.

    Preference order: explicit CLI --max-id, explicit config max_id, a stored
    cut-off that still matches the configured before_date, a freshly resolved
    before_date. The resolved value is stored so re-runs use the same boundary.
    """
    date_text = before_date.isoformat() if before_date else None
    state = load_state(state_collection, key) or {}
    stored_cutoff = state.get("cutoff_id")
    stored_date = state.get("before_date")

    if cli_max_id is not None:
        return cli_max_id, before_date
    if entry_max_id:
        return int(entry_max_id), before_date
    if stored_cutoff is not None and stored_date == date_text:
        return as_int(stored_cutoff), before_date
    if before_date is None:
        return None, None

    resolved = resolve_cutoff_id(live, id_field, time_field, before_date)
    if resolved is None:
        return None, before_date
    if persist:
        save_state(
            state_collection,
            key,
            source,
            target,
            cutoff_id=resolved,
            before_date=date_text,
        )
    return resolved, before_date


def print_status(state_collection, db, config: dict[str, Any]) -> None:
    print("stored progress:")
    found = False
    for doc in state_collection.find({}):
        if str(doc["_id"]).startswith("lock::"):
            continue
        found = True
        print(
            f"  {doc['_id']}: last_archived_id={as_int(doc.get('last_archived_id') or 0):,} "
            f"cutoff_id={doc.get('cutoff_id')} updated={doc.get('updated_at')}"
        )
    if not found:
        print("  (none)")
    print()
    for entry in config.get("collections", []):
        source, target = entry["source"], entry["target"]
        print(f"  {source}: {db[source].estimated_document_count():,} docs")
        print(f"  {target}: {db[target].estimated_document_count():,} docs")


def verify_collection(db, source: str, target: str, id_field: str, cutoff_id: int | None) -> bool:
    live = db[source]
    archive = db[target]
    ok = True
    print(f"  {source}: {live.estimated_document_count():,} docs")
    print(f"  {target}: {archive.estimated_document_count():,} docs")
    if cutoff_id is not None:
        remaining = live.count_documents({id_field: {"$lte": cutoff_id}})
        in_archive = archive.count_documents({id_field: {"$lte": cutoff_id}})
        print(f"    live  with {id_field} <= {cutoff_id:,}: {remaining:,}")
        print(f"    archive with {id_field} <= {cutoff_id:,}: {in_archive:,}")
        if remaining != 0:
            print("    WARNING: documents at or below the cut-off are still in the live collection")
            ok = False
    return ok


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    archive_cfg = config.get("archive", {})
    mongo_cfg = config.get("mongo", {})
    entries = config.get("collections") or []
    if not entries:
        raise ValueError("Config has no collections to archive.")
    if args.only:
        entries = [entry for entry in entries if entry.get("source") == args.only]
        if not entries:
            raise ValueError(f"No configured collection named {args.only!r}.")

    batch_size = args.batch_size or int(archive_cfg.get("batch_size", DEFAULT_BATCH_SIZE))
    max_documents = (
        args.max_documents
        if args.max_documents is not None
        else int(archive_cfg.get("max_documents_per_run", 0) or 0)
    )
    lock_timeout = int(archive_cfg.get("lock_timeout_seconds", DEFAULT_LOCK_TIMEOUT_SECONDS))
    state_collection_name = archive_cfg.get("state_collection", DEFAULT_STATE_COLLECTION)
    assume_yes = bool(archive_cfg.get("assume_yes", False)) or args.yes

    client = get_mongo_client(config)
    try:
        db = client[mongo_cfg.get("database", "eastel-data")]
        state_collection = db[state_collection_name]

        if args.status:
            print_status(state_collection, db, config)
            return 0

        if args.verify:
            ok = True
            for entry in entries:
                state = load_state(state_collection, state_key(entry["source"], entry["target"])) or {}
                cutoff = state.get("cutoff_id")
                print(f"{entry['source']} -> {entry['target']}")
                ok = verify_collection(
                    db, entry["source"], entry["target"], entry["id_field"],
                    as_int(cutoff) if cutoff is not None else None,
                ) and ok
                print()
            return 0 if ok else 1

        print(f"database: {mongo_cfg.get('database', 'eastel-data')}")
        print(f"batch size: {batch_size:,}  max documents per run: {max_documents or 'unlimited'}")
        print()

        if not args.dry_run and not assume_yes:
            answer = input(
                "This MOVES documents out of the live collections and deletes them there.\n"
                "Type 'archive' to continue: "
            ).strip()
            if answer != "archive":
                print("Aborted.")
                return 1

        for entry in entries:
            source, target = entry["source"], entry["target"]
            id_field = entry["id_field"]
            time_field = entry.get("time_field") or "cr_time"
            live, archive = db[source], db[target]
            key = state_key(source, target)

            print(f"=== {source} -> {target} ===")
            if args.reset_state:
                state_collection.delete_one({"_id": key})
                print("  cleared stored progress")

            if args.ensure_indexes:
                created = ensure_archive_indexes(live, archive)
                print(f"  ensured {len(created)} archive index(es): {', '.join(created) or 'none'}")

            state = load_state(state_collection, key) or {}
            date_text = args.before_date or entry.get("before_date")
            before_date = parse_date(str(date_text)) if date_text else None

            cutoff_id, before_date = resolve_cutoff(
                live=live,
                state_collection=state_collection,
                key=key,
                source=source,
                target=target,
                id_field=id_field,
                time_field=time_field,
                cli_max_id=args.max_id,
                entry_max_id=entry.get("max_id"),
                before_date=before_date,
                persist=not args.dry_run,
            )
            if cutoff_id is None:
                print("  no documents older than the configured date — nothing to do")
                print()
                continue
            cutoff_id = as_int(cutoff_id)

            checkpoint = as_int(state.get("last_archived_id") or 0)
            print(f"  cut-off: {id_field} <= {cutoff_id:,}  (resuming from {checkpoint:,})"
                  + (f", guard {time_field} < {before_date}" if before_date else ""))
            if args.dry_run or checkpoint == 0:
                # Index-only count on the id bound. Counting with the time_field guard
                # would have to read every candidate document, because time_field is
                # not indexed; the guard only ever removes a few inverted rows.
                candidates = live.count_documents(
                    {id_field: {"$gt": checkpoint, "$lte": cutoff_id}}
                )
                print(f"  candidates in live: {candidates:,}")

            if args.dry_run:
                print("  dry run: nothing moved")
                print()
                continue

            owner_id = str(uuid.uuid4())
            acquire_lock(state_collection, source, target, owner_id, lock_timeout)
            print("  acquired archive lock")
            started = time.perf_counter()
            try:
                moved, batches = archive_collection(
                    live=live,
                    archive=archive,
                    state_collection=state_collection,
                    source=source,
                    target=target,
                    id_field=id_field,
                    time_field=time_field,
                    cutoff_id=cutoff_id,
                    before_date=before_date,
                    batch_size=batch_size,
                    max_documents=max_documents,
                    owner_id=owner_id,
                    lock_timeout_seconds=lock_timeout,
                )
            finally:
                release_lock(state_collection, source, target, owner_id)
                print("  released archive lock")

            elapsed = time.perf_counter() - started
            remaining = live.count_documents({id_field: {"$lte": cutoff_id}})
            print(
                f"  done: moved {moved:,} docs in {batches} batch(es) in {elapsed:.1f}s "
                f"({moved / elapsed:.0f} docs/s)"
            )
            print(f"  remaining in live with {id_field} <= {cutoff_id:,}: {remaining:,}")
            print()

        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
