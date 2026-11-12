"""Sync usage logs for a supplied list of MSISDNs ahead of the main usage sync.

The main usage sync walks ``usage_log_id`` forward from its checkpoint, so recent
rows for a specific subscriber can lag by days while the backlog drains. This
script reads MSISDNs from a CSV file and copies every row for those subscribers
straight into MongoDB.

It shares the document transform with the main sync (so documents stay identical)
but keeps its own state document and its own lock, which means it can run at the
same time as the main sync: writes are idempotent upserts keyed by usage_log_id,
and neither script touches the other's checkpoint.
"""

import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import UpdateOne


USAGE_SYNC_DIR = Path(__file__).resolve().parent.parent / "postgres-to-mongo-usage-sync"
if not (USAGE_SYNC_DIR / "postgres_to_mongo_usage_sync.py").exists():
    raise SystemExit(
        "Cannot find the usage sync module next to this script. Expected "
        f"{USAGE_SYNC_DIR / 'postgres_to_mongo_usage_sync.py'}; keep both folders together."
    )
sys.path.insert(0, str(USAGE_SYNC_DIR))

from postgres_to_mongo_usage_sync import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_OOM_RETRY_ATTEMPTS,
    DEFAULT_OOM_RETRY_DELAY_SECONDS,
    acquire_lock,
    get_config_value,
    get_mongo_client,
    get_postgres_dsn,
    get_state_key,
    get_usage_collection_name,
    get_usage_mongo_db_name,
    get_usage_source_table,
    get_usage_state_collection_name,
    refresh_lock,
    release_lock,
    transform_row,
    validate_usage_collection_indexes,
    write_batch,
)


