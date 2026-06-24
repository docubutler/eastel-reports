import argparse
import os
from pathlib import Path

import yaml
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, MongoClient


DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "usage_logs"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
INDEX_NAME = "ix_usage_start_time_msisdn_active_units"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the partial MongoDB index used by the active subscriber report query."
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
    return MongoClient(str(mongo_uri))


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

    with get_mongo_client(config) as client:
        collection = client[mongo_db_name][mongo_collection_name]
        index_name = collection.create_index(
            [("usage_start_time", ASCENDING), ("msisdn", ASCENDING)],
            name=INDEX_NAME,
            partialFilterExpression={"act_usage_unit": {"$gt": Decimal128("0")}},
        )
        print(f"Created or verified index: {index_name}")
        print(f"Database: {mongo_db_name}")
        print(f"Collection: {mongo_collection_name}")


if __name__ == "__main__":
    main()
