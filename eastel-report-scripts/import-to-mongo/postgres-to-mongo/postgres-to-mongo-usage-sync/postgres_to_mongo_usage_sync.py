import argparse
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml
from bson.decimal128 import Decimal128
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import MongoClient, ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError


DEFAULT_SOURCE_TABLE = "iot_portal_tb_usage_log_rep"
DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "usage_logs"
DEFAULT_STATE_COLLECTION = "usage_log_sync_state"
DEFAULT_BATCH_SIZE = 1000
DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
DEFAULT_LOCK_TIMEOUT_SECONDS = 3600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally sync usage logs from PostgreSQL to MongoDB."
    )
    parser.add_argument(
        "--source-table",
        default=os.getenv("PG_SOURCE_TABLE", DEFAULT_SOURCE_TABLE),
        help="PostgreSQL source table name.",
    )
    parser.add_argument(
        "--mongo-db",
        default=os.getenv("MONGO_DB", DEFAULT_MONGO_DB),
        help="MongoDB database name.",
    )
    parser.add_argument(
        "--mongo-collection",
        default=os.getenv("MONGO_COLLECTION", DEFAULT_MONGO_COLLECTION),
        help="MongoDB collection name.",
    )
    parser.add_argument(
        "--state-collection",
        default=os.getenv("MONGO_STATE_COLLECTION", DEFAULT_STATE_COLLECTION),
        help="MongoDB collection used to store sync checkpoints.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("SYNC_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        help="Number of source rows fetched per batch.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=int(os.getenv("SYNC_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)),
        help="Sleep interval between sync cycles when --continuous is used.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Keep polling PostgreSQL instead of running once.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run once and exit, even if config enables continuous mode.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Reset the stored checkpoint before syncing. Existing documents remain safe because writes are upserts.",
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


def get_config_value(config: dict[str, Any], section: str, key: str, env_name: str, default: Any = None) -> Any:
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    section_data = config.get(section, {})
    if isinstance(section_data, dict) and key in section_data and section_data[key] not in (None, ""):
        return section_data[key]
    return default


def get_postgres_dsn(config: dict[str, Any]) -> str:
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn
    dsn = config.get("postgres", {}).get("dsn")
    if dsn:
        return str(dsn)

    host = get_config_value(config, "postgres", "host", "PGHOST", "localhost")
    port = get_config_value(config, "postgres", "port", "PGPORT", "5432")
    dbname = get_config_value(config, "postgres", "database", "PGDATABASE")
    user = get_config_value(config, "postgres", "user", "PGUSER")
    password = get_config_value(config, "postgres", "password", "PGPASSWORD")
    sslmode = get_config_value(config, "postgres", "sslmode", "PGSSLMODE")

    missing = [name for name, value in {
        "PGDATABASE": dbname,
        "PGUSER": user,
        "PGPASSWORD": password,
    }.items() if not value]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"Missing PostgreSQL settings: {missing_text}")

    parts = [
        f"host={host}",
        f"port={port}",
        f"dbname={dbname}",
        f"user={user}",
        f"password={password}",
    ]
    if sslmode:
        parts.append(f"sslmode={sslmode}")
    return " ".join(parts)


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI")
    return MongoClient(mongo_uri)


def get_usage_source_table(config: dict[str, Any], default: str) -> str:
    sync_config = config.get("sync", {})
    if isinstance(sync_config, dict):
        value = sync_config.get("postgres_usage_source_table")
        if value not in (None, ""):
            return str(value)
    return default


def get_usage_mongo_db_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_database")
        if value not in (None, ""):
            return str(value)
    return default


def get_usage_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_usage_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_usage_state_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_usage_state_collection")
        if value not in (None, ""):
            return str(value)
    return default


def classify_service(row: dict[str, Any]) -> str:
    rat_type = row.get("rat_type")
    direction = row.get("service_type_sub_cd")
    rating_group = row.get("rating_group")

    if rat_type == "VO" or direction in {"MO", "MT"}:
        return "VOICE"
    if rat_type == "SM" or rating_group == "SM":
        return "SMS"
    if rat_type in {"4G", "5G"}:
        return "DATA"
    return "UNKNOWN"


def classify_roaming_status(roaming_destination_id: Any) -> str | None:
    if roaming_destination_id is None:
        return None
    return "NON_ROAMING" if roaming_destination_id == 87 else "ROAMING"


def classify_number_type(opposite_number: Any) -> str | None:
    if not opposite_number:
        return None
    text = str(opposite_number)
    return "MY" if text.startswith("60") else "NON_MY"


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return Decimal128(str(value))
    return value


def transform_row(row: dict[str, Any], source_table: str) -> dict[str, Any]:
    doc = {key: normalize_value(value) for key, value in row.items()}

    doc["derived"] = {
        "service_type": classify_service(row),
        "roaming_status": classify_roaming_status(row.get("roaming_destination_id")),
        "opposite_number_type": classify_number_type(row.get("opposite_number")),
        "is_billable": bool((row.get("act_usage_unit") or 0) > 0),
        "rat_family": row.get("rat_type"),
    }
    doc["sync_metadata"] = {
        "source_table": source_table,
        "synced_at": datetime.now(timezone.utc),
    }
    return doc


