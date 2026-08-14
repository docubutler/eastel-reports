import argparse
import os
import time
from datetime import datetime
from typing import Any

import psycopg
from bson.decimal128 import Decimal128
from psycopg.rows import dict_row

from backfill_usage_logs import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_SOURCE_TABLE,
    build_effective_args,
    count_rows_by_id_range,
    count_rows_by_ids,
    count_rows_by_time,
    fetch_rows_by_id_range,
    fetch_rows_by_ids,
    fetch_rows_by_time,
    parse_ids,
    parse_iso_datetime,
    validate_args,
)
from postgres_to_mongo_usage_sync import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MONGO_COLLECTION,
    DEFAULT_MONGO_DB,
    get_config_value,
    get_mongo_client,
    get_postgres_dsn,
    get_usage_collection_name,
    get_usage_mongo_db_name,
    get_usage_source_table,
    load_config,
    transform_row,
)


DEFAULT_MISMATCH_SAMPLE_LIMIT = 100
IGNORED_PATHS = {("_id",), ("sync_metadata", "synced_at")}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect usage log MongoDB documents against PostgreSQL source rows."
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
        help="Inspection scope mode. If omitted, config backfill.mode is used.",
    )
    parser.add_argument(
        "--time-field",
        choices=["usage_start_time", "usage_update_time", "up_time", "cr_time"],
        default="",
        help="Timestamp field to use with --start/--end. Recommended: usage_update_time.",
    )
    parser.add_argument("--start", default="", help="Inclusive ISO datetime lower bound.")
    parser.add_argument("--end", default="", help="Exclusive ISO datetime upper bound.")
    parser.add_argument("--id-from", type=int, default=None, help="Inclusive lower bound for usage_log_id.")
    parser.add_argument("--id-to", type=int, default=None, help="Inclusive upper bound for usage_log_id.")
    parser.add_argument("--ids", default="", help="Comma-separated explicit usage_log_id values to inspect.")
    parser.add_argument(
        "--min-record-age-seconds",
        type=int,
        default=None,
        help="Time mode only: skip rows whose cr_time is newer than now minus this many seconds.",
    )
    parser.add_argument(
        "--mismatch-sample-limit",
        type=int,
        default=DEFAULT_MISMATCH_SAMPLE_LIMIT,
        help="Maximum number of mismatched usage_log_id values to print.",
    )
    return parser.parse_args()


def build_effective_inspect_args(args: argparse.Namespace, config: dict[str, Any]) -> argparse.Namespace:
    effective = build_effective_args(args, config)
    backfill_config = config.get("backfill", {}) or {}
    if effective.mismatch_sample_limit == DEFAULT_MISMATCH_SAMPLE_LIMIT:
        config_value = backfill_config.get("mismatch_sample_limit")
        if config_value not in (None, ""):
            effective.mismatch_sample_limit = int(config_value)
    if effective.mismatch_sample_limit < 0:
        raise ValueError("mismatch_sample_limit cannot be negative.")
    return effective


