import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pymongo import MongoClient, UpdateOne


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "smsc_cdrs"
DEFAULT_BATCH_SIZE = 1000
DELIVERY_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert string delivery_date values in SMSC CDR MongoDB documents to BSON Date."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file used when env vars are not set.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Bulk update batch size.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be updated without writing changes.",
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


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("migrate_smsc_cdr_delivery_date_to_bson")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def parse_delivery_date(value: str) -> datetime:
    for date_format in DELIVERY_DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(value)


def flush_updates(collection, operations: list[UpdateOne], dry_run: bool) -> int:
    if not operations:
        return 0
    if dry_run:
        return len(operations)
    result = collection.bulk_write(operations, ordered=False)
    return result.modified_count


def main() -> None:
    args = parse_args()
    logger = configure_logging()
    config = load_config(args.config)
    mongo_db_name = get_mongo_db_name(
        config,
        get_config_value(config, "mongo", "database", "MONGO_DB", DEFAULT_MONGO_DB),
    )
    mongo_collection_name = get_cdr_collection_name(
        config,
        get_config_value(config, "mongo", "collection", "MONGO_COLLECTION", DEFAULT_MONGO_COLLECTION),
    )

    scanned = 0
    convertible = 0
    converted = 0
    failed = 0
    operations: list[UpdateOne] = []

    with get_mongo_client(config) as client:
        collection = client[mongo_db_name][mongo_collection_name]
        cursor = collection.find(
            {"delivery_date": {"$type": "string"}},
            {"delivery_date": 1, "source_file": 1, "line_number": 1},
            no_cursor_timeout=True,
        )
        try:
            for document in cursor:
                scanned += 1
                delivery_date = document.get("delivery_date")
                if not isinstance(delivery_date, str):
                    continue
                try:
                    parsed_date = parse_delivery_date(delivery_date)
                except ValueError:
                    failed += 1
                    logger.warning(
                        "unable to parse delivery_date _id=%s source_file=%s line_number=%s value=%s",
                        document.get("_id"),
                        document.get("source_file"),
                        document.get("line_number"),
                        delivery_date,
                    )
                    continue
                convertible += 1
                operations.append(
                    UpdateOne(
                        {"_id": document["_id"]},
                        {"$set": {"delivery_date": parsed_date}},
                    )
                )
                if len(operations) >= args.batch_size:
                    converted += flush_updates(collection, operations, args.dry_run)
                    logger.info(
                        "progress scanned=%s convertible=%s converted=%s failed=%s",
                        scanned,
                        convertible,
                        converted,
                        failed,
                    )
                    operations = []
            converted += flush_updates(collection, operations, args.dry_run)
        finally:
            cursor.close()

    logger.info(
        "done dry_run=%s scanned=%s convertible=%s converted=%s failed=%s",
        args.dry_run,
        scanned,
        convertible,
        converted,
        failed,
    )


if __name__ == "__main__":
    main()