def get_state_key(source_table: str, mongo_collection: str) -> str:
    return f"{source_table}->{mongo_collection}"


def get_lock_key(source_table: str, mongo_collection: str) -> str:
    return f"lock::{get_state_key(source_table, mongo_collection)}"


def get_last_synced_id(state_collection, source_table: str, mongo_collection: str) -> int:
    state_key = get_state_key(source_table, mongo_collection)
    state = state_collection.find_one({"_id": state_key}, {"last_usage_log_id": 1})
    if not state:
        return 0
    return int(state.get("last_usage_log_id", 0))


def reset_state(state_collection, source_table: str, mongo_collection: str) -> None:
    state_key = get_state_key(source_table, mongo_collection)
    state_collection.delete_one({"_id": state_key})


def save_last_synced_id(
    state_collection,
    source_table: str,
    mongo_collection: str,
    last_usage_log_id: int,
) -> None:
    state_key = get_state_key(source_table, mongo_collection)
    state_collection.update_one(
        {"_id": state_key},
        {
            "$set": {
                "source_table": source_table,
                "mongo_collection": mongo_collection,
                "last_usage_log_id": last_usage_log_id,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def acquire_lock(
    state_collection,
    source_table: str,
    mongo_collection: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_lock_key(source_table, mongo_collection)
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + lock_timeout_seconds, tz=timezone.utc)
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
                    "owner_id": owner_id,
                    "source_table": source_table,
                    "mongo_collection": mongo_collection,
                    "updated_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise RuntimeError(
            "Another sync instance is already running for the same source table and Mongo collection."
        ) from exc

    if not lock_doc or lock_doc.get("owner_id") != owner_id:
        raise RuntimeError(
            "Another sync instance is already running for the same source table and Mongo collection."
        )


def refresh_lock(
    state_collection,
    source_table: str,
    mongo_collection: str,
    owner_id: str,
    lock_timeout_seconds: int,
) -> None:
    lock_key = get_lock_key(source_table, mongo_collection)
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + lock_timeout_seconds, tz=timezone.utc)
    result = state_collection.update_one(
        {"_id": lock_key, "owner_id": owner_id},
        {"$set": {"updated_at": now, "expires_at": expires_at}},
    )
    if result.matched_count != 1:
        raise RuntimeError("Sync instance lock was lost during execution.")


def release_lock(
    state_collection,
    source_table: str,
    mongo_collection: str,
    owner_id: str,
) -> None:
    lock_key = get_lock_key(source_table, mongo_collection)
    state_collection.delete_one({"_id": lock_key, "owner_id": owner_id})


def validate_usage_collection_indexes(mongo_collection) -> None:
    has_usage_unique_index = False

    for index in mongo_collection.list_indexes():
        name = index.get("name")
        key = index.get("key")
        key_items = list(key.items())

        if name == "uq_request_log_id" and key_items == [("request_log_id", 1)]:
            raise RuntimeError(
                "Mongo collection has incompatible unique index 'uq_request_log_id' on "
                "'request_log_id'. This usage sync writes documents keyed by 'usage_log_id'. "
                "Run create_mongo_usage_collection.py to drop the stale request-log index "
                "and ensure 'uq_usage_log_id'."
            )

        if name == "uq_usage_log_id" and key_items == [("usage_log_id", 1)] and index.get("unique"):
            has_usage_unique_index = True

    if not has_usage_unique_index:
        raise RuntimeError(
            "Mongo collection is missing the required unique index 'uq_usage_log_id' on "
            "'usage_log_id'. Run create_mongo_usage_collection.py before starting usage sync."
        )


def fetch_rows(pg_conn, source_table: str, last_usage_log_id: int, batch_size: int) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT *
        FROM {source_table}
        WHERE usage_log_id > %s
        ORDER BY usage_log_id ASC
        LIMIT %s
        """
    ).format(source_table=sql.Identifier(source_table))
    with pg_conn.cursor() as cursor:
        cursor.execute(query, (last_usage_log_id, batch_size))
        return cursor.fetchall()


def sync_once(
    pg_conn,
    mongo_collection,
    state_collection,
    source_table: str,
    mongo_collection_name: str,
    batch_size: int,
) -> int:
    total_processed = 0

    while True:
        batch_started_at = time.perf_counter()
        last_usage_log_id = get_last_synced_id(
            state_collection=state_collection,
            source_table=source_table,
            mongo_collection=mongo_collection_name,
        )
        fetch_started_at = time.perf_counter()
        rows = fetch_rows(pg_conn, source_table, last_usage_log_id, batch_size)
        fetch_duration_seconds = time.perf_counter() - fetch_started_at
        if not rows:
            break

        operations = []
        max_usage_log_id = last_usage_log_id
        transform_started_at = time.perf_counter()
        for row in rows:
            usage_log_id = int(row["usage_log_id"])
            max_usage_log_id = max(max_usage_log_id, usage_log_id)
            operations.append(
                UpdateOne(
                    {"usage_log_id": usage_log_id},
                    {"$set": transform_row(row, source_table)},
                    upsert=True,
                )
            )
        transform_duration_seconds = time.perf_counter() - transform_started_at

        mongo_write_started_at = time.perf_counter()
        mongo_collection.bulk_write(operations, ordered=False)
        mongo_write_duration_seconds = time.perf_counter() - mongo_write_started_at
        checkpoint_started_at = time.perf_counter()
        save_last_synced_id(
            state_collection=state_collection,
            source_table=source_table,
            mongo_collection=mongo_collection_name,
            last_usage_log_id=max_usage_log_id,
        )
        checkpoint_duration_seconds = time.perf_counter() - checkpoint_started_at

        total_processed += len(rows)
        batch_duration_seconds = time.perf_counter() - batch_started_at
        rows_per_second = len(rows) / batch_duration_seconds if batch_duration_seconds > 0 else 0.0
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"synced {len(rows)} rows, checkpoint={max_usage_log_id}, "
            f"fetch={fetch_duration_seconds:.3f}s, "
            f"transform={transform_duration_seconds:.3f}s, "
            f"mongo_write={mongo_write_duration_seconds:.3f}s, "
            f"checkpoint_save={checkpoint_duration_seconds:.3f}s, "
            f"batch_total={batch_duration_seconds:.3f}s, "
            f"rate={rows_per_second:.2f} rows/s"
        )

        if len(rows) < batch_size:
            break

    return total_processed


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    postgres_dsn = get_postgres_dsn(config)

    mongo_db_name = get_config_value(
        config,
        "mongo",
        "database",
        "MONGO_DB",
        args.mongo_db,
    )
    mongo_db_name = get_usage_mongo_db_name(config, str(mongo_db_name))
    mongo_collection_name = get_config_value(
        config,
        "mongo",
        "collection",
        "MONGO_COLLECTION",
        args.mongo_collection,
    )
    mongo_collection_name = get_usage_collection_name(config, str(mongo_collection_name))
    state_collection_name = get_config_value(
        config,
        "mongo",
        "state_collection",
        "MONGO_STATE_COLLECTION",
        args.state_collection,
    )
    state_collection_name = get_usage_state_collection_name(config, str(state_collection_name))
    source_table = get_config_value(
        config,
        "sync",
        "source_table",
        "PG_SOURCE_TABLE",
        args.source_table,
    )
    source_table = get_usage_source_table(config, str(source_table))
    batch_size = int(
        get_config_value(
            config,
            "sync",
            "batch_size",
            "SYNC_BATCH_SIZE",
            args.batch_size,
        )
    )
    poll_interval_seconds = int(
        get_config_value(
            config,
            "sync",
            "poll_interval_seconds",
            "SYNC_POLL_INTERVAL_SECONDS",
            args.poll_interval_seconds,
        )
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
    continuous_mode = False if args.run_once else (
        args.continuous
        or str(
            get_config_value(
                config,
                "sync",
                "continuous",
                "SYNC_CONTINUOUS",
                False,
            )
        ).strip().lower() in {"1", "true", "yes", "on"}
    )
    owner_id = str(uuid.uuid4())

    with psycopg.connect(postgres_dsn, row_factory=dict_row) as pg_conn:
        with get_mongo_client(config) as mongo_client:
            mongo_db = mongo_client[mongo_db_name]
            mongo_collection = mongo_db[mongo_collection_name]
            state_collection = mongo_db[state_collection_name]
            validate_usage_collection_indexes(mongo_collection)

            if args.reset_state:
                reset_state(state_collection, source_table, mongo_collection_name)
                print("Reset stored sync checkpoint.")

            acquire_lock(
                state_collection=state_collection,
                source_table=source_table,
                mongo_collection=mongo_collection_name,
                owner_id=owner_id,
                lock_timeout_seconds=lock_timeout_seconds,
            )
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"acquired sync lock for {source_table}->{mongo_collection_name}"
            )

            try:
                while True:
                    refresh_lock(
                        state_collection=state_collection,
                        source_table=source_table,
                        mongo_collection=mongo_collection_name,
                        owner_id=owner_id,
                        lock_timeout_seconds=lock_timeout_seconds,
                    )
                    processed = sync_once(
                        pg_conn=pg_conn,
                        mongo_collection=mongo_collection,
                        state_collection=state_collection,
                        source_table=source_table,
                        mongo_collection_name=mongo_collection_name,
                        batch_size=batch_size,
                    )

                    if processed == 0:
                        print(
                            f"[{datetime.now().isoformat(timespec='seconds')}] "
                            "no new rows found"
                        )

                    if not continuous_mode:
                        break

                    time.sleep(poll_interval_seconds)
            finally:
                release_lock(
                    state_collection=state_collection,
                    source_table=source_table,
                    mongo_collection=mongo_collection_name,
                    owner_id=owner_id,
                )
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"released sync lock for {source_table}->{mongo_collection_name}"
                )


if __name__ == "__main__":
    main()
