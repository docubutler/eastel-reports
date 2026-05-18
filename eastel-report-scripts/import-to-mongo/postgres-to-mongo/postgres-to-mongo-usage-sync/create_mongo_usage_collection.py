import argparse
import os
from pathlib import Path

import yaml
from pymongo import ASCENDING, MongoClient


DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "usage_logs"
DEFAULT_STATE_COLLECTION = "usage_log_sync_state"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create MongoDB collection and indexes for usage log reporting."
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
        help="MongoDB state collection name.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file used when env vars are not set.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def get_config_value(config: dict, section: str, key: str, env_name: str, default=None):
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    section_data = config.get(section, {})
    if isinstance(section_data, dict) and key in section_data and section_data[key] not in (None, ""):
        return section_data[key]
    return default


def get_mongo_client(config: dict) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI")
    return MongoClient(mongo_uri)


def get_usage_mongo_db_name(config: dict, default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_database")
        if value not in (None, ""):
            return str(value)
    return default


def get_usage_collection_name(config: dict, default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_usage_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_usage_state_collection_name(config: dict, default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_usage_state_collection")
        if value not in (None, ""):
            return str(value)
    return default


def ensure_collection(db, collection_name: str):
    if collection_name not in db.list_collection_names():
        db.create_collection(collection_name)
    return db[collection_name]


def drop_legacy_request_log_index_if_present(collection) -> list[str]:
    dropped_indexes = []
    for index in collection.list_indexes():
        name = index.get("name")
        key = index.get("key")
        if name == "uq_request_log_id" and list(key.items()) == [("request_log_id", 1)]:
            collection.drop_index(name)
            dropped_indexes.append(name)
    return dropped_indexes


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

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

    with get_mongo_client(config) as client:
        db = client[mongo_db_name]
        usage_collection = ensure_collection(db, mongo_collection_name)
        state_collection = ensure_collection(db, state_collection_name)
        dropped_indexes = drop_legacy_request_log_index_if_present(usage_collection)

        created_indexes = []
        created_indexes.append(
            usage_collection.create_index(
                [("usage_log_id", ASCENDING)],
                name="uq_usage_log_id",
                unique=True,
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("msisdn", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_msisdn_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("rat_type", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_rat_type_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [
                    ("rat_type", ASCENDING),
                    ("service_type_sub_cd", ASCENDING),
                    ("usage_start_time", ASCENDING),
                ],
                name="ix_rat_type_direction_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [
                    ("rat_type", ASCENDING),
                    ("roaming_destination_id", ASCENDING),
                    ("usage_start_time", ASCENDING),
                ],
                name="ix_rat_type_roaming_destination_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("opposite_number", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_opposite_number_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [
                    ("rat_type", ASCENDING),
                    ("rating_group", ASCENDING),
                    ("usage_start_time", ASCENDING),
                ],
                name="ix_rat_type_rating_group_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("roaming_mccmnc", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_roaming_mccmnc_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("customer_id", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_customer_id_usage_start_time",
            )
        )
        created_indexes.append(
            usage_collection.create_index(
                [("sim_id", ASCENDING), ("usage_start_time", ASCENDING)],
                name="ix_sim_id_usage_start_time",
            )
        )
        print("Mongo usage collection is ready.")
        if dropped_indexes:
            print("Dropped incompatible legacy indexes:")
            for index_name in dropped_indexes:
                print(f" - {index_name}")
        print("Indexes ensured:")
        for index_name in created_indexes:
            print(f" - {index_name}")


if __name__ == "__main__":
    main()
