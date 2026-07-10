import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import ASCENDING, UpdateOne


SYNC_FOLDER = Path(__file__).resolve().parent.parent / "postgres-to-mongo-request-sync"
if str(SYNC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SYNC_FOLDER))

from postgres_to_mongo_request_log_sync import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_MONGO_COLLECTION,
    DEFAULT_MONGO_DB,
    get_config_value,
    get_mongo_client,
    get_postgres_dsn,
    get_request_log_collection_name,
    get_request_log_mongo_db_name,
    get_request_log_source_table,
    load_config,
    transform_row,
)


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
DEFAULT_SOURCE_TABLE = "iot_portal_tb_request_log"
DEFAULT_SYNCED_COLLECTION = "request_synced"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill or repair request log documents in MongoDB from PostgreSQL."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to YAML config file.")
    parser.add_argument("--source-table", default="", help="Override PostgreSQL source table name.")
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", DEFAULT_MONGO_DB), help="Override MongoDB database name.")
    parser.add_argument(
        "--mongo-collection",
        default=os.getenv("MONGO_COLLECTION", DEFAULT_MONGO_COLLECTION),
        help="Override MongoDB collection name.",
    )
    parser.add_argument(
        "--synced-collection",
        default=os.getenv("MONGO_SYNCED_COLLECTION", DEFAULT_SYNCED_COLLECTION),
        help="MongoDB collection used to store temporary backfill sync history.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("SYNC_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        help="Number of PostgreSQL rows to fetch per batch.",
    )
    parser.add_argument(
        "--mode",
        choices=["ids", "id_range", "time"],
        default="",
        help="Backfill scope mode. If omitted, config backfill.mode is used.",
    )
    parser.add_argument(
        "--time-field",
        choices=["req_time", "up_time", "cr_time"],
        default="",
        help="Timestamp field to use with --start/--end. Recommended: up_time.",
    )
    parser.add_argument("--start", default="", help="Inclusive ISO datetime lower bound.")
    parser.add_argument("--end", default="", help="Exclusive ISO datetime upper bound.")
    parser.add_argument("--id-from", type=int, default=None, help="Inclusive lower bound for request_log_id.")
    parser.add_argument("--id-to", type=int, default=None, help="Inclusive upper bound for request_log_id.")
    parser.add_argument("--ids", default="", help="Comma-separated explicit request_log_id values to repair.")
    parser.add_argument(
        "--min-record-age-seconds",
        type=int,
        default=None,
        help="Time mode only: skip rows whose cr_time is newer than now minus this many seconds.",
    )
    return parser.parse_args()


def parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("Datetime value cannot be empty.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_ids(ids_text: str) -> list[int]:
    if not ids_text.strip():
        return []
    return [int(part.strip()) for part in ids_text.split(",") if part.strip()]


def validate_args(args: argparse.Namespace) -> None:
    if args.mode not in {"ids", "id_range", "time"}:
        raise ValueError("backfill mode must be one of: ids, id_range, time.")

    if args.mode == "time":
        if not (args.start and args.end):
            raise ValueError("Both start and end are required in time mode.")
        if not args.time_field:
            raise ValueError("time_field is required in time mode.")

    if args.mode == "id_range":
        if args.id_from is None and args.id_to is None:
            raise ValueError("At least one of id_from or id_to is required in id_range mode.")
        if args.id_from is not None and args.id_to is not None and args.id_from > args.id_to:
            raise ValueError("id_from cannot be greater than id_to.")

    if args.mode == "ids" and not args.ids.strip():
        raise ValueError("ids is required in ids mode.")


def build_effective_args(args: argparse.Namespace, config: dict[str, Any]) -> argparse.Namespace:
    backfill_config = config.get("backfill", {})
    if backfill_config is None:
        backfill_config = {}
    if not isinstance(backfill_config, dict):
        raise ValueError("Config key 'backfill' must be a YAML object.")

    effective = argparse.Namespace(**vars(args))

    if not effective.mode:
        effective.mode = str(backfill_config.get("mode") or "").strip()
    if not effective.time_field:
        effective.time_field = str(backfill_config.get("time_field") or "").strip()
    if not effective.start:
        effective.start = str(backfill_config.get("start") or "").strip()
    if not effective.end:
        effective.end = str(backfill_config.get("end") or "").strip()
    if effective.id_from is None and backfill_config.get("id_from") not in (None, ""):
        effective.id_from = int(backfill_config.get("id_from"))
    if effective.id_to is None and backfill_config.get("id_to") not in (None, ""):
        effective.id_to = int(backfill_config.get("id_to"))
    if not effective.ids:
        effective.ids = str(backfill_config.get("ids") or "").strip()
    if effective.batch_size == DEFAULT_BATCH_SIZE and backfill_config.get("batch_size") not in (None, ""):
        effective.batch_size = int(backfill_config.get("batch_size"))
    if effective.min_record_age_seconds is None and backfill_config.get("min_record_age_seconds") not in (None, ""):
        effective.min_record_age_seconds = int(backfill_config.get("min_record_age_seconds"))
    if effective.min_record_age_seconds is None:
        effective.min_record_age_seconds = 0

    return effective


def get_request_log_synced_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_request_synced_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_synced_doc_key(source_table: str, mongo_collection: str, log_id: int) -> str:
    return f"{source_table}->{mongo_collection}->{log_id}"


def ensure_request_synced_collection_indexes(synced_collection) -> None:
    synced_collection.create_index(
        [("source_table", ASCENDING), ("mongo_collection", ASCENDING), ("request_log_id", ASCENDING)],
        name="uq_request_synced_source_collection_id",
        unique=True,
    )
    synced_collection.create_index(
        [("request_log_id", ASCENDING)],
        name="ix_request_synced_request_log_id",
    )


def get_already_synced_request_ids(
    synced_collection,
    source_table: str,
    mongo_collection: str,
    request_log_ids: list[int],
) -> set[int]:
    if not request_log_ids:
        return set()
    synced_doc_ids = [
        get_synced_doc_key(source_table, mongo_collection, request_log_id)
        for request_log_id in request_log_ids
    ]
    cursor = synced_collection.find({"_id": {"$in": synced_doc_ids}}, {"request_log_id": 1})
    return {
        int(doc["request_log_id"])
        for doc in cursor
        if doc.get("request_log_id") is not None
    }


def mark_request_ids_synced(
    synced_collection,
    source_table: str,
    mongo_collection: str,
    request_log_ids: list[int],
) -> None:
    if not request_log_ids:
        return
    now = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"_id": get_synced_doc_key(source_table, mongo_collection, request_log_id)},
            {
                "$set": {
                    "source_table": source_table,
                    "mongo_collection": mongo_collection,
                    "request_log_id": request_log_id,
                    "synced_at": now,
                }
            },
            upsert=True,
        )
        for request_log_id in request_log_ids
    ]
    synced_collection.bulk_write(operations, ordered=False)


def fetch_rows_by_time(
    pg_conn,
    source_table: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
    last_request_log_id: int,
    batch_size: int,
    min_record_age_seconds: int,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    if min_record_age_seconds > 0:
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - min_record_age_seconds,
            tz=timezone.utc,
        ).replace(tzinfo=None)
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE {time_field} >= %s
          AND {time_field} < %s
          AND cr_time <= %s
          AND request_log_id > %s
        ORDER BY request_log_id ASC
        LIMIT %s
        """
    ).format(source_table=sql.Identifier(source_table), time_field=sql.Identifier(time_field))
    with pg_conn.cursor() as cursor:
        cursor.execute(
            query,
            (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None), cutoff, last_request_log_id, batch_size),
        )
        return cursor.fetchall()


def fetch_rows_by_id_range(
    pg_conn,
    source_table: str,
    id_from: int,
    id_to: int,
    last_request_log_id: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE request_log_id >= %s
          AND request_log_id <= %s
          AND request_log_id > %s
        ORDER BY request_log_id ASC
        LIMIT %s
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (id_from, id_to, last_request_log_id, batch_size))
        return cursor.fetchall()


def fetch_rows_by_ids(pg_conn, source_table: str, ids: list[int]) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE request_log_id = ANY(%s)
        ORDER BY request_log_id ASC
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (ids,))
        return cursor.fetchall()


def fetch_count_value(cursor) -> int:
    row = cursor.fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def count_rows_by_time(
    pg_conn,
    source_table: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
    min_record_age_seconds: int,
) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    if min_record_age_seconds > 0:
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - min_record_age_seconds,
            tz=timezone.utc,
        ).replace(tzinfo=None)
    query = sql.SQL(
        """
        SELECT COUNT(*)
        FROM {source_table}
        WHERE {time_field} >= %s
          AND {time_field} < %s
          AND cr_time <= %s
        """
    ).format(source_table=sql.Identifier(source_table), time_field=sql.Identifier(time_field))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None), cutoff))
        return fetch_count_value(cursor)


def count_rows_by_id_range(pg_conn, source_table: str, id_from: int, id_to: int) -> int:
    query = sql.SQL(
        """
        SELECT COUNT(*)
        FROM {source_table}
        WHERE request_log_id >= %s
          AND request_log_id <= %s
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (id_from, id_to))
        return fetch_count_value(cursor)


