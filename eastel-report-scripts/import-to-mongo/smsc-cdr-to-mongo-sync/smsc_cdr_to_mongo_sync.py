import argparse
import csv
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any

import yaml
from pymongo import ASCENDING, MongoClient, ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError


SCRIPT_NAME = "smsc_cdr_to_mongo_sync"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "smsc_cdrs"
DEFAULT_STATE_COLLECTION = "smsc_cdr_sync_state"
DEFAULT_BATCH_SIZE = 1000
DEFAULT_LOCK_TIMEOUT_SECONDS = 3600
FILE_NAME_PATTERN = re.compile(r"^cdr\.log\.(\d{4}-\d{2}-\d{2})$")
FIELD_NAMES = [
    "delivery_date",
    "submit_date",
    "addr_src_digits",
    "addr_src_ton",
    "addr_src_npi",
    "addr_dst_digits",
    "addr_dst_ton",
    "addr_dst_npi",
    "message_delivery_status",
    "origination_type",
    "message_type",
    "orig_system_id",
    "message_id",
    "dvl_message_id",
    "receipt_local_message_id",
    "nnn_digits",
    "imsi",
    "corr_id",
    "originator_sccp_address",
    "mt_service_center_address",
    "orig_network_id",
    "network_id",
    "mproc_notes",
    "msg_parts",
    "char_numbers",
    "processing_time",
    "delivery_delay",
    "schedule_delivery_delay",
    "delivery_count",
    "sms_text",
    "reason_for_failure",
]


@dataclass(frozen=True)
class FileCandidate:
    full_path: Path
    relative_path: str
    file_name: str
    file_date: date
    file_size: int
    last_modified_at: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import SMSC CDR files into MongoDB with resume, lock, and idempotent writes."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file used when env vars are not set.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one import cycle immediately and exit.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Keep running and trigger one import cycle per configured schedule time.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Reset file checkpoint state before the run. Existing Mongo documents stay safe because writes are upserts.",
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


def get_config_value(
    config: dict[str, Any],
    section: str,
    key: str,
    env_name: str,
    default: Any = None,
) -> Any:
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    section_data = config.get(section, {})
    if isinstance(section_data, dict) and key in section_data and section_data[key] not in (None, ""):
        return section_data[key]
    return default


def get_input_dir(config: dict[str, Any]) -> Path:
    input_dir = os.getenv("SMSC_CDR_INPUT_DIR") or config.get("source", {}).get("input_dir")
    if not input_dir:
        raise ValueError("Missing source input directory: SMSC_CDR_INPUT_DIR or source.input_dir")
    return Path(str(input_dir)).expanduser().resolve()


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI")
    return MongoClient(str(mongo_uri))


def get_mongo_db_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_database")
        if value not in (None, ""):
            return str(value)
    return str(default)


def get_cdr_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("smsc_cdr_collection")
        if value not in (None, ""):
            return str(value)
    return str(default)


def get_cdr_state_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("smsc_cdr_state_collection")
        if value not in (None, ""):
            return str(value)
    return str(default)


