import argparse
import csv
import logging
import os
import time as timer
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from bson.decimal128 import Decimal128
from pymongo import MongoClient


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
LOGGER = logging.getLogger("mongo_one_day_cdr_details")


USAGE_CATEGORY_LABELS = {
    1: "Domestic Data 4G",
    2: "Domestic Data 5G",
    3: "Domestic MO SMS (Offnet / Onnet)",
    4: "Domestic MO Voice (Onnet)",
    5: "Domestic MO Voice (Offnet)",
    6: "Domestic IDD MO Voice",
    7: "Domestic IDD MO SMS",
    8: "Roaming Data 4G / 5G",
    9: "Roaming MT Voice (Camel/S8HR)",
    10: "Roaming MO Voice (Camel/S8HR)",
    11: "Roaming SMS MO (Camel/S8HR)",
    12: "Premium Special Number Voice",
}

SMSC_CATEGORY_LABELS = {
    13: "Non-Profit A2P",
    14: "Commercial A2P",
}

OUTPUT_HEADERS = [
    "S.No.",
    "Category No.",
    "Service Type",
    "Event/Call Start Date Time",
    "Call Duration (second) / Total Volume (UL +DL ) in bytes",
    "MSISDN A#",
    "MSISDN B#",
    "IMSI",
    "Source Collection",
    "Source Record ID",
    "Mongo Record ID",
]

