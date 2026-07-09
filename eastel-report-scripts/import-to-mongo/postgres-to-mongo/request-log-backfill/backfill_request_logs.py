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
from pymongo import UpdateOne


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

    return effective


def fetch_rows_by_time(
    pg_conn,
    source_table: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
    last_request_log_id: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE {time_field} >= %s
          AND {time_field} < %s
          AND request_log_id > %s
        ORDER BY request_log_id ASC
        LIMIT %s
        """
    ).format(source_table=sql.Identifier(source_table), time_field=sql.Identifier(time_field))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None), last_request_log_id, batch_size))
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


def count_rows_by_time(
    pg_conn,
    source_table: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
) -> int:
    query = sql.SQL(
        """
        SELECT COUNT(*)
        FROM {source_table}
        WHERE {time_field} >= %s
          AND {time_field} < %s
        """
    ).format(source_table=sql.Identifier(source_table), time_field=sql.Identifier(time_field))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None)))
        return int(cursor.fetchone()[0])


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
        return int(cursor.fetchone()[0])


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
        return int(cursor.fetchone()[0])


def upsert_rows(mongo_collection, rows: list[dict[str, Any]], source_table: str) -> None:
    if not rows:
        return
    operations = [
        UpdateOne(
            {"request_log_id": int(row["request_log_id"])},
            {"$set": transform_row(row, source_table)},
            upsert=True,
        )
        for row in rows
    ]
    mongo_collection.bulk_write(operations, ordered=False)


def backfill_by_time(pg_conn, mongo_collection, source_table: str, time_field: str, start_dt: datetime, end_dt: datetime, batch_size: int, total_rows: int) -> int:
    last_request_log_id = 0
    total_processed = 0
    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_time(pg_conn, source_table, time_field, start_dt, end_dt, last_request_log_id, batch_size)
        if not rows:
            break
        upsert_rows(mongo_collection, rows, source_table)
        last_request_log_id = int(rows[-1]["request_log_id"])
        total_processed += len(rows)
        percent = (total_processed / total_rows * 100.0) if total_rows > 0 else 100.0
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"repaired {len(rows)} rows, total={total_processed}/{total_rows}, percent={percent:.2f}%, last_request_log_id={last_request_log_id}, "
            f"batch_total={time.perf_counter() - batch_started_at:.3f}s"
        )
        if len(rows) < batch_size:
            break
    return total_processed


def backfill_by_id_range(pg_conn, mongo_collection, source_table: str, id_from: int, id_to: int, batch_size: int, total_rows: int) -> int:
    last_request_log_id = id_from - 1
    total_processed = 0
    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_id_range(pg_conn, source_table, id_from, id_to, last_request_log_id, batch_size)
        if not rows:
            break
        upsert_rows(mongo_collection, rows, source_table)
        last_request_log_id = int(rows[-1]["request_log_id"])
        total_processed += len(rows)
        percent = (total_processed / total_rows * 100.0) if total_rows > 0 else 100.0
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"repaired {len(rows)} rows, total={total_processed}/{total_rows}, percent={percent:.2f}%, last_request_log_id={last_request_log_id}, "
            f"batch_total={time.perf_counter() - batch_started_at:.3f}s"
        )
        if len(rows) < batch_size:
            break
    return total_processed


def main() -> None:
    config = load_config(args.config)
    args = build_effective_args(parse_args(), config)
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

    explicit_ids = parse_ids(args.ids)
    start_dt = parse_iso_datetime(args.start) if args.start else None
    end_dt = parse_iso_datetime(args.end) if args.end else None

    with psycopg.connect(postgres_dsn, row_factory=dict_row) as pg_conn:
        with get_mongo_client(config) as mongo_client:
            mongo_collection = mongo_client[mongo_db_name][mongo_collection_name]

            if args.mode == "ids":
                total_rows = count_rows_by_ids(pg_conn, source_table, explicit_ids)
                print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
                rows = fetch_rows_by_ids(pg_conn, source_table, explicit_ids)
                upsert_rows(mongo_collection, rows, source_table)
                print(f"[{datetime.now().isoformat(timespec='seconds')}] repaired {len(rows)} explicit request_log_id rows")
                return

            if args.mode == "time":
                total_rows = count_rows_by_time(pg_conn, source_table, args.time_field, start_dt, end_dt)
                print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
                total_processed = backfill_by_time(pg_conn, mongo_collection, source_table, args.time_field, start_dt, end_dt, args.batch_size, total_rows)
                print(f"[{datetime.now().isoformat(timespec='seconds')}] completed time-based repair, total_rows={total_processed}")
                return

            id_from = args.id_from if args.id_from is not None else 0
            id_to = args.id_to if args.id_to is not None else 9223372036854775807
            total_rows = count_rows_by_id_range(pg_conn, source_table, id_from, id_to)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
            total_processed = backfill_by_id_range(pg_conn, mongo_collection, source_table, id_from, id_to, args.batch_size, total_rows)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] completed id-range repair, total_rows={total_processed}")


if __name__ == "__main__":
    main()