BACKFILL_LABEL = "msisdn-backfill"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
HEADER_NAMES = {"msisdn", "msisdn_number", "number", "phone", "phone_number", "subscriber"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy all usage log rows for the MSISDNs listed in a CSV file from "
            "PostgreSQL to MongoDB, keyed by usage_log_id."
        )
    )
    parser.add_argument(
        "--msisdn-csv",
        default=os.getenv("MSISDN_CSV"),
        help="CSV file with one MSISDN per row. A header row such as 'msisdn' is allowed.",
    )
    parser.add_argument(
        "--source-table",
        default=None,
        help="PostgreSQL source table name. Defaults to config sync.postgres_usage_source_table.",
    )
    parser.add_argument("--mongo-db", default=None, help="MongoDB database name override.")
    parser.add_argument("--mongo-collection", default=None, help="MongoDB collection name override.")
    parser.add_argument("--state-collection", default=None, help="MongoDB state collection override.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Rows fetched per batch, per MSISDN.",
    )
    parser.add_argument(
        "--lock-timeout-seconds",
        type=int,
        default=None,
        help="Expiry of this script's own sync lock.",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help=(
            "Forget the stored progress of the MSISDNs in this CSV so they are copied "
            "again from the first row. Existing documents are updated in place."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count the source rows per MSISDN. Nothing is written to MongoDB.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file used when env vars are not set.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def normalize_msisdn(value: str) -> str:
    text = value.strip()
    if text.startswith("+"):
        text = text[1:]
    return text.replace(" ", "").replace("-", "")


def load_msisdns(csv_path: str) -> list[str]:
    msisdns: list[str] = []
    seen: set[str] = set()
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.reader(handle), start=1):
            if not row:
                continue
            raw = row[0]
            if not raw or not raw.strip():
                continue
            if row_number == 1 and raw.strip().lower() in HEADER_NAMES:
                continue
            msisdn = normalize_msisdn(raw)
            if not msisdn:
                continue
            if not msisdn.isdigit():
                print(
                    f"warning: row {row_number} value {raw!r} is not all digits after "
                    f"normalisation, using {msisdn!r} as-is",
                    file=sys.stderr,
                )
            if msisdn in seen:
                continue
            seen.add(msisdn)
            msisdns.append(msisdn)

    if not msisdns:
        raise ValueError(f"No MSISDN values found in {csv_path}")
    return msisdns


def get_progress(state_collection, state_key: str) -> dict[str, int]:
    state = state_collection.find_one({"_id": state_key}, {"progress": 1})
    if not state:
        return {}
    progress = state.get("progress") or {}
    return {str(msisdn): int(last_id) for msisdn, last_id in progress.items()}


def save_progress(
    state_collection,
    state_key: str,
    source_table: str,
    mongo_collection: str,
    msisdn: str,
    last_usage_log_id: int,
) -> None:
    state_collection.update_one(
        {"_id": state_key},
        {
            "$set": {
                "source_table": source_table,
                "mongo_collection": mongo_collection,
                f"progress.{msisdn}": last_usage_log_id,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def reset_progress(state_collection, state_key: str, msisdns: list[str]) -> None:
    unset_fields = {f"progress.{msisdn}": "" for msisdn in msisdns}
    state_collection.update_one({"_id": state_key}, {"$unset": unset_fields})


def fetch_rows(
    pg_conn,
    source_table: str,
    msisdn: str,
    last_usage_log_id: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE msisdn = %s
          AND usage_log_id > %s
        ORDER BY usage_log_id ASC
        LIMIT %s
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (msisdn, last_usage_log_id, batch_size))
        return cursor.fetchall()


def count_rows(pg_conn, source_table: str, msisdn: str) -> int:
    query = sql.SQL("SELECT count(*) AS total FROM {source_table} WHERE msisdn = %s").format(
        source_table=sql.Identifier(source_table)
    )
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (msisdn,))
        row = cursor.fetchone()
        return int(row["total"])


def sync_msisdn(
    pg_conn,
    mongo_collection,
    state_collection,
    state_key: str,
    source_table: str,
    mongo_collection_name: str,
    msisdn: str,
    start_id: int,
    batch_size: int,
    lock_args: dict[str, Any],
    oom_retry_attempts: int,
    oom_retry_delay_seconds: int,
) -> tuple[int, int, int]:
    checkpoint = start_id
    total_rows = 0
    batches = 0

    while True:
        refresh_lock(**lock_args)

        rows = fetch_rows(
            pg_conn=pg_conn,
            source_table=source_table,
            msisdn=msisdn,
            last_usage_log_id=checkpoint,
            batch_size=batch_size,
        )
        if not rows:
            break

        row_count = len(rows)
        operations = [
            UpdateOne(
                {"usage_log_id": int(row["usage_log_id"])},
                {"$set": transform_row(row, source_table)},
                upsert=True,
            )
            for row in rows
        ]
        max_usage_log_id = max(int(row["usage_log_id"]) for row in rows)
        # Free the source rows before the write; the batch message is built from
        # operations and both being alive doubles peak memory.
        del rows

        write_batch(
            mongo_collection=mongo_collection,
            operations=operations,
            oom_retry_attempts=oom_retry_attempts,
            oom_retry_delay_seconds=oom_retry_delay_seconds,
        )
        checkpoint = max_usage_log_id
        save_progress(
            state_collection=state_collection,
            state_key=state_key,
            source_table=source_table,
            mongo_collection=mongo_collection_name,
            msisdn=msisdn,
            last_usage_log_id=checkpoint,
        )

        total_rows += row_count
        batches += 1
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"msisdn={msisdn} synced {row_count} rows, checkpoint={checkpoint}, "
            f"batch={batches}",
            flush=True,
        )

        if row_count < batch_size:
            break

    return total_rows, checkpoint, batches


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    msisdns_csv = args.msisdn_csv or get_config_value(
        config, "backfill", "msisdns_csv", "MSISDN_CSV"
    )
    if not msisdns_csv:
        raise SystemExit("Provide --msisdn-csv <path> (or set MSISDN_CSV).")

    postgres_dsn = get_postgres_dsn(config)
    mongo_db_name = args.mongo_db or get_config_value(
        config, "mongo", "database", "MONGO_DB", "eastel-data"
    )
    mongo_db_name = get_usage_mongo_db_name(config, str(mongo_db_name))
    mongo_collection_name = args.mongo_collection or get_config_value(
        config, "mongo", "collection", "MONGO_COLLECTION", "usage_logs"
    )
    mongo_collection_name = get_usage_collection_name(config, str(mongo_collection_name))
    state_collection_name = args.state_collection or get_config_value(
        config, "mongo", "state_collection", "MONGO_STATE_COLLECTION", "usage_log_sync_state"
    )
    state_collection_name = get_usage_state_collection_name(config, str(state_collection_name))
    source_table = args.source_table or get_config_value(
        config, "sync", "source_table", "PG_SOURCE_TABLE", "iot_portal_tb_usage_log"
    )
    source_table = get_usage_source_table(config, str(source_table))
    batch_size = int(
        args.batch_size
        or get_config_value(config, "backfill", "batch_size", "SYNC_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    )
    lock_timeout_seconds = int(
        args.lock_timeout_seconds
        or get_config_value(
            config,
            "sync",
            "lock_timeout_seconds",
            "SYNC_LOCK_TIMEOUT_SECONDS",
            DEFAULT_LOCK_TIMEOUT_SECONDS,
        )
    )
    oom_retry_attempts = int(
        get_config_value(
            config,
            "sync",
            "oom_retry_attempts",
            "SYNC_OOM_RETRY_ATTEMPTS",
            DEFAULT_OOM_RETRY_ATTEMPTS,
        )
    )
    oom_retry_delay_seconds = int(
        get_config_value(
            config,
            "sync",
            "oom_retry_delay_seconds",
            "SYNC_OOM_RETRY_DELAY_SECONDS",
            DEFAULT_OOM_RETRY_DELAY_SECONDS,
        )
    )

    msisdns = load_msisdns(msisdns_csv)
    state_key = get_state_key(source_table, mongo_collection_name, BACKFILL_LABEL)
    owner_id = str(uuid.uuid4())
    lock_args = {
        "state_collection": None,
        "source_table": source_table,
        "mongo_collection": mongo_collection_name,
        "owner_id": owner_id,
        "lock_timeout_seconds": lock_timeout_seconds,
        "label": BACKFILL_LABEL,
    }

    print(f"source table: {source_table}")
    print(f"mongo collection: {mongo_db_name}.{mongo_collection_name}")
    print(f"state document: {state_key}")
    print(f"msisdns: {len(msisdns)} from {msisdns_csv}")
    if args.dry_run:
        print("dry run: counting source rows only")

    with psycopg.connect(postgres_dsn, row_factory=dict_row) as pg_conn:
        with get_mongo_client(config) as mongo_client:
            mongo_db = mongo_client[mongo_db_name]
            mongo_collection = mongo_db[mongo_collection_name]
            state_collection = mongo_db[state_collection_name]
            validate_usage_collection_indexes(mongo_collection)

            if args.dry_run:
                for msisdn in msisdns:
                    print(f"msisdn={msisdn} source rows={count_rows(pg_conn, source_table, msisdn)}")
                return

            if args.reset_progress:
                reset_progress(state_collection, state_key, msisdns)
                print("Cleared stored progress for the supplied msisdns.")

            progress = get_progress(state_collection, state_key)
            lock_args["state_collection"] = state_collection
            acquire_lock(
                state_collection=state_collection,
                source_table=source_table,
                mongo_collection=mongo_collection_name,
                owner_id=owner_id,
                lock_timeout_seconds=lock_timeout_seconds,
                label=BACKFILL_LABEL,
            )
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"acquired {BACKFILL_LABEL} lock for {source_table}->{mongo_collection_name}"
            )

            started_at = time.perf_counter()
            summary: list[tuple[str, int, int, int, float]] = []
            try:
                for index, msisdn in enumerate(msisdns, start=1):
                    msisdn_started_at = time.perf_counter()
                    start_id = progress.get(msisdn, 0)
                    rows_written, checkpoint, _batches = sync_msisdn(
                        pg_conn=pg_conn,
                        mongo_collection=mongo_collection,
                        state_collection=state_collection,
                        state_key=state_key,
                        source_table=source_table,
                        mongo_collection_name=mongo_collection_name,
                        msisdn=msisdn,
                        start_id=start_id,
                        batch_size=batch_size,
                        lock_args=lock_args,
                        oom_retry_attempts=oom_retry_attempts,
                        oom_retry_delay_seconds=oom_retry_delay_seconds,
                    )
                    elapsed = time.perf_counter() - msisdn_started_at
                    summary.append((msisdn, start_id, checkpoint, rows_written, elapsed))
                    print(
                        f"[{datetime.now().isoformat(timespec='seconds')}] "
                        f"done {index}/{len(msisdns)} msisdn={msisdn}: "
                        f"{rows_written} rows from checkpoint {start_id} to {checkpoint} "
                        f"in {elapsed:.1f}s",
                        flush=True,
                    )
            finally:
                release_lock(
                    state_collection=state_collection,
                    source_table=source_table,
                    mongo_collection=mongo_collection_name,
                    owner_id=owner_id,
                    label=BACKFILL_LABEL,
                )
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"released {BACKFILL_LABEL} lock for {source_table}->{mongo_collection_name}"
                )

    total_elapsed = time.perf_counter() - started_at
    total_rows = sum(item[3] for item in summary)
    print()
    print(f"{'msisdn':<20}{'from':>14}{'to':>14}{'rows':>10}{'seconds':>10}")
    for msisdn, start_id, checkpoint, rows_written, elapsed in summary:
        print(f"{msisdn:<20}{start_id:>14}{checkpoint:>14}{rows_written:>10}{elapsed:>10.1f}")
    print(
        f"total: {total_rows} rows across {len(summary)} msisdn(s) in {total_elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