def count_rows_by_ids(pg_conn, source_table: str, ids: list[int]) -> int:
    query = sql.SQL(
        """
        SELECT COUNT(*)
        FROM {source_table}
        WHERE request_log_id = ANY(%s)
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (ids,))
        return fetch_count_value(cursor)


def upsert_rows(mongo_collection, rows: list[dict[str, Any]], source_table: str) -> list[int]:
    if not rows:
        return []
    operations = [
        UpdateOne(
            {"request_log_id": int(row["request_log_id"])},
            {"$set": transform_row(row, source_table)},
            upsert=True,
        )
        for row in rows
    ]
    mongo_collection.bulk_write(operations, ordered=False)
    return [int(row["request_log_id"]) for row in rows]


def filter_unsynced_request_rows(
    synced_collection,
    source_table: str,
    mongo_collection_name: str,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    candidate_ids = [int(row["request_log_id"]) for row in rows]
    already_synced_ids = get_already_synced_request_ids(
        synced_collection=synced_collection,
        source_table=source_table,
        mongo_collection=mongo_collection_name,
        request_log_ids=candidate_ids,
    )
    filtered_rows = [
        row for row in rows
        if int(row["request_log_id"]) not in already_synced_ids
    ]
    return filtered_rows, len(rows) - len(filtered_rows)


def backfill_by_time(
    pg_conn,
    mongo_collection,
    synced_collection,
    source_table: str,
    mongo_collection_name: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
    batch_size: int,
    total_rows: int,
    min_record_age_seconds: int,
) -> int:
    last_request_log_id = 0
    total_processed = 0
    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_time(
            pg_conn,
            source_table,
            time_field,
            start_dt,
            end_dt,
            last_request_log_id,
            batch_size,
            min_record_age_seconds,
        )
        if not rows:
            break
        last_request_log_id = int(rows[-1]["request_log_id"])
        rows_to_process, skipped_count = filter_unsynced_request_rows(
            synced_collection=synced_collection,
            source_table=source_table,
            mongo_collection_name=mongo_collection_name,
            rows=rows,
        )
        synced_request_ids = upsert_rows(mongo_collection, rows_to_process, source_table)
        mark_request_ids_synced(synced_collection, source_table, mongo_collection_name, synced_request_ids)
        total_processed += len(synced_request_ids)
        percent = (total_processed / total_rows * 100.0) if total_rows > 0 else 100.0
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"repaired {len(synced_request_ids)} rows, skipped_already_marked={skipped_count}, total={total_processed}/{total_rows}, percent={percent:.2f}%, last_request_log_id={last_request_log_id}, "
            f"batch_total={time.perf_counter() - batch_started_at:.3f}s"
        )
        if len(rows) < batch_size:
            break
    return total_processed


def backfill_by_id_range(
    pg_conn,
    mongo_collection,
    synced_collection,
    source_table: str,
    mongo_collection_name: str,
    id_from: int,
    id_to: int,
    batch_size: int,
    total_rows: int,
) -> int:
    last_request_log_id = id_from - 1
    total_processed = 0
    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_id_range(pg_conn, source_table, id_from, id_to, last_request_log_id, batch_size)
        if not rows:
            break
        last_request_log_id = int(rows[-1]["request_log_id"])
        rows_to_process, skipped_count = filter_unsynced_request_rows(
            synced_collection=synced_collection,
            source_table=source_table,
            mongo_collection_name=mongo_collection_name,
            rows=rows,
        )
        synced_request_ids = upsert_rows(mongo_collection, rows_to_process, source_table)
        mark_request_ids_synced(synced_collection, source_table, mongo_collection_name, synced_request_ids)
        total_processed += len(synced_request_ids)
        percent = (total_processed / total_rows * 100.0) if total_rows > 0 else 100.0
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"repaired {len(synced_request_ids)} rows, skipped_already_marked={skipped_count}, total={total_processed}/{total_rows}, percent={percent:.2f}%, last_request_log_id={last_request_log_id}, "
            f"batch_total={time.perf_counter() - batch_started_at:.3f}s"
        )
        if len(rows) < batch_size:
            break
    return total_processed


def main() -> None:
    raw_args = parse_args()
    config = load_config(raw_args.config)
    args = build_effective_args(raw_args, config)
    validate_args(args)
    postgres_dsn = get_postgres_dsn(config)
    source_table = args.source_table or str(
        get_request_log_source_table(
            config,
            get_config_value(config, "sync", "source_table", "PG_SOURCE_TABLE", DEFAULT_SOURCE_TABLE),
        )
    )
    mongo_db_name = get_request_log_mongo_db_name(config, str(get_config_value(config, "mongo", "database", "MONGO_DB", args.mongo_db)))
    mongo_collection_name = get_request_log_collection_name(
        config,
        str(get_config_value(config, "mongo", "collection", "MONGO_COLLECTION", args.mongo_collection)),
    )
    synced_collection_name = get_request_log_synced_collection_name(
        config,
        str(get_config_value(config, "mongo", "synced_collection", "MONGO_SYNCED_COLLECTION", args.synced_collection)),
    )

    explicit_ids = parse_ids(args.ids)
    start_dt = parse_iso_datetime(args.start) if args.start else None
    end_dt = parse_iso_datetime(args.end) if args.end else None

    with psycopg.connect(postgres_dsn, row_factory=dict_row) as pg_conn:
        with get_mongo_client(config) as mongo_client:
            mongo_collection = mongo_client[mongo_db_name][mongo_collection_name]
            synced_collection = mongo_client[mongo_db_name][synced_collection_name]
            ensure_request_synced_collection_indexes(synced_collection)

            if args.mode == "ids":
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    "calculating potential affected rows before processing explicit request_log_id list"
                )
                total_rows = count_rows_by_ids(pg_conn, source_table, explicit_ids)
                print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
                rows = fetch_rows_by_ids(pg_conn, source_table, explicit_ids)
                rows_to_process, skipped_count = filter_unsynced_request_rows(
                    synced_collection=synced_collection,
                    source_table=source_table,
                    mongo_collection_name=mongo_collection_name,
                    rows=rows,
                )
                synced_request_ids = upsert_rows(mongo_collection, rows_to_process, source_table)
                mark_request_ids_synced(synced_collection, source_table, mongo_collection_name, synced_request_ids)
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"repaired {len(synced_request_ids)} explicit request_log_id rows, skipped_already_marked={skipped_count}"
                )
                return

            if args.mode == "time":
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    "calculating potential affected rows before processing "
                    f"time range start={start_dt.isoformat()} end={end_dt.isoformat()} field={args.time_field} "
                    f"min_record_age_seconds={args.min_record_age_seconds}"
                )
                total_rows = count_rows_by_time(
                    pg_conn,
                    source_table,
                    args.time_field,
                    start_dt,
                    end_dt,
                    args.min_record_age_seconds,
                )
                print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
                total_processed = backfill_by_time(
                    pg_conn,
                    mongo_collection,
                    synced_collection,
                    source_table,
                    mongo_collection_name,
                    args.time_field,
                    start_dt,
                    end_dt,
                    args.batch_size,
                    total_rows,
                    args.min_record_age_seconds,
                )
                print(f"[{datetime.now().isoformat(timespec='seconds')}] completed time-based repair, total_rows={total_processed}")
                return

            id_from = args.id_from if args.id_from is not None else 0
            id_to = args.id_to if args.id_to is not None else 9223372036854775807
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                "calculating potential affected rows before processing "
                f"request_log_id range id_from={id_from} id_to={id_to}"
            )
            total_rows = count_rows_by_id_range(pg_conn, source_table, id_from, id_to)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
            total_processed = backfill_by_id_range(
                pg_conn,
                mongo_collection,
                synced_collection,
                source_table,
                mongo_collection_name,
                id_from,
                id_to,
                args.batch_size,
                total_rows,
            )
            print(f"[{datetime.now().isoformat(timespec='seconds')}] completed id-range repair, total_rows={total_processed}")


if __name__ == "__main__":
    main()
