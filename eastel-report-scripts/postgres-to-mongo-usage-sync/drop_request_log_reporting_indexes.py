import os
from pathlib import Path
from typing import Any

import yaml
from pymongo import MongoClient


DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "request_logs"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")

REPORTING_INDEX_NAMES = [
    "ix_account_id_req_time",
    "ix_customer_id_req_time",
    "ix_sim_id_req_time",
    "ix_iccid_req_time",
    "ix_req_type_req_time",
    "ix_service_type_id_req_time",
    "ix_session_id",
    "ix_req_time",
]


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

    with get_mongo_client(config) as client:
        collection = client[mongo_db_name][mongo_collection_name]
        existing_index_names = {index_info["name"] for index_info in collection.list_indexes()}

        print(f"Target collection: {mongo_db_name}.{mongo_collection_name}")
        print("Keeping unique indexes:")
        print(" - uq_request_log_id")
        print(" - uq_session_request_rating_group")

        dropped = []
        missing = []
        for index_name in REPORTING_INDEX_NAMES:
            if index_name not in existing_index_names:
                missing.append(index_name)
                continue
            collection.drop_index(index_name)
            dropped.append(index_name)

        print("Dropped reporting indexes:")
        if dropped:
            for index_name in dropped:
                print(f" - {index_name}")
        else:
            print(" - none")

        print("Indexes already absent:")
        if missing:
            for index_name in missing:
                print(f" - {index_name}")
        else:
            print(" - none")


if __name__ == "__main__":
    main()