def comparable_value(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return str(value)
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, dict):
        return {key: comparable_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [comparable_value(child) for child in value]
    return value


def values_equal(expected: Any, actual: Any) -> bool:
    return comparable_value(expected) == comparable_value(actual)


def expected_projection(expected_doc: dict[str, Any]) -> dict[str, int]:
    projection = {"_id": 0}
    for key in expected_doc:
        if (key,) not in IGNORED_PATHS:
            projection[key] = 1
    return projection


def get_nested(document: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = document
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def expected_paths(document: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    paths = []
    for key, value in document.items():
        path = prefix + (key,)
        if path in IGNORED_PATHS:
            continue
        if isinstance(value, dict):
            paths.extend(expected_paths(value, path))
        else:
            paths.append((path, value))
    return paths


def document_has_field_mismatch(expected_doc: dict[str, Any], mongo_doc: dict[str, Any]) -> bool:
    for path, expected_value in expected_paths(expected_doc):
        found, actual_value = get_nested(mongo_doc, path)
        if not found or not values_equal(expected_value, actual_value):
            return True
    return False


def inspect_rows(
    mongo_collection,
    rows: list[dict[str, Any]],
    source_table: str,
    sample_limit: int,
    sample_ids: list[int],
) -> tuple[int, int]:
    if not rows:
        return 0, 0

    expected_by_id = {
        int(row["usage_log_id"]): transform_row(row, source_table)
        for row in rows
    }
    projection = expected_projection(next(iter(expected_by_id.values())))
    mongo_docs = {
        int(doc["usage_log_id"]): doc
        for doc in mongo_collection.find({"usage_log_id": {"$in": list(expected_by_id)}}, projection)
        if doc.get("usage_log_id") is not None
    }

    missing_count = 0
    field_mismatch_count = 0
    for usage_log_id, expected_doc in expected_by_id.items():
        mongo_doc = mongo_docs.get(usage_log_id)
        is_mismatched = False
        if mongo_doc is None:
            missing_count += 1
            is_mismatched = True
        elif document_has_field_mismatch(expected_doc, mongo_doc):
            field_mismatch_count += 1
            is_mismatched = True

        if is_mismatched and len(sample_ids) < sample_limit:
            sample_ids.append(usage_log_id)

    return missing_count, field_mismatch_count


def print_progress(
    scanned_rows: int,
    total_rows: int,
    missing_count: int,
    field_mismatch_count: int,
    last_usage_log_id: int,
    batch_started_at: float,
) -> None:
    mismatched_count = missing_count + field_mismatch_count
    matched_count = scanned_rows - mismatched_count
    percent = (scanned_rows / total_rows * 100.0) if total_rows > 0 else 100.0
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"scanned={scanned_rows}/{total_rows}, percent={percent:.2f}%, "
        f"matched={matched_count}, "
        f"missing={missing_count}, field_mismatches={field_mismatch_count}, "
        f"total_mismatched={mismatched_count}, last_usage_log_id={last_usage_log_id}, "
        f"batch_total={time.perf_counter() - batch_started_at:.3f}s"
    )


def print_summary(
    total_rows: int,
    scanned_rows: int,
    missing_count: int,
    field_mismatch_count: int,
    sample_limit: int,
    sample_ids: list[int],
) -> None:
    mismatched_count = missing_count + field_mismatch_count
    matched_count = scanned_rows - mismatched_count
    print("\nInspection summary")
    print(f"total_postgres_rows={total_rows}")
    print(f"total_rows_scanned={scanned_rows}")
    print(f"total_matched_records={matched_count}")
    print(f"mongo_documents_missing={missing_count}")
    print(f"records_with_field_mismatches={field_mismatch_count}")
    print(f"total_mismatched_records={mismatched_count}")
    print(f"mismatch_sample_limit={sample_limit}")
    print(f"sampled_mismatched_usage_log_ids={sample_ids}")


def inspect_by_time(
    pg_conn,
    mongo_collection,
    source_table: str,
    time_field: str,
    start_dt: datetime,
    end_dt: datetime,
    batch_size: int,
    total_rows: int,
    min_record_age_seconds: int,
    sample_limit: int,
) -> None:
    last_usage_log_id = 0
    scanned_rows = 0
    missing_count = 0
    field_mismatch_count = 0
    sample_ids: list[int] = []

    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_time(
            pg_conn,
            source_table,
            time_field,
            start_dt,
            end_dt,
            last_usage_log_id,
            batch_size,
            min_record_age_seconds,
        )
        if not rows:
            break
        last_usage_log_id = int(rows[-1]["usage_log_id"])
        batch_missing, batch_field_mismatches = inspect_rows(
            mongo_collection, rows, source_table, sample_limit, sample_ids
        )
        scanned_rows += len(rows)
        missing_count += batch_missing
        field_mismatch_count += batch_field_mismatches
        print_progress(scanned_rows, total_rows, missing_count, field_mismatch_count, last_usage_log_id, batch_started_at)
        if len(rows) < batch_size:
            break

    print_summary(total_rows, scanned_rows, missing_count, field_mismatch_count, sample_limit, sample_ids)


def inspect_by_id_range(
    pg_conn,
    mongo_collection,
    source_table: str,
    id_from: int,
    id_to: int,
    batch_size: int,
    total_rows: int,
    sample_limit: int,
) -> None:
    last_usage_log_id = id_from - 1
    scanned_rows = 0
    missing_count = 0
    field_mismatch_count = 0
    sample_ids: list[int] = []

    while True:
        batch_started_at = time.perf_counter()
        rows = fetch_rows_by_id_range(pg_conn, source_table, id_from, id_to, last_usage_log_id, batch_size)
        if not rows:
            break
        last_usage_log_id = int(rows[-1]["usage_log_id"])
        batch_missing, batch_field_mismatches = inspect_rows(
            mongo_collection, rows, source_table, sample_limit, sample_ids
        )
        scanned_rows += len(rows)
        missing_count += batch_missing
        field_mismatch_count += batch_field_mismatches
        print_progress(scanned_rows, total_rows, missing_count, field_mismatch_count, last_usage_log_id, batch_started_at)
        if len(rows) < batch_size:
            break

    print_summary(total_rows, scanned_rows, missing_count, field_mismatch_count, sample_limit, sample_ids)


def main() -> None:
    raw_args = parse_args()
    config = load_config(raw_args.config)
    args = build_effective_inspect_args(raw_args, config)
    validate_args(args)

    postgres_dsn = get_postgres_dsn(config)
    source_table = args.source_table or str(
        get_usage_source_table(
            config,
            get_config_value(config, "sync", "source_table", "PG_SOURCE_TABLE", DEFAULT_SOURCE_TABLE),
        )
    )
    mongo_db_name = get_usage_mongo_db_name(
        config,
        str(get_config_value(config, "mongo", "database", "MONGO_DB", args.mongo_db)),
    )
    mongo_collection_name = get_usage_collection_name(
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
                print(f"[{datetime.now().isoformat(timespec='seconds')}] calculating total rows for explicit usage_log_id list")
                total_rows = count_rows_by_ids(pg_conn, source_table, explicit_ids)
                rows = fetch_rows_by_ids(pg_conn, source_table, explicit_ids)
                sample_ids: list[int] = []
                missing_count, field_mismatch_count = inspect_rows(
                    mongo_collection,
                    rows,
                    source_table,
                    args.mismatch_sample_limit,
                    sample_ids,
                )
                print_summary(
                    total_rows,
                    len(rows),
                    missing_count,
                    field_mismatch_count,
                    args.mismatch_sample_limit,
                    sample_ids,
                )
                return

            if args.mode == "time":
                total_rows = count_rows_by_time(
                    pg_conn,
                    source_table,
                    args.time_field,
                    start_dt,
                    end_dt,
                    args.min_record_age_seconds,
                )
                print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
                inspect_by_time(
                    pg_conn,
                    mongo_collection,
                    source_table,
                    args.time_field,
                    start_dt,
                    end_dt,
                    args.batch_size,
                    total_rows,
                    args.min_record_age_seconds,
                    args.mismatch_sample_limit,
                )
                return

            id_from = args.id_from if args.id_from is not None else 0
            id_to = args.id_to if args.id_to is not None else 9223372036854775807
            total_rows = count_rows_by_id_range(pg_conn, source_table, id_from, id_to)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] total matching rows={total_rows}")
            inspect_by_id_range(
                pg_conn,
                mongo_collection,
                source_table,
                id_from,
                id_to,
                args.batch_size,
                total_rows,
                args.mismatch_sample_limit,
            )


if __name__ == "__main__":
    main()
