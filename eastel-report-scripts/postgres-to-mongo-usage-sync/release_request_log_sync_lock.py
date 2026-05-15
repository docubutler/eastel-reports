import os
from pathlib import Path
from typing import Any

import yaml
from pymongo import MongoClient


DEFAULT_SOURCE_TABLE = "iot_portal_tb_request_log"
DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "request_logs"
DEFAULT_STATE_COLLECTION = "request_log_sync_state"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


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


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI")
    return MongoClient(mongo_uri)


def get_request_log_source_table(config: dict[str, Any], default: str) -> str:
    sync_config = config.get("sync", {})
    if isinstance(sync_config, dict):
        value = sync_config.get("postgres_request_source_table")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_mongo_db_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_database")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_request_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_state_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_request_state_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_state_key(source_table: str, mongo_collection: str) -> str:
    return f"{source_table}->{mongo_collection}"


def get_lock_key(source_table: str, mongo_collection: str) -> str:
    return f"lock::{get_state_key(source_table, mongo_collection)}"


def main() -> None:
    config = load_config(str(DEFAULT_CONFIG_PATH))

    mongo_db_name = get_config_value(
        config,
        "mongo",
        "database",
        "MONGO_DB",
        DEFAULT_MONGO_DB,
    )
    mongo_db_name = get_request_log_mongo_db_name(config, str(mongo_db_name))
    mongo_collection_name = get_config_value(
        config,
        "mongo",
        "collection",
        "MONGO_COLLECTION",
        DEFAULT_MONGO_COLLECTION,
    )
    mongo_collection_name = get_request_log_collection_name(config, str(mongo_collection_name))
    state_collection_name = get_config_value(
        config,
        "mongo",
        "state_collection",
        "MONGO_STATE_COLLECTION",
        DEFAULT_STATE_COLLECTION,
    )
    state_collection_name = get_request_log_state_collection_name(config, str(state_collection_name))
    source_table = get_config_value(
        config,
        "sync",
        "source_table",
        "PG_SOURCE_TABLE",
        DEFAULT_SOURCE_TABLE,
    )
    source_table = get_request_log_source_table(config, str(source_table))

    lock_key = get_lock_key(source_table, mongo_collection_name)

    with get_mongo_client(config) as mongo_client:
        state_collection = mongo_client[mongo_db_name][state_collection_name]
        existing_lock = state_collection.find_one({"_id": lock_key})
        if not existing_lock:
            print(f"No request-log sync lock found for {lock_key}")
            return

        result = state_collection.delete_one({"_id": lock_key})
        if result.deleted_count == 1:
            print(f"Released request-log sync lock: {lock_key}")
        else:
            print(f"Lock was found but could not be deleted: {lock_key}")


if __name__ == "__main__":
    main()