SPECIAL_NUMBERS = [
    "600380008000",
    "60103",
    "60100",
    "6015454",
    "6015300",
    "6015353",
    "6015404",
    "6015444",
    "6015777",
]
SPECIAL_PREFIXES = ["^601300", "^601700", "^601800"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate non-summarized OneDay CDR Details CSV from MongoDB.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Override variables.start_date with YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Override variables.end_date with YYYY-MM-DD.",
    )
    parser.add_argument(
        "--msisdn-a",
        default="",
        help="Optional MSISDN A filter. When omitted, all MSISDNs in the date range are included.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
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
    if isinstance(section_data, dict) and section_data.get(key) not in (None, ""):
        return section_data[key]
    return default


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        mongo_config = config.get("mongo", {})
        if isinstance(mongo_config, dict):
            mongo_uri = mongo_config.get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI or mongo.uri")
    return MongoClient(str(mongo_uri))


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def get_report_config(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    report_config = config.get("report_generation", {})
    if not isinstance(report_config, dict):
        raise ValueError("Config key 'report_generation' must be a YAML object.")

    base_dir = config_path.resolve().parent
    return {
        "report_spec_csv": resolve_path(
            base_dir,
            str(report_config.get("report_spec_csv") or "3-OneDay-CDR-Details.csv"),
        ),
        "mapping_csv": resolve_path(
            base_dir,
            str(report_config.get("mapping_csv") or "3-OneDay-CDR-Details-Mapping.csv"),
        ),
        "output_csv": resolve_path(
            base_dir,
            str(report_config.get("output_csv") or "3-OneDay-CDR-Details-output.csv"),
        ),
        "exclude_zero_usage_rows": bool(report_config.get("exclude_zero_usage_rows", False)),
    }


def parse_iso_date_or_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("Date variable value cannot be empty.")

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed_datetime = datetime.fromisoformat(raw)
    except ValueError:
        parsed_date = date.fromisoformat(raw)
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)

    if parsed_datetime.tzinfo is None:
        return parsed_datetime.replace(tzinfo=timezone.utc)
    return parsed_datetime.astimezone(timezone.utc)


def build_runtime_variables(config: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    variables = config.get("variables", {})
    if variables is None:
        variables = {}
    if not isinstance(variables, dict):
        raise ValueError("Config key 'variables' must be a YAML object.")

    merged: dict[str, str] = {str(key): str(value) for key, value in variables.items()}

    if args.start_date:
        merged["start_date"] = args.start_date.strip()
    if args.end_date:
        merged["end_date"] = args.end_date.strip()
    if args.msisdn_a:
        merged["msisdn_a"] = args.msisdn_a.strip()

    if "start_date" not in merged or "end_date" not in merged:
        raise ValueError("Both start_date and end_date must be provided in config or CLI.")

    end_date_dt = parse_iso_date_or_datetime(merged["end_date"])
    merged["end_date_exclusive"] = (end_date_dt + timedelta(days=1)).isoformat()
    return merged


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, list):
        return [normalize_scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_scalar(inner) for key, inner in value.items()}
    return value


def format_output_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def special_number_condition(field_name: str) -> dict[str, Any]:
    return {
        "$or": [
            {"$in": [f"${field_name}", SPECIAL_NUMBERS]},
            {
                "$and": [
                    {
                        "$or": [
                            {
                                "$regexMatch": {
                                    "input": {"$ifNull": [f"${field_name}", ""]},
                                    "regex": prefix,
                                }
                            }
                            for prefix in SPECIAL_PREFIXES
                        ]
                    },
                    {
                        "$lt": [
                            {"$strLenCP": {"$ifNull": [f"${field_name}", ""]}},
                            12,
                        ]
                    },
                ]
            },
        ]
    }


def usage_category_branches() -> list[dict[str, Any]]:
    return [
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "4G"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {"$ne": ["$rating_group", "500003"]},
                ]
            },
            "then": 1,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "5G"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {"$ne": ["$rating_group", "500003"]},
                ]
            },
            "then": 2,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "SM"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                ]
            },
            "then": 3,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MO"]},
                    special_number_condition("opposite_number"),
                ]
            },
            "then": 12,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MO"]},
                    {"$eq": ["$rating_group", "ONNET"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {"$gt": [{"$strLenCP": {"$ifNull": ["$opposite_number", ""]}}, 10]},
                ]
            },
            "then": 4,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MO"]},
                    {"$eq": ["$rating_group", "OFFNET"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {"$gt": [{"$strLenCP": {"$ifNull": ["$opposite_number", ""]}}, 10]},
                    {
                        "$regexMatch": {
                            "input": {"$ifNull": ["$opposite_number", ""]},
                            "regex": "^60",
                        }
                    },
                ]
            },
            "then": 5,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MO"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {
                        "$not": [
                            {
                                "$regexMatch": {
                                    "input": {"$ifNull": ["$opposite_number", ""]},
                                    "regex": "^60",
                                }
                            }
                        ]
                    },
                ]
            },
            "then": 6,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "SM"]},
                    {"$eq": ["$roaming_destination_id", 87]},
                    {
                        "$not": [
                            {
                                "$regexMatch": {
                                    "input": {"$ifNull": ["$opposite_number", ""]},
                                    "regex": "^60",
                                }
                            }
                        ]
                    },
                ]
            },
            "then": 7,
        },
        {
            "case": {
                "$and": [
                    {"$in": ["$rat_type", ["4G", "5G"]]},
                    {"$ne": ["$roaming_destination_id", 87]},
                ]
            },
            "then": 8,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MT"]},
                    {"$ne": ["$roaming_destination_id", 87]},
                    # Removed after discussion:
                    # MT calls should be captured regardless of where the calling party originates.
                    # In MT CDRs, msisdn is the subscriber and opposite_number is the calling party
                    # dialing this subscriber.
                    # {
                    #     "$not": [
                    #         {
                    #             "$regexMatch": {
                    #                 "input": {"$ifNull": ["$opposite_number", ""]},
                    #                 "regex": "^60",
                    #             }
                    #         }
                    #     ]
                    # },
                ]
            },
            "then": 9,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "VO"]},
                    {"$eq": ["$service_type_sub_cd", "MO"]},
                    {"$ne": ["$roaming_destination_id", 87]},
                    {
                        "$not": [
                            {
                                "$regexMatch": {
                                    "input": {"$ifNull": ["$opposite_number", ""]},
                                    "regex": "^60",
                                }
                            }
                        ]
                    },
                ]
            },
            "then": 10,
        },
        {
            "case": {
                "$and": [
                    {"$eq": ["$rat_type", "SM"]},
                    {"$ne": ["$roaming_destination_id", 87]},
                ]
            },
            "then": 11,
        },
    ]