def get_schedule_time(config: dict[str, Any]) -> dt_time:
    raw_value = str(
        get_config_value(
            config,
            "sync",
            "schedule_time",
            "SMSC_CDR_SCHEDULE_TIME",
            "02:00",
        )
    ).strip()
    try:
        return datetime.strptime(raw_value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(
            f"Invalid schedule time '{raw_value}'. Expected HH:MM in 24-hour format."
        ) from exc


def should_run_continuously(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.run_once:
        return False
    if args.continuous:
        return True
    value = str(
        get_config_value(
            config,
            "sync",
            "continuous",
            "SMSC_CDR_CONTINUOUS",
            False,
        )
    ).strip().lower()
    return value in {"1", "true", "yes", "on"}


def configure_logging(config: dict[str, Any]) -> logging.Logger:
    logger = logging.getLogger(SCRIPT_NAME)
    if logger.handlers:
        return logger

    log_level_name = str(
        get_config_value(config, "logging", "level", "SMSC_CDR_LOG_LEVEL", "INFO")
    ).upper()
    level = getattr(logging, log_level_name, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(level)
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    log_file = get_config_value(config, "logging", "file_path", "SMSC_CDR_LOG_FILE")
    if log_file:
        log_path = Path(str(log_file)).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

    return logger


def ensure_collection(db, collection_name: str):
    if collection_name not in db.list_collection_names():
        db.create_collection(collection_name)
    return db[collection_name]


def ensure_indexes(data_collection, state_collection) -> None:
    data_collection.create_index(
        [("source_path", ASCENDING), ("line_number", ASCENDING)],
        name="uq_source_path_line_number",
        unique=True,
    )
    data_collection.create_index(
        [("source_file_date", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_source_file_date_delivery_date",
    )
    data_collection.create_index(
        [("message_id", ASCENDING)],
        name="ix_message_id",
    )
    data_collection.create_index(
        [("addr_src_digits", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_addr_src_digits_delivery_date",
    )
    data_collection.create_index(
        [("addr_dst_digits", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_addr_dst_digits_delivery_date",
    )
    state_collection.create_index(
        [("type", ASCENDING), ("mongo_collection", ASCENDING), ("status", ASCENDING)],
        name="ix_type_collection_status",
    )
    state_collection.create_index(
        [("type", ASCENDING), ("mongo_collection", ASCENDING), ("file_date", ASCENDING)],
        name="ix_type_collection_file_date",
    )


def get_state_key(mongo_collection_name: str) -> str:
    return f"state::{mongo_collection_name}"


def get_lock_key(mongo_collection_name: str) -> str:
    return f"lock::{mongo_collection_name}"


def get_file_state_key(mongo_collection_name: str, relative_path: str) -> str:
    return f"file::{mongo_collection_name}::{relative_path}"


def acquire_lock(
    state_collection,
    mongo_collection_name: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_lock_key(mongo_collection_name)
    now = datetime.now()
    expires_at = now + timedelta(seconds=lock_timeout_seconds)
    try:
        lock_doc = state_collection.find_one_and_update(
            {
                "_id": lock_key,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"owner_id": owner_id},
                    {"expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "type": "lock",
                    "owner_id": owner_id,
                    "mongo_collection": mongo_collection_name,
                    "updated_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise RuntimeError(
            f"Another {SCRIPT_NAME} instance is already running for collection {mongo_collection_name}."
        ) from exc

    if not lock_doc or lock_doc.get("owner_id") != owner_id:
        raise RuntimeError(
            f"Another {SCRIPT_NAME} instance is already running for collection {mongo_collection_name}."
        )


def refresh_lock(
    state_collection,
    mongo_collection_name: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_lock_key(mongo_collection_name)
    now = datetime.now()
    expires_at = now + timedelta(seconds=lock_timeout_seconds)
    result = state_collection.update_one(
        {"_id": lock_key, "owner_id": owner_id},
        {"$set": {"updated_at": now, "expires_at": expires_at}},
    )
    if result.matched_count != 1:
        raise RuntimeError(f"{SCRIPT_NAME} lock was lost during execution.")


def release_lock(state_collection, mongo_collection_name: str, owner_id: str) -> None:
    lock_key = get_lock_key(mongo_collection_name)
    state_collection.delete_one({"_id": lock_key, "owner_id": owner_id})


def reset_state(state_collection, mongo_collection_name: str) -> None:
    state_collection.delete_many(
        {
            "$or": [
                {"_id": get_state_key(mongo_collection_name)},
                {"_id": get_lock_key(mongo_collection_name)},
                {"_id": {"$regex": f"^file::{re.escape(mongo_collection_name)}::"}},
            ]
        }
    )


def update_cycle_state(
    state_collection,
    mongo_collection_name: str,
    *,
    status: str,
    last_cycle_started_at: datetime,
    last_cycle_completed_at: datetime | None = None,
    files_seen: int | None = None,
    files_processed: int | None = None,
    files_completed: int | None = None,
) -> None:
    state_collection.update_one(
        {"_id": get_state_key(mongo_collection_name)},
        {
            "$set": {
                "type": "cycle_state",
                "mongo_collection": mongo_collection_name,
                "status": status,
                "last_cycle_started_at": last_cycle_started_at,
                "last_cycle_completed_at": last_cycle_completed_at,
                "files_seen": files_seen,
                "files_processed": files_processed,
                "files_completed": files_completed,
                "updated_at": datetime.now(),
            }
        },
        upsert=True,
    )


def load_file_states(state_collection, mongo_collection_name: str) -> dict[str, dict[str, Any]]:
    state_docs = state_collection.find(
        {"type": "file", "mongo_collection": mongo_collection_name}
    )
    return {str(doc.get("relative_path")): doc for doc in state_docs if doc.get("relative_path")}


def count_lines(file_path: Path) -> tuple[int, float]:
    started_at = time.perf_counter()
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        total_lines = sum(1 for _ in handle)
    return total_lines, time.perf_counter() - started_at


def discover_eligible_files(input_dir: Path, current_date: date) -> list[FileCandidate]:
    candidates: list[FileCandidate] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        match = FILE_NAME_PATTERN.match(path.name)
        if not match:
            continue
        file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        if file_date >= current_date:
            continue
        stat = path.stat()
        candidates.append(
            FileCandidate(
                full_path=path,
                relative_path=path.relative_to(input_dir).as_posix(),
                file_name=path.name,
                file_date=file_date,
                file_size=stat.st_size,
                last_modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    candidates.sort(key=lambda item: (item.file_date, item.relative_path))
    return candidates


def should_process_file(candidate: FileCandidate, state_doc: dict[str, Any] | None) -> tuple[bool, str]:
    if not state_doc:
        return True, "new file"

    saved_size = state_doc.get("file_size")
    saved_mtime = state_doc.get("last_modified_at")
    metadata_changed = saved_size != candidate.file_size or saved_mtime != candidate.last_modified_at

    if state_doc.get("status") == "completed" and not metadata_changed:
        return False, "already completed"

    if metadata_changed:
        return True, "file metadata changed since last run"

    if state_doc.get("status") == "completed":
        return False, "already completed"

    return True, "resume incomplete file"


def has_same_file_metadata(candidate: FileCandidate, state_doc: dict[str, Any] | None) -> bool:
    if not state_doc:
        return False
    return (
        state_doc.get("file_size") == candidate.file_size
        and state_doc.get("last_modified_at") == candidate.last_modified_at
    )


def extract_cdr_payload(line: str) -> str | None:
    parts = line.split("] ", 1)
    if len(parts) != 2:
        return None
    payload = parts[1].strip()
    return payload or None


def normalize_field(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.lower() == "null":
        return None
    return stripped


def parse_cdr_payload(payload: str) -> tuple[dict[str, Any], list[str]]:
    fields = list(csv.reader([payload]))[0]
    parsed: dict[str, Any] = {}
    for index, field_name in enumerate(FIELD_NAMES):
        parsed[field_name] = normalize_field(fields[index]) if index < len(fields) else None
    return parsed, fields


def build_update_operation(
    candidate: FileCandidate,
    line_number: int,
    raw_line: str,
    payload: str,
    parsed_fields: dict[str, Any],
    raw_fields: list[str],
) -> UpdateOne:
    document = {
        "source_path": candidate.relative_path,
        "source_file": candidate.file_name,
        "source_full_path": str(candidate.full_path),
        "source_file_date": candidate.file_date.isoformat(),
        "source_file_size": candidate.file_size,
        "source_last_modified_at": candidate.last_modified_at,
        "line_number": line_number,
        "raw_line": raw_line.rstrip("\n"),
        "raw_cdr": payload,
        "raw_fields_count": len(raw_fields),
        "extra_fields": raw_fields[len(FIELD_NAMES):] if len(raw_fields) > len(FIELD_NAMES) else [],
        "synced_at": datetime.now(),
        **parsed_fields,
    }
    return UpdateOne(
        {"source_path": candidate.relative_path, "line_number": line_number},
        {"$set": document},
        upsert=True,
    )


def save_file_progress(
    state_collection,
    mongo_collection_name: str,
    candidate: FileCandidate,
    *,
    status: str,
    last_processed_line: int,
    total_lines: int,
    records_upserted: int,
    parse_errors: int,
    invalid_prefix_lines: int,
    count_duration_seconds: float,
    read_duration_seconds: float,
    write_duration_seconds: float,
    started_at: datetime,
) -> None:
    state_collection.update_one(
        {"_id": get_file_state_key(mongo_collection_name, candidate.relative_path)},
        {
            "$set": {
                "type": "file",
                "mongo_collection": mongo_collection_name,
                "relative_path": candidate.relative_path,
                "file_name": candidate.file_name,
                "file_date": candidate.file_date.isoformat(),
                "file_size": candidate.file_size,
                "last_modified_at": candidate.last_modified_at,
                "status": status,
                "last_processed_line": last_processed_line,
                "total_lines": total_lines,
                "records_upserted": records_upserted,
                "parse_errors": parse_errors,
                "invalid_prefix_lines": invalid_prefix_lines,
                "count_duration_seconds": round(count_duration_seconds, 6),
                "read_duration_seconds": round(read_duration_seconds, 6),
                "write_duration_seconds": round(write_duration_seconds, 6),
                "started_at": started_at,
                "updated_at": datetime.now(),
            }
        },
        upsert=True,
    )


def flush_batch(
    *,
    data_collection,
    state_collection,
    mongo_collection_name: str,
    candidate: FileCandidate,
    owner_id: str,
    lock_timeout_seconds: int,
    batch_operations: list[UpdateOne],
    checkpoint_line: int,
    total_lines: int,
    records_upserted: int,
    parse_errors: int,
    invalid_prefix_lines: int,
    count_duration_seconds: float,
    accumulated_read_duration_seconds: float,
    accumulated_write_duration_seconds: float,
    started_at: datetime,
    logger: logging.Logger,
) -> tuple[int, float]:
    refresh_lock(state_collection, mongo_collection_name, owner_id, lock_timeout_seconds)

    write_duration_seconds = 0.0
    batch_size = len(batch_operations)
    if batch_operations:
        mongo_write_started_at = time.perf_counter()
        data_collection.bulk_write(batch_operations, ordered=False)
        write_duration_seconds = time.perf_counter() - mongo_write_started_at
        accumulated_write_duration_seconds += write_duration_seconds
        records_upserted += batch_size

    save_file_progress(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        candidate=candidate,
        status="in_progress",
        last_processed_line=checkpoint_line,
        total_lines=total_lines,
        records_upserted=records_upserted,
        parse_errors=parse_errors,
        invalid_prefix_lines=invalid_prefix_lines,
        count_duration_seconds=count_duration_seconds,
        read_duration_seconds=accumulated_read_duration_seconds,
        write_duration_seconds=accumulated_write_duration_seconds,
        started_at=started_at,
    )

    logger.info(
        "file=%s batch_checkpoint=%s/%s batch_rows=%s read=%.3fs mongo_write=%.3fs cumulative_upserts=%s parse_errors=%s invalid_prefix=%s",
        candidate.relative_path,
        checkpoint_line,
        total_lines,
        batch_size,
        accumulated_read_duration_seconds,
        write_duration_seconds,
        records_upserted,
        parse_errors,
        invalid_prefix_lines,
    )
    return records_upserted, accumulated_write_duration_seconds


def process_file(
    *,
    data_collection,
    state_collection,
    mongo_collection_name: str,
    candidate: FileCandidate,
    state_doc: dict[str, Any] | None,
    batch_size: int,
    owner_id: str,
    lock_timeout_seconds: int,
    logger: logging.Logger,
    file_position: int,
    total_files: int,
) -> dict[str, Any]:
    file_started_at = datetime.now()
    logger.info(
        "processing file %s/%s: %s (date=%s size=%s bytes)",
        file_position,
        total_files,
        candidate.relative_path,
        candidate.file_date.isoformat(),
        candidate.file_size,
    )

    total_lines, count_duration_seconds = count_lines(candidate.full_path)
    metadata_matches_state = has_same_file_metadata(candidate, state_doc)
    saved_line = 0
    if state_doc and metadata_matches_state and state_doc.get("status") != "completed":
        saved_line = int(state_doc.get("last_processed_line", 0))
    if saved_line > total_lines:
        saved_line = 0

    logger.info(
        "file=%s total_lines=%s count_time=%.3fs resume_line=%s",
        candidate.relative_path,
        total_lines,
        count_duration_seconds,
        saved_line,
    )

    records_upserted = int(state_doc.get("records_upserted", 0)) if metadata_matches_state and state_doc else 0
    parse_errors = int(state_doc.get("parse_errors", 0)) if metadata_matches_state and state_doc else 0
    invalid_prefix_lines = (
        int(state_doc.get("invalid_prefix_lines", 0))
        if metadata_matches_state and state_doc
        else 0
    )
    batch_operations: list[UpdateOne] = []
    accumulated_read_duration_seconds = (
        float(state_doc.get("read_duration_seconds", 0.0))
        if metadata_matches_state and state_doc
        else 0.0
    )
    accumulated_write_duration_seconds = (
        float(state_doc.get("write_duration_seconds", 0.0))
        if metadata_matches_state and state_doc
        else 0.0
    )
    batch_read_started_at = time.perf_counter()
    last_processed_line = saved_line

    save_file_progress(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        candidate=candidate,
        status="in_progress",
        last_processed_line=saved_line,
        total_lines=total_lines,
        records_upserted=records_upserted,
        parse_errors=parse_errors,
        invalid_prefix_lines=invalid_prefix_lines,
        count_duration_seconds=count_duration_seconds,
        read_duration_seconds=accumulated_read_duration_seconds,
        write_duration_seconds=accumulated_write_duration_seconds,
        started_at=file_started_at,
    )

    with candidate.full_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if line_number <= saved_line:
                continue

            last_processed_line = line_number
            payload = extract_cdr_payload(raw_line)
            if payload is None:
                invalid_prefix_lines += 1
                continue

            try:
                parsed_fields, raw_fields = parse_cdr_payload(payload)
            except Exception:
                parse_errors += 1
                continue

            batch_operations.append(
                build_update_operation(
                    candidate=candidate,
                    line_number=line_number,
                    raw_line=raw_line,
                    payload=payload,
                    parsed_fields=parsed_fields,
                    raw_fields=raw_fields,
                )
            )

            if len(batch_operations) >= batch_size:
                accumulated_read_duration_seconds += time.perf_counter() - batch_read_started_at
                records_upserted, accumulated_write_duration_seconds = flush_batch(
                    data_collection=data_collection,
                    state_collection=state_collection,
                    mongo_collection_name=mongo_collection_name,
                    candidate=candidate,
                    owner_id=owner_id,
                    lock_timeout_seconds=lock_timeout_seconds,
                    batch_operations=batch_operations,
                    checkpoint_line=line_number,
                    total_lines=total_lines,
                    records_upserted=records_upserted,
                    parse_errors=parse_errors,
                    invalid_prefix_lines=invalid_prefix_lines,
                    count_duration_seconds=count_duration_seconds,
                    accumulated_read_duration_seconds=accumulated_read_duration_seconds,
                    accumulated_write_duration_seconds=accumulated_write_duration_seconds,
                    started_at=file_started_at,
                    logger=logger,
                )
                batch_operations = []
                batch_read_started_at = time.perf_counter()

    accumulated_read_duration_seconds += time.perf_counter() - batch_read_started_at
    if batch_operations or last_processed_line != saved_line:
        records_upserted, accumulated_write_duration_seconds = flush_batch(
            data_collection=data_collection,
            state_collection=state_collection,
            mongo_collection_name=mongo_collection_name,
            candidate=candidate,
            owner_id=owner_id,
            lock_timeout_seconds=lock_timeout_seconds,
            batch_operations=batch_operations,
            checkpoint_line=last_processed_line,
            total_lines=total_lines,
            records_upserted=records_upserted,
            parse_errors=parse_errors,
            invalid_prefix_lines=invalid_prefix_lines,
            count_duration_seconds=count_duration_seconds,
            accumulated_read_duration_seconds=accumulated_read_duration_seconds,
            accumulated_write_duration_seconds=accumulated_write_duration_seconds,
            started_at=file_started_at,
            logger=logger,
        )

    save_file_progress(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        candidate=candidate,
        status="completed",
        last_processed_line=last_processed_line,
        total_lines=total_lines,
        records_upserted=records_upserted,
        parse_errors=parse_errors,
        invalid_prefix_lines=invalid_prefix_lines,
        count_duration_seconds=count_duration_seconds,
        read_duration_seconds=accumulated_read_duration_seconds,
        write_duration_seconds=accumulated_write_duration_seconds,
        started_at=file_started_at,
    )

    file_total_duration_seconds = (datetime.now() - file_started_at).total_seconds()
    logger.info(
        "completed file=%s total_lines=%s upserts=%s parse_errors=%s invalid_prefix=%s count=%.3fs read=%.3fs mongo_write=%.3fs file_total=%.3fs",
        candidate.relative_path,
        total_lines,
        records_upserted,
        parse_errors,
        invalid_prefix_lines,
        count_duration_seconds,
        accumulated_read_duration_seconds,
        accumulated_write_duration_seconds,
        file_total_duration_seconds,
    )

    return {
        "relative_path": candidate.relative_path,
        "total_lines": total_lines,
        "records_upserted": records_upserted,
        "parse_errors": parse_errors,
        "invalid_prefix_lines": invalid_prefix_lines,
        "file_total_duration_seconds": file_total_duration_seconds,
    }


def run_sync_cycle(
    *,
    input_dir: Path,
    data_collection,
    state_collection,
    mongo_collection_name: str,
    batch_size: int,
    owner_id: str,
    lock_timeout_seconds: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    cycle_started_at = datetime.now()
    current_date = cycle_started_at.date()
    file_states = load_file_states(state_collection, mongo_collection_name)
    eligible_files = discover_eligible_files(input_dir, current_date)

    files_to_process: list[tuple[FileCandidate, dict[str, Any] | None, str]] = []
    skipped_completed = 0
    for candidate in eligible_files:
        state_doc = file_states.get(candidate.relative_path)
        should_process, reason = should_process_file(candidate, state_doc)
        if should_process:
            files_to_process.append((candidate, state_doc, reason))
        else:
            skipped_completed += 1

    logger.info(
        "eligible_files=%s pending_files=%s completed_files=%s current_date=%s input_dir=%s",
        len(eligible_files),
        len(files_to_process),
        skipped_completed,
        current_date.isoformat(),
        input_dir,
    )

    update_cycle_state(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        status="running",
        last_cycle_started_at=cycle_started_at,
        files_seen=len(eligible_files),
        files_processed=len(files_to_process),
        files_completed=skipped_completed,
    )

    processed_files = 0
    summaries = []
    for index, (candidate, state_doc, reason) in enumerate(files_to_process, start=1):
        refresh_lock(state_collection, mongo_collection_name, owner_id, lock_timeout_seconds)
        logger.info("queue file=%s reason=%s", candidate.relative_path, reason)
        summaries.append(
            process_file(
                data_collection=data_collection,
                state_collection=state_collection,
                mongo_collection_name=mongo_collection_name,
                candidate=candidate,
                state_doc=state_doc,
                batch_size=batch_size,
                owner_id=owner_id,
                lock_timeout_seconds=lock_timeout_seconds,
                logger=logger,
                file_position=index,
                total_files=len(files_to_process),
            )
        )
        processed_files += 1

    cycle_completed_at = datetime.now()
    update_cycle_state(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        status="completed",
        last_cycle_started_at=cycle_started_at,
        last_cycle_completed_at=cycle_completed_at,
        files_seen=len(eligible_files),
        files_processed=processed_files,
        files_completed=skipped_completed + processed_files,
    )

    logger.info(
        "cycle complete processed_files=%s skipped_completed=%s cycle_total=%.3fs",
        processed_files,
        skipped_completed,
        (cycle_completed_at - cycle_started_at).total_seconds(),
    )
    return {
        "eligible_files": len(eligible_files),
        "pending_files": len(files_to_process),
        "processed_files": processed_files,
        "skipped_completed": skipped_completed,
        "summaries": summaries,
    }


def get_next_run_at(schedule_time: dt_time, now: datetime) -> datetime:
    candidate = datetime.combine(now.date(), schedule_time)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    logger = configure_logging(config)

    input_dir = get_input_dir(config)
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Configured input directory does not exist or is not a directory: {input_dir}")

    mongo_db_name = get_mongo_db_name(
        config,
        get_config_value(config, "mongo", "database", "MONGO_DB", DEFAULT_MONGO_DB),
    )
    mongo_collection_name = get_cdr_collection_name(
        config,
        get_config_value(config, "mongo", "collection", "MONGO_COLLECTION", DEFAULT_MONGO_COLLECTION),
    )
    state_collection_name = get_cdr_state_collection_name(
        config,
        get_config_value(
            config,
            "mongo",
            "state_collection",
            "MONGO_STATE_COLLECTION",
            DEFAULT_STATE_COLLECTION,
        ),
    )
    batch_size = int(
        get_config_value(config, "sync", "batch_size", "SYNC_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    )
    lock_timeout_seconds = int(
        get_config_value(
            config,
            "sync",
            "lock_timeout_seconds",
            "SYNC_LOCK_TIMEOUT_SECONDS",
            DEFAULT_LOCK_TIMEOUT_SECONDS,
        )
    )
    schedule_time = get_schedule_time(config)
    continuous_mode = should_run_continuously(args, config)
    owner_id = str(uuid.uuid4())

    logger.info(
        "starting %s input_dir=%s mongo_db=%s collection=%s state_collection=%s batch_size=%s continuous=%s schedule_time=%s",
        SCRIPT_NAME,
        input_dir,
        mongo_db_name,
        mongo_collection_name,
        state_collection_name,
        batch_size,
        continuous_mode,
        schedule_time.strftime("%H:%M"),
    )

    with get_mongo_client(config) as mongo_client:
        mongo_db = mongo_client[mongo_db_name]
        data_collection = ensure_collection(mongo_db, mongo_collection_name)
        state_collection = ensure_collection(mongo_db, state_collection_name)
        ensure_indexes(data_collection, state_collection)

        if args.reset_state:
            reset_state(state_collection, mongo_collection_name)
            logger.info("reset state for collection=%s", mongo_collection_name)

        if not continuous_mode:
            acquire_lock(state_collection, mongo_collection_name, owner_id, lock_timeout_seconds)
            logger.info("acquired lock for collection=%s", mongo_collection_name)
            try:
                run_sync_cycle(
                    input_dir=input_dir,
                    data_collection=data_collection,
                    state_collection=state_collection,
                    mongo_collection_name=mongo_collection_name,
                    batch_size=batch_size,
                    owner_id=owner_id,
                    lock_timeout_seconds=lock_timeout_seconds,
                    logger=logger,
                )
            finally:
                release_lock(state_collection, mongo_collection_name, owner_id)
                logger.info("released lock for collection=%s", mongo_collection_name)
            return

        while True:
            now = datetime.now()
            next_run_at = get_next_run_at(schedule_time, now)
            sleep_seconds = max((next_run_at - now).total_seconds(), 0.0)
            logger.info(
                "waiting until next scheduled run at %s (sleep %.1fs)",
                next_run_at.strftime("%Y-%m-%d %H:%M:%S"),
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

            owner_id = str(uuid.uuid4())
            acquire_lock(state_collection, mongo_collection_name, owner_id, lock_timeout_seconds)
            logger.info("acquired lock for collection=%s", mongo_collection_name)
            try:
                run_sync_cycle(
                    input_dir=input_dir,
                    data_collection=data_collection,
                    state_collection=state_collection,
                    mongo_collection_name=mongo_collection_name,
                    batch_size=batch_size,
                    owner_id=owner_id,
                    lock_timeout_seconds=lock_timeout_seconds,
                    logger=logger,
                )
            finally:
                release_lock(state_collection, mongo_collection_name, owner_id)
                logger.info("released lock for collection=%s", mongo_collection_name)


if __name__ == "__main__":
    main()
