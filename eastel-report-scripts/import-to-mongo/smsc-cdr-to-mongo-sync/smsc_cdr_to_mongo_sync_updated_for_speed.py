import argparse
import csv
import gzip
import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from contextlib import nullcontext
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
DEFAULT_FILE_META_COLLECTION = "smsc_cdr_file_meta"
DEFAULT_BATCH_SIZE = 1000
DEFAULT_LOCK_TIMEOUT_SECONDS = 3600
FILE_NAME_PATTERN = re.compile(r"^(cdr\.log\.(\d{4}-\d{2}-\d{2}))(?:\.gz)?$")
FILE_HASH_ALGORITHM = "blake2b-256"
FILE_HASH_CHUNK_SIZE = 8 * 1024 * 1024
# Match the field order used by the working MySQL parser. The sample payloads do not
# contain a real submit_date column, even though some older docs/comments say they do.
FIELD_NAMES = [
    "delivery_date",
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
KNOWN_MESSAGE_DELIVERY_STATUSES = {
    "temp_failed",
    "success",
    "success_esme",
    "ocs_rejected",
    "failed",
    "temp_failed_esme",
    "partial",
}
KNOWN_ORIGINATION_TYPES = {"SMPP", "LOCAL_ORIG", "SS7_MO"}
KNOWN_MESSAGE_TYPES = {"message", "dlr"}

PENDING_FILE_META_STATUSES = {"pending", "in_progress", "failed"}


@dataclass
class FileCandidate:
    full_path: Path
    relative_path: str
    file_name: str
    file_date: date
    file_size: int
    last_modified_at: datetime
    source_full_path: Path | None = None
    logical_file_name: str | None = None
    source_file_size: int | None = None
    is_gzip: bool = False
    extracted_temp_path: Path | None = None
    server_name: str | None = None
    file_hash: str | None = None
    hash_duration_seconds: float | None = None


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


def get_processed_dir(config: dict[str, Any]) -> Path:
    processed_dir = os.getenv("SMSC_CDR_PROCESSED_DIR") or config.get("source", {}).get("processed_dir")
    if not processed_dir:
        raise ValueError("Missing processed directory: SMSC_CDR_PROCESSED_DIR or source.processed_dir")
    return Path(str(processed_dir)).expanduser().resolve()


def get_server_name(config: dict[str, Any]) -> str:
    server_name = os.getenv("SMSC_CDR_SERVER_NAME") or config.get("source", {}).get("server_name")
    if not server_name:
        raise ValueError("Missing source server name: SMSC_CDR_SERVER_NAME or source.server_name")
    return str(server_name).strip()


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


def get_cdr_file_meta_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("smsc_cdr_file_meta_collection")
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


def get_error_file_path(config: dict[str, Any]) -> Path | None:
    error_file = get_config_value(
        config,
        "logging",
        "error_file_path",
        "SMSC_CDR_ERROR_LOG_FILE",
    )
    if error_file in (None, ""):
        return None
    return Path(str(error_file)).expanduser()


def is_path_within(path: Path, parent: Path | None) -> bool:
    if parent is None:
        return False
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def parse_candidate_file_name(file_name: str) -> tuple[str, date, bool] | None:
    match = FILE_NAME_PATTERN.match(file_name)
    if not match:
        return None
    logical_file_name = match.group(1)
    file_date = datetime.strptime(match.group(2), "%Y-%m-%d").date()
    return logical_file_name, file_date, file_name.endswith(".gz")


def ensure_collection(db, collection_name: str):
    if collection_name not in db.list_collection_names():
        db.create_collection(collection_name)
    return db[collection_name]


def ensure_indexes(data_collection, state_collection, file_meta_collection) -> None:
    data_collection.create_index(
        [("identity_key", ASCENDING)],
        name="uq_identity_key",
        unique=True,
        partialFilterExpression={"identity_key": {"$exists": True}},
    )
    data_collection.create_index(
        [("server_name", ASCENDING), ("source_file_date", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_server_source_file_date_delivery_date",
    )
    data_collection.create_index(
        [("server_name", ASCENDING), ("message_id", ASCENDING)],
        name="ix_server_message_id",
    )
    data_collection.create_index(
        [("server_name", ASCENDING), ("addr_src_digits", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_server_addr_src_digits_delivery_date",
    )
    data_collection.create_index(
        [("server_name", ASCENDING), ("addr_dst_digits", ASCENDING), ("delivery_date", ASCENDING)],
        name="ix_server_addr_dst_digits_delivery_date",
    )
    state_collection.create_index(
        [("type", ASCENDING), ("mongo_collection", ASCENDING), ("server_name", ASCENDING), ("status", ASCENDING)],
        name="ix_type_collection_server_status",
    )
    state_collection.create_index(
        [("type", ASCENDING), ("mongo_collection", ASCENDING), ("server_name", ASCENDING), ("expires_at", ASCENDING)],
        name="ix_type_collection_server_expires_at",
    )
    file_meta_collection.create_index(
        [("mongo_collection", ASCENDING), ("server_name", ASCENDING), ("file_hash", ASCENDING)],
        name="uq_collection_server_file_hash",
        unique=True,
    )
    file_meta_collection.create_index(
        [("mongo_collection", ASCENDING), ("server_name", ASCENDING), ("status", ASCENDING)],
        name="ix_collection_server_status",
    )
    file_meta_collection.create_index(
        [("mongo_collection", ASCENDING), ("server_name", ASCENDING), ("file_name", ASCENDING)],
        name="ix_collection_server_file_name",
    )


def build_identity_key(server_name: str, file_hash: str, line_number: int) -> str:
    return f"{server_name}::{file_hash}::{line_number}"


def get_cycle_state_key(mongo_collection_name: str, server_name: str) -> str:
    return f"cycle::{mongo_collection_name}::{server_name}"


def get_file_lock_key(mongo_collection_name: str, server_name: str, file_hash: str) -> str:
    return f"lock::{mongo_collection_name}::{server_name}::{file_hash}"


def get_file_meta_key(mongo_collection_name: str, server_name: str, file_hash: str) -> str:
    return f"file_meta::{mongo_collection_name}::{server_name}::{file_hash}"


def acquire_file_lock(
    state_collection,
    mongo_collection_name: str,
    server_name: str,
    file_hash: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_file_lock_key(mongo_collection_name, server_name, file_hash)
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
                    "type": "file_lock",
                    "owner_id": owner_id,
                    "mongo_collection": mongo_collection_name,
                    "server_name": server_name,
                    "file_hash": file_hash,
                    "updated_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise RuntimeError(
            f"Another {SCRIPT_NAME} instance is already running for server={server_name} file_hash={file_hash}."
        ) from exc

    if not lock_doc or lock_doc.get("owner_id") != owner_id:
        raise RuntimeError(
            f"Another {SCRIPT_NAME} instance is already running for server={server_name} file_hash={file_hash}."
        )


def refresh_file_lock(
    state_collection,
    mongo_collection_name: str,
    server_name: str,
    file_hash: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_file_lock_key(mongo_collection_name, server_name, file_hash)
    now = datetime.now()
    expires_at = now + timedelta(seconds=lock_timeout_seconds)
    result = state_collection.update_one(
        {"_id": lock_key, "owner_id": owner_id},
        {"$set": {"updated_at": now, "expires_at": expires_at}},
    )
    if result.matched_count != 1:
        raise RuntimeError(f"{SCRIPT_NAME} file lock was lost during execution.")


def release_file_lock(
    state_collection,
    mongo_collection_name: str,
    server_name: str,
    file_hash: str,
    owner_id: str,
) -> None:
    lock_key = get_file_lock_key(mongo_collection_name, server_name, file_hash)
    state_collection.delete_one({"_id": lock_key, "owner_id": owner_id})


def reset_state(state_collection, file_meta_collection, mongo_collection_name: str, server_name: str) -> None:
    now = datetime.now()
    state_collection.delete_many(
        {
            "$or": [
                {"_id": get_cycle_state_key(mongo_collection_name, server_name)},
                {
                    "_id": {
                        "$regex": f"^lock::{re.escape(mongo_collection_name)}::{re.escape(server_name)}::"
                    }
                },
            ]
        }
    )
    file_meta_collection.update_many(
        {
            "type": "file_meta",
            "mongo_collection": mongo_collection_name,
            "server_name": server_name,
            "status": {"$in": list(PENDING_FILE_META_STATUSES)},
        },
        {
            "$set": {
                "status": "pending",
                "last_processed_line": 0,
                "records_upserted": 0,
                "parse_errors": 0,
                "invalid_prefix_lines": 0,
                "read_duration_seconds": 0.0,
                "write_duration_seconds": 0.0,
                "updated_at": now,
                "reset_at": now,
            }
        },
    )


def update_cycle_state(
    state_collection,
    mongo_collection_name: str,
    server_name: str,
    *,
    status: str,
    last_cycle_started_at: datetime,
    last_cycle_completed_at: datetime | None = None,
    files_seen: int | None = None,
    files_processed: int | None = None,
    files_completed: int | None = None,
) -> None:
    state_collection.update_one(
        {"_id": get_cycle_state_key(mongo_collection_name, server_name)},
        {
            "$set": {
                "type": "cycle_state",
                "mongo_collection": mongo_collection_name,
                "server_name": server_name,
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


def compute_file_hash(candidate: FileCandidate, logger: logging.Logger) -> FileCandidate:
    logger.info(
        "hashing file=%s server=%s size=%s bytes algorithm=%s",
        candidate.relative_path,
        candidate.server_name,
        candidate.file_size,
        FILE_HASH_ALGORITHM,
    )
    started_at = time.perf_counter()
    digest = hashlib.blake2b(digest_size=32)
    with candidate.full_path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    candidate.file_hash = digest.hexdigest()
    candidate.hash_duration_seconds = time.perf_counter() - started_at
    logger.info(
        "hashed file=%s server=%s hash=%s hash_time=%.3fs",
        candidate.relative_path,
        candidate.server_name,
        candidate.file_hash,
        candidate.hash_duration_seconds,
    )
    return candidate


def load_file_meta(
    file_meta_collection,
    mongo_collection_name: str,
    server_name: str,
    file_hash: str,
) -> dict[str, Any] | None:
    return file_meta_collection.find_one(
        {
            "_id": get_file_meta_key(mongo_collection_name, server_name, file_hash),
            "type": "file_meta",
        }
    )


def count_lines(file_path: Path) -> tuple[int, float]:
    started_at = time.perf_counter()
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        total_lines = sum(1 for _ in handle)
    return total_lines, time.perf_counter() - started_at


def discover_eligible_files(input_dir: Path, current_date: date, processed_dir: Path | None) -> list[FileCandidate]:
    candidates: list[FileCandidate] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if is_path_within(path, processed_dir):
            continue
        parsed_name = parse_candidate_file_name(path.name)
        if parsed_name is None:
            continue
        logical_file_name, file_date, is_gzip = parsed_name
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
                source_full_path=path,
                logical_file_name=logical_file_name,
                source_file_size=stat.st_size,
                is_gzip=is_gzip,
            )
        )
    candidates.sort(key=lambda item: (item.file_date, item.relative_path))
    return candidates


def prepare_candidate_for_processing(candidate: FileCandidate, logger: logging.Logger) -> FileCandidate:
    source_path = candidate.source_full_path or candidate.full_path
    if not candidate.is_gzip:
        logger.info(
            "using plain file server=%s file=%s source_path=%s",
            candidate.server_name,
            candidate.relative_path,
            source_path,
        )
        candidate.full_path = source_path
        return candidate

    temp_dir = Path(tempfile.gettempdir()) / SCRIPT_NAME / "gzip_extract" / str(uuid.uuid4())
    temp_dir.mkdir(parents=True, exist_ok=True)
    extracted_name = candidate.logical_file_name or source_path.name.removesuffix(".gz")
    extracted_path = temp_dir / extracted_name
    logger.info(
        "found gzip file server=%s file=%s source_path=%s",
        candidate.server_name,
        candidate.relative_path,
        source_path,
    )
    logger.info(
        "extracting gzip file server=%s file=%s extracted_path=%s",
        candidate.server_name,
        candidate.relative_path,
        extracted_path,
    )
    with gzip.open(source_path, "rb") as compressed_handle, extracted_path.open("wb") as extracted_handle:
        shutil.copyfileobj(compressed_handle, extracted_handle, length=FILE_HASH_CHUNK_SIZE)
    logger.info(
        "finished extracting gzip file server=%s file=%s extracted_path=%s",
        candidate.server_name,
        candidate.relative_path,
        extracted_path,
    )
    candidate.full_path = extracted_path
    candidate.extracted_temp_path = extracted_path
    return candidate


def cleanup_prepared_candidate(candidate: FileCandidate, logger: logging.Logger) -> None:
    temp_path = candidate.extracted_temp_path
    if temp_path is None or not temp_path.exists():
        return
    try:
        logger.info(
            "deleting temporary extracted file server=%s file=%s temp_path=%s",
            candidate.server_name,
            candidate.relative_path,
            temp_path,
        )
        temp_path.unlink()
        parent = temp_path.parent
        if parent.exists():
            parent.rmdir()
        logger.info(
            "deleted temporary extracted file server=%s file=%s temp_path=%s",
            candidate.server_name,
            candidate.relative_path,
            temp_path,
        )
    except OSError:
        logger.warning(
            "unable to fully clean temporary extracted file server=%s file=%s temp_path=%s",
            candidate.server_name,
            candidate.relative_path,
            temp_path,
        )


def build_processed_destination(candidate: FileCandidate, processed_dir: Path) -> Path:
    destination = processed_dir / candidate.relative_path
    if not destination.exists():
        return destination
    suffix = destination.suffix
    stem = destination.name[: -len(suffix)] if suffix else destination.name
    unique_name = f"{stem}.moved-{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    return destination.with_name(unique_name)


def move_candidate_to_processed_dir(candidate: FileCandidate, processed_dir: Path, logger: logging.Logger) -> Path:
    source_path = candidate.source_full_path or candidate.full_path
    destination = build_processed_destination(candidate, processed_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "moving processed source file server=%s file=%s from=%s to=%s",
        candidate.server_name,
        candidate.relative_path,
        source_path,
        destination,
    )
    shutil.move(str(source_path), str(destination))
    logger.info(
        "moved processed file server=%s from=%s to=%s",
        candidate.server_name,
        source_path,
        destination,
    )
    return destination


def should_process_file(candidate: FileCandidate, meta_doc: dict[str, Any] | None) -> tuple[bool, str]:
    if not meta_doc:
        return True, "new file"

    if meta_doc.get("status") == "completed":
        return False, "already processed (same file hash)"

    return True, "resume incomplete file"


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


def has_shifted_field_mapping(parsed_fields: dict[str, Any]) -> bool:
    return (
        parsed_fields.get("addr_dst_npi") in KNOWN_MESSAGE_DELIVERY_STATUSES
        and parsed_fields.get("message_delivery_status") in KNOWN_ORIGINATION_TYPES
        and parsed_fields.get("origination_type") in KNOWN_MESSAGE_TYPES
    )


def build_update_operation(
    candidate: FileCandidate,
    line_number: int,
    raw_line: str,
    payload: str,
    parsed_fields: dict[str, Any],
    raw_fields: list[str],
) -> UpdateOne:
    if not candidate.server_name or not candidate.file_hash:
        raise ValueError("server_name and file_hash must be populated before building update operations.")
    identity_key = build_identity_key(candidate.server_name, candidate.file_hash, line_number)
    document = {
        "identity_key": identity_key,
        "server_name": candidate.server_name,
        "file_hash": candidate.file_hash,
        "file_hash_algorithm": FILE_HASH_ALGORITHM,
        "source_path": candidate.relative_path,
        "source_file": candidate.logical_file_name or candidate.file_name,
        "source_original_file": candidate.file_name,
        "source_is_gzip": candidate.is_gzip,
        "source_full_path": str(candidate.source_full_path or candidate.full_path),
        "source_file_date": candidate.file_date.isoformat(),
        "source_file_size": candidate.source_file_size or candidate.file_size,
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
        {"identity_key": identity_key},
        {"$set": document},
        upsert=True,
    )

def save_file_meta(
    file_meta_collection,
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
    completed_at: datetime | None = None,
) -> None:
    if not candidate.server_name or not candidate.file_hash:
        raise ValueError("server_name and file_hash must be populated before saving file metadata.")
    now = datetime.now()
    file_meta_collection.update_one(
        {"_id": get_file_meta_key(mongo_collection_name, candidate.server_name, candidate.file_hash)},
        {
            "$set": {
                "type": "file_meta",
                "mongo_collection": mongo_collection_name,
                "server_name": candidate.server_name,
                "file_hash": candidate.file_hash,
                "file_hash_algorithm": FILE_HASH_ALGORITHM,
                "relative_path": candidate.relative_path,
                "file_name": candidate.file_name,
                "logical_file_name": candidate.logical_file_name or candidate.file_name,
                "source_full_path": str(candidate.source_full_path or candidate.full_path),
                "source_file_date": candidate.file_date.isoformat(),
                "file_date": candidate.file_date.isoformat(),
                "file_size": candidate.file_size,
                "source_file_size": candidate.source_file_size or candidate.file_size,
                "source_is_gzip": candidate.is_gzip,
                "last_modified_at": candidate.last_modified_at,
                "hash_duration_seconds": round(candidate.hash_duration_seconds or 0.0, 6),
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
                "process_completed_at": completed_at,
                "last_seen_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "first_seen_at": now,
                "source_full_path_first_seen": str(candidate.source_full_path or candidate.full_path),
            },
            "$addToSet": {
                "seen_paths": candidate.relative_path,
                "seen_full_paths": str(candidate.source_full_path or candidate.full_path),
            },
        },
        upsert=True,
    )


def flush_batch(
    *,
    data_collection,
    file_meta_collection,
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
    if not candidate.server_name or not candidate.file_hash:
        raise ValueError("server_name and file_hash must be populated before flushing batches.")
    refresh_file_lock(
        state_collection,
        mongo_collection_name,
        candidate.server_name,
        candidate.file_hash,
        owner_id,
        lock_timeout_seconds,
    )

    write_duration_seconds = 0.0
    batch_size = len(batch_operations)
    if batch_operations:
        mongo_write_started_at = time.perf_counter()
        data_collection.bulk_write(batch_operations, ordered=False)
        write_duration_seconds = time.perf_counter() - mongo_write_started_at
        accumulated_write_duration_seconds += write_duration_seconds
        records_upserted += batch_size

    save_file_meta(
        file_meta_collection=file_meta_collection,
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
    file_meta_collection,
    state_collection,
    mongo_collection_name: str,
    candidate: FileCandidate,
    meta_doc: dict[str, Any] | None,
    batch_size: int,
    owner_id: str,
    lock_timeout_seconds: int,
    logger: logging.Logger,
    error_file_path: Path | None,
    processed_dir: Path,
    file_position: int,
    total_files: int,
) -> dict[str, Any]:
    file_started_at = datetime.now()
    logger.info(
        "processing file %s/%s: %s (date=%s size=%s bytes gzip=%s)",
        file_position,
        total_files,
        candidate.relative_path,
        candidate.file_date.isoformat(),
        candidate.file_size,
        candidate.is_gzip,
    )

    total_lines, count_duration_seconds = count_lines(candidate.full_path)
    saved_line = 0
    if meta_doc and meta_doc.get("status") != "completed":
        saved_line = int(meta_doc.get("last_processed_line", 0))
    if saved_line > total_lines:
        saved_line = 0

    logger.info(
        "file=%s total_lines=%s count_time=%.3fs resume_line=%s",
        candidate.relative_path,
        total_lines,
        count_duration_seconds,
        saved_line,
    )

    records_upserted = int(meta_doc.get("records_upserted", 0)) if meta_doc else 0
    parse_errors = int(meta_doc.get("parse_errors", 0)) if meta_doc else 0
    invalid_prefix_lines = (
        int(meta_doc.get("invalid_prefix_lines", 0))
        if meta_doc
        else 0
    )
    batch_operations: list[UpdateOne] = []
    accumulated_read_duration_seconds = (
        float(meta_doc.get("read_duration_seconds", 0.0))
        if meta_doc
        else 0.0
    )
    accumulated_write_duration_seconds = (
        float(meta_doc.get("write_duration_seconds", 0.0))
        if meta_doc
        else 0.0
    )
    batch_read_started_at = time.perf_counter()
    last_processed_line = saved_line

    save_file_meta(
        file_meta_collection=file_meta_collection,
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

    error_context = (
        error_file_path.open("a", encoding="utf-8")
        if error_file_path is not None
        else nullcontext()
    )
    with error_context as error_handle, candidate.full_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if line_number <= saved_line:
                continue

            last_processed_line = line_number
            payload = extract_cdr_payload(raw_line)
            if payload is None:
                invalid_prefix_lines += 1
                if error_handle is not None:
                    error_handle.write(
                        f"{datetime.now().isoformat()}\tINVALID_PREFIX\tserver={candidate.server_name}\t"
                        f"file={candidate.file_name}\trelative_path={candidate.relative_path}\t"
                        f"line_number={line_number}\n"
                    )
                continue

            try:
                parsed_fields, raw_fields = parse_cdr_payload(payload)
            except Exception:
                parse_errors += 1
                if error_handle is not None:
                    error_handle.write(
                        f"{datetime.now().isoformat()}\tCSV_PARSE_ERROR\tserver={candidate.server_name}\t"
                        f"file={candidate.file_name}\trelative_path={candidate.relative_path}\t"
                        f"line_number={line_number}\n"
                    )
                continue

            if has_shifted_field_mapping(parsed_fields):
                parse_errors += 1
                logger.warning(
                    "file=%s line=%s detected shifted CDR mapping; skipping corrupt row raw_cdr=%s",
                    candidate.relative_path,
                    line_number,
                    payload,
                )
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
                    file_meta_collection=file_meta_collection,
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
            file_meta_collection=file_meta_collection,
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

    moved_to = move_candidate_to_processed_dir(candidate, processed_dir, logger)
    file_completed_at = datetime.now()
    save_file_meta(
        file_meta_collection=file_meta_collection,
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
        completed_at=file_completed_at,
    )

    file_total_duration_seconds = (file_completed_at - file_started_at).total_seconds()
    logger.info(
        "completed file=%s total_lines=%s upserts=%s parse_errors=%s invalid_prefix=%s count=%.3fs read=%.3fs mongo_write=%.3fs file_total=%.3fs moved_to=%s",
        candidate.relative_path,
        total_lines,
        records_upserted,
        parse_errors,
        invalid_prefix_lines,
        count_duration_seconds,
        accumulated_read_duration_seconds,
        accumulated_write_duration_seconds,
        file_total_duration_seconds,
        moved_to,
    )

    return {
        "relative_path": candidate.relative_path,
        "file_hash": candidate.file_hash,
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
    file_meta_collection,
    state_collection,
    mongo_collection_name: str,
    server_name: str,
    batch_size: int,
    owner_id: str,
    lock_timeout_seconds: int,
    logger: logging.Logger,
    error_file_path: Path | None,
    processed_dir: Path,
) -> dict[str, Any]:
    cycle_started_at = datetime.now()
    current_date = cycle_started_at.date()
    eligible_files = discover_eligible_files(input_dir, current_date, processed_dir)

    logger.info(
        "eligible_files=%s current_date=%s input_dir=%s processed_dir=%s file_pattern=%s",
        len(eligible_files),
        current_date.isoformat(),
        input_dir,
        processed_dir,
        FILE_NAME_PATTERN.pattern,
    )

    update_cycle_state(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        server_name=server_name,
        status="running",
        last_cycle_started_at=cycle_started_at,
        files_seen=len(eligible_files),
        files_processed=0,
        files_completed=0,
    )

    processed_files = 0
    pending_files = 0
    skipped_completed = 0
    summaries = []
    for index, candidate in enumerate(eligible_files, start=1):
        candidate.server_name = server_name
        try:
            prepare_candidate_for_processing(candidate, logger)
            compute_file_hash(candidate, logger)
            meta_doc = load_file_meta(
                file_meta_collection,
                mongo_collection_name,
                candidate.server_name,
                candidate.file_hash,
            )
            should_process, reason = should_process_file(candidate, meta_doc)
            if not should_process:
                skipped_completed += 1
                logger.warning(
                    "skipping file=%s server=%s hash=%s reason=%s previously_seen_paths=%s",
                    candidate.relative_path,
                    candidate.server_name,
                    candidate.file_hash,
                    reason,
                    meta_doc.get("seen_paths") if meta_doc else [],
                )
                save_file_meta(
                    file_meta_collection=file_meta_collection,
                    mongo_collection_name=mongo_collection_name,
                    candidate=candidate,
                    status=str(meta_doc.get("status", "completed")) if meta_doc else "completed",
                    last_processed_line=int(meta_doc.get("last_processed_line", 0)) if meta_doc else 0,
                    total_lines=int(meta_doc.get("total_lines", 0)) if meta_doc else 0,
                    records_upserted=int(meta_doc.get("records_upserted", 0)) if meta_doc else 0,
                    parse_errors=int(meta_doc.get("parse_errors", 0)) if meta_doc else 0,
                    invalid_prefix_lines=int(meta_doc.get("invalid_prefix_lines", 0)) if meta_doc else 0,
                    count_duration_seconds=float(meta_doc.get("count_duration_seconds", 0.0)) if meta_doc else 0.0,
                    read_duration_seconds=float(meta_doc.get("read_duration_seconds", 0.0)) if meta_doc else 0.0,
                    write_duration_seconds=float(meta_doc.get("write_duration_seconds", 0.0)) if meta_doc else 0.0,
                    started_at=meta_doc.get("started_at", cycle_started_at) if meta_doc else cycle_started_at,
                    completed_at=meta_doc.get("process_completed_at") if meta_doc else cycle_started_at,
                )
                move_candidate_to_processed_dir(candidate, processed_dir, logger)
                continue

            pending_files += 1
            logger.info("queue file=%s reason=%s", candidate.relative_path, reason)
            if not candidate.file_hash or not candidate.server_name:
                raise ValueError("candidate file hash and server name must be populated before processing.")
            acquire_file_lock(
                state_collection,
                mongo_collection_name,
                candidate.server_name,
                candidate.file_hash,
                owner_id,
                lock_timeout_seconds,
            )
            try:
                latest_meta_doc = load_file_meta(
                    file_meta_collection,
                    mongo_collection_name,
                    candidate.server_name,
                    candidate.file_hash,
                )
                should_process_latest, latest_reason = should_process_file(candidate, latest_meta_doc)
                if not should_process_latest:
                    skipped_completed += 1
                    logger.warning(
                        "skipping file=%s server=%s hash=%s after lock acquisition reason=%s",
                        candidate.relative_path,
                        candidate.server_name,
                        candidate.file_hash,
                        latest_reason,
                    )
                    move_candidate_to_processed_dir(candidate, processed_dir, logger)
                    continue
                summaries.append(
                    process_file(
                        data_collection=data_collection,
                        file_meta_collection=file_meta_collection,
                        state_collection=state_collection,
                        mongo_collection_name=mongo_collection_name,
                        candidate=candidate,
                        meta_doc=latest_meta_doc,
                        batch_size=batch_size,
                        owner_id=owner_id,
                        lock_timeout_seconds=lock_timeout_seconds,
                        logger=logger,
                        error_file_path=error_file_path,
                        processed_dir=processed_dir,
                        file_position=index,
                        total_files=len(eligible_files),
                    )
                )
                processed_files += 1
            finally:
                release_file_lock(
                    state_collection,
                    mongo_collection_name,
                    candidate.server_name,
                    candidate.file_hash,
                    owner_id,
                )
        finally:
            cleanup_prepared_candidate(candidate, logger)

    cycle_completed_at = datetime.now()
    update_cycle_state(
        state_collection=state_collection,
        mongo_collection_name=mongo_collection_name,
        server_name=server_name,
        status="completed",
        last_cycle_started_at=cycle_started_at,
        last_cycle_completed_at=cycle_completed_at,
        files_seen=len(eligible_files),
        files_processed=pending_files,
        files_completed=skipped_completed + processed_files,
    )

    logger.info(
        "cycle complete pending_files=%s processed_files=%s skipped_completed=%s cycle_total=%.3fs",
        pending_files,
        processed_files,
        skipped_completed,
        (cycle_completed_at - cycle_started_at).total_seconds(),
    )
    return {
        "eligible_files": len(eligible_files),
        "pending_files": pending_files,
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
    error_file_path = get_error_file_path(config)
    if error_file_path is not None:
        error_file_path.parent.mkdir(parents=True, exist_ok=True)

    input_dir = get_input_dir(config)
    processed_dir = get_processed_dir(config)
    server_name = get_server_name(config)
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Configured input directory does not exist or is not a directory: {input_dir}")
    processed_dir.mkdir(parents=True, exist_ok=True)

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
    file_meta_collection_name = get_cdr_file_meta_collection_name(
        config,
        get_config_value(
            config,
            "mongo",
            "file_meta_collection",
            "MONGO_FILE_META_COLLECTION",
            DEFAULT_FILE_META_COLLECTION,
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
        "starting %s server=%s input_dir=%s processed_dir=%s mongo_db=%s collection=%s state_collection=%s file_meta_collection=%s batch_size=%s continuous=%s schedule_time=%s",
        SCRIPT_NAME,
        server_name,
        input_dir,
        processed_dir,
        mongo_db_name,
        mongo_collection_name,
        state_collection_name,
        file_meta_collection_name,
        batch_size,
        continuous_mode,
        schedule_time.strftime("%H:%M"),
    )

    with get_mongo_client(config) as mongo_client:
        mongo_db = mongo_client[mongo_db_name]
        data_collection = ensure_collection(mongo_db, mongo_collection_name)
        state_collection = ensure_collection(mongo_db, state_collection_name)
        file_meta_collection = ensure_collection(mongo_db, file_meta_collection_name)
        ensure_indexes(data_collection, state_collection, file_meta_collection)

        if args.reset_state:
            reset_state(state_collection, file_meta_collection, mongo_collection_name, server_name)
            logger.info("reset resumable state for collection=%s server=%s", mongo_collection_name, server_name)

        if not continuous_mode:
            run_sync_cycle(
                input_dir=input_dir,
                data_collection=data_collection,
                file_meta_collection=file_meta_collection,
                state_collection=state_collection,
                mongo_collection_name=mongo_collection_name,
                server_name=server_name,
                batch_size=batch_size,
                owner_id=owner_id,
                lock_timeout_seconds=lock_timeout_seconds,
                logger=logger,
                error_file_path=error_file_path,
                processed_dir=processed_dir,
            )
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
            run_sync_cycle(
                input_dir=input_dir,
                data_collection=data_collection,
                file_meta_collection=file_meta_collection,
                state_collection=state_collection,
                mongo_collection_name=mongo_collection_name,
                server_name=server_name,
                batch_size=batch_size,
                owner_id=owner_id,
                lock_timeout_seconds=lock_timeout_seconds,
                logger=logger,
                error_file_path=error_file_path,
                processed_dir=processed_dir,
            )


if __name__ == "__main__":
    main()