def build_usage_pipeline(
    start_dt: datetime,
    end_exclusive_dt: datetime,
    msisdn_a: str | None,
    exclude_zero_usage_rows: bool,
) -> list[dict[str, Any]]:
    match_stage: dict[str, Any] = {
        "usage_start_time": {
            "$gte": start_dt,
            "$lt": end_exclusive_dt,
        },
        "rat_type": {"$in": ["VO", "SM", "4G", "5G"]},
    }
    if msisdn_a:
        match_stage["msisdn"] = msisdn_a
    if exclude_zero_usage_rows:
        # Optional performance and output filter:
        # when enabled, exclude usage_log rows with zero duration/volume
        # directly in Mongo so they are never transferred to Python.
        match_stage["act_usage_unit"] = {"$gt": 0}

    return [
        {"$match": match_stage},
        {
            "$addFields": {
                "cdr_category_no": {
                    "$switch": {
                        "branches": usage_category_branches(),
                        "default": None,
                    }
                }
            }
        },
        {"$match": {"cdr_category_no": {"$ne": None}}},
        {
            "$project": {
                "_id": 0,
                "category_no": "$cdr_category_no",
                "event_time": "$usage_start_time",
                "usage_value": "$act_usage_unit",
                "msisdn_a": "$msisdn",
                "msisdn_b": "$opposite_number",
                "imsi": "$imsi",
                "source_collection": {"$literal": "usage_logs"},
                "source_record_id": "$usage_log_id",
                "mongo_record_id": {"$toString": "$_id"},
            }
        },
        {"$sort": {"category_no": 1, "event_time": 1, "mongo_record_id": 1}},
    ]


def build_smsc_pipeline(start_dt: datetime, end_exclusive_dt: datetime, msisdn_a: str | None) -> list[dict[str, Any]]:
    match_stage: dict[str, Any] = {
        "delivery_date": {
            "$gte": start_dt,
            "$lt": end_exclusive_dt,
        },
        "origination_type": "SMPP",
        "message_delivery_status": "success",
    }
    if msisdn_a:
        match_stage["addr_dst_digits"] = msisdn_a

    return [
        {"$match": match_stage},
        {
            "$addFields": {
                "cdr_category_no": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$or": [
                                        {
                                            "$regexMatch": {
                                                "input": {"$ifNull": ["$addr_src_digits", ""]},
                                                "regex": "^2",
                                            }
                                        },
                                        {"$eq": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": 13,
                            },
                            {
                                "case": {
                                    "$and": [
                                        {
                                            "$regexMatch": {
                                                "input": {"$ifNull": ["$addr_src_digits", ""]},
                                                "regex": "^6",
                                            }
                                        },
                                        {"$ne": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": 14,
                            },
                        ],
                        "default": None,
                    }
                }
            }
        },
        {"$match": {"cdr_category_no": {"$ne": None}}},
        {
            "$project": {
                "_id": 0,
                "category_no": "$cdr_category_no",
                "event_time": "$delivery_date",
                "usage_value": None,
                "msisdn_a": "$addr_dst_digits",
                "msisdn_b": "$addr_src_digits",
                "imsi": "$imsi",
                "source_collection": {"$literal": "smsc_cdrs"},
                "source_record_id": "$message_id",
                "mongo_record_id": {"$toString": "$_id"},
            }
        },
        {"$sort": {"category_no": 1, "event_time": 1, "mongo_record_id": 1}},
    ]


def get_label_for_row(row: dict[str, Any]) -> str:
    category_no = int(row["category_no"])
    if category_no in USAGE_CATEGORY_LABELS:
        return USAGE_CATEGORY_LABELS[category_no]
    return SMSC_CATEGORY_LABELS[category_no]


def write_rows_to_csv(
    output_csv: Path,
    usage_cursor: Any,
    smsc_cursor: Any,
) -> tuple[int, dict[str, int]]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    serial_number = 1
    category_counts: dict[str, int] = {}

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()

        for cursor in (usage_cursor, smsc_cursor):
            for raw_row in cursor:
                row = normalize_scalar(raw_row)
                service_type = get_label_for_row(row)
                writer.writerow(
                    {
                        "S.No.": serial_number,
                        "Category No.": row["category_no"],
                        "Service Type": service_type,
                        "Event/Call Start Date Time": format_output_value(row.get("event_time")),
                        "Call Duration (second) / Total Volume (UL +DL ) in bytes": format_output_value(row.get("usage_value")),
                        "MSISDN A#": format_output_value(row.get("msisdn_a")),
                        "MSISDN B#": format_output_value(row.get("msisdn_b")),
                        "IMSI": format_output_value(row.get("imsi")),
                        "Source Collection": format_output_value(row.get("source_collection")),
                        "Source Record ID": format_output_value(row.get("source_record_id")),
                        "Mongo Record ID": format_output_value(row.get("mongo_record_id")),
                    }
                )
                category_counts[service_type] = category_counts.get(service_type, 0) + 1
                serial_number += 1

    return serial_number - 1, category_counts


def main() -> None:
    configure_logging()
    args = parse_args()
    overall_started_at = timer.perf_counter()
    config_path = Path(args.config).resolve()
    config = load_config(str(config_path))
    report_config = get_report_config(config, config_path)
    variables = build_runtime_variables(config, args)

    start_dt = parse_iso_date_or_datetime(variables["start_date"])
    end_exclusive_dt = parse_iso_date_or_datetime(variables["end_date_exclusive"])
    msisdn_a = variables.get("msisdn_a") or None

    mongo_database = get_config_value(config, "mongo", "database", "MONGO_DB", None)
    if not mongo_database:
        raise ValueError("Missing MongoDB database name: MONGO_DB or mongo.database")

    usage_collection_name = str(config.get("collections", {}).get("usage_log") or "usage_logs")
    smsc_collection_name = str(config.get("collections", {}).get("smsc_cdr") or "smsc_cdrs")
    output_csv = report_config["output_csv"]

    LOGGER.info("Report generation started")
    LOGGER.info("Config path: %s", config_path)
    LOGGER.info("Report spec CSV: %s", report_config["report_spec_csv"])
    LOGGER.info("Mapping CSV: %s", report_config["mapping_csv"])
    LOGGER.info("Output CSV: %s", output_csv)
    LOGGER.info("Mongo database: %s", mongo_database)
    LOGGER.info("Usage collection: %s", usage_collection_name)
    LOGGER.info("SMSC collection: %s", smsc_collection_name)
    LOGGER.info("Exclude zero usage rows: %s", report_config["exclude_zero_usage_rows"])
    LOGGER.info(
        "Report date window | start_date=%s | end_date=%s (inclusive) | end_date_exclusive=%s | msisdn_a=%s",
        variables["start_date"],
        variables["end_date"],
        variables["end_date_exclusive"],
        msisdn_a or "(all)",
    )

    usage_pipeline = build_usage_pipeline(
        start_dt,
        end_exclusive_dt,
        msisdn_a,
        report_config["exclude_zero_usage_rows"],
    )
    smsc_pipeline = build_smsc_pipeline(start_dt, end_exclusive_dt, msisdn_a)

    with get_mongo_client(config) as mongo_client:
        mongo_db = mongo_client[str(mongo_database)]

        usage_aggregate_options: dict[str, Any] = {"allowDiskUse": True}
        smsc_aggregate_options: dict[str, Any] = {"allowDiskUse": True}
        if msisdn_a:
            usage_aggregate_options["hint"] = "ix_msisdn_usage_start_time"
            smsc_aggregate_options["hint"] = "ix_addr_dst_digits_delivery_date"

        usage_cursor = mongo_db[usage_collection_name].aggregate(usage_pipeline, **usage_aggregate_options)
        smsc_cursor = mongo_db[smsc_collection_name].aggregate(smsc_pipeline, **smsc_aggregate_options)

        total_rows, category_counts = write_rows_to_csv(
            output_csv,
            usage_cursor,
            smsc_cursor,
        )

    total_duration_seconds = timer.perf_counter() - overall_started_at
    LOGGER.info("CSV output written: %s", output_csv)
    LOGGER.info("Total output rows: %s", total_rows)
    for category_name, count in sorted(category_counts.items(), key=lambda item: item[0]):
        LOGGER.info("Category summary | service_type=%s | rows=%s", category_name, count)
    LOGGER.info("Report generation finished | total_duration=%.3fs", total_duration_seconds)
    print(f"Generated report CSV: {output_csv}")


if __name__ == "__main__":
    main()
