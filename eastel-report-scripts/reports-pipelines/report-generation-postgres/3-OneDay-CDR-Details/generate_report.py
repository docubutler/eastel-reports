"""Export usage CDRs from read-only PostgreSQL and SMSC A2P details from MongoDB."""
import argparse
import csv
import json
import logging
import os
import re
import tempfile
import time as timer
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import yaml
from bson.decimal128 import Decimal128
from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
LOGGER = logging.getLogger("postgres_one_day_cdr_details")
CATEGORY_LABELS = {
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
    13: "Non-Profit A2P",
    14: "Commercial A2P",
}
OUTPUT_HEADERS = [
    "S.No.", "Category No.", "Service Type", "Event/Call Start Date Time",
    "Call Duration (second) / Total Volume (UL +DL ) in bytes",
    "MSISDN A#", "MSISDN B#", "IMSI", "Source Database", "Source Table / Collection",
    "Source Record ID", "Postgres Record ID", "Mongo Record ID",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--start-date", default="", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--msisdn-a", default=None, help="Subscriber filter; empty string includes all.")
    parser.add_argument("--usage-table", default="", help="Override tables.usage_log_table.")
    parser.add_argument("--smsc-collection", default="", help="Override collections.smsc_cdr.")
    parser.add_argument("--output", default="", help="Output path, relative to config directory.")
    smsc = parser.add_mutually_exclusive_group()
    smsc.add_argument("--include-smsc", dest="include_smsc", action="store_true")
    smsc.add_argument("--skip-smsc", dest="include_smsc", action="store_false")
    parser.set_defaults(include_smsc=None)
    parser.add_argument("--dry-run", action="store_true", help="Print SQL and parameters without connecting.")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}. Copy config-sample.yml to config.yml first.")
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("Config must contain a YAML mapping.")
    return config


def section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping.")
    return value


def boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be YAML true or false.")
    return value


def positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def quote_identifier(value: str, qualified: bool = True) -> str:
    """Validate config identifiers, then quote each part; values remain parameters."""
    parts = value.strip().split(".")
    if len(parts) not in ((1, 2) if qualified else (1,)) or not all(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts
    ):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return ".".join(f'"{part}"' for part in parts)


def date_window(start: str, end: str) -> tuple[datetime, datetime]:
    """Preserve the source's naive timestamp convention; do not shift timezones."""
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise ValueError("start_date and end_date must be YYYY-MM-DD dates.") from exc
    if last < first:
        raise ValueError("end_date must be on or after start_date.")
    return datetime.combine(first, time.min), datetime.combine(last + timedelta(days=1), time.min)


def build_usage_query(table: str, filter_msisdn: bool, exclude_zero: bool) -> str:
    query = (BASE_DIR / "queries" / "usage-details.sql").read_text(encoding="utf-8")
    return query.replace("{{usage_log_table}}", quote_identifier(table)).replace(
        "{{msisdn_filter}}", "AND msisdn = %(msisdn_a)s" if filter_msisdn else ""
    ).replace("{{volume_filter}}", "AND act_usage_unit > 0" if exclude_zero else "")


def build_smsc_pipeline(start: datetime, end: datetime, msisdn: str) -> list[dict[str, Any]]:
    # Same BSON-Date boundaries and category precedence as the Mongo extractor.
    match = {
        "delivery_date": {"$gte": start.replace(tzinfo=timezone.utc), "$lt": end.replace(tzinfo=timezone.utc)},
        "origination_type": "SMPP", "message_delivery_status": "success",
    }
    if msisdn:
        match["addr_dst_digits"] = msisdn
    sender = {"$ifNull": ["$addr_src_digits", ""]}
    return [
        {"$match": match},
        {"$addFields": {"cdr_category_no": {"$switch": {
            "branches": [
                {"case": {"$or": [
                    {"$regexMatch": {"input": sender, "regex": "^2"}},
                    {"$eq": ["$addr_src_digits", "601170337777"]},
                ]}, "then": 13},
                {"case": {"$and": [
                    {"$regexMatch": {"input": sender, "regex": "^6"}},
                    {"$ne": ["$addr_src_digits", "601170337777"]},
                ]}, "then": 14},
            ], "default": None,
        }}}},
        {"$match": {"cdr_category_no": {"$ne": None}}},
        {"$project": {
            "_id": 0, "category_no": "$cdr_category_no", "event_time": "$delivery_date",
            "usage_value": {"$literal": None}, "msisdn_a": "$addr_dst_digits",
            "msisdn_b": "$addr_src_digits", "imsi": "$imsi",
            "source_database": {"$literal": "MongoDB"},
            "source_record_id": "$message_id", "mongo_record_id": {"$toString": "$_id"},
        }},
        {"$sort": {"category_no": 1, "event_time": 1, "mongo_record_id": 1}},
    ]


def connect_mongo(config: dict[str, Any]) -> Any:
    mongo = section(config, "mongo")
    uri = os.getenv("MONGO_URI") or mongo.get("uri")
    if not uri:
        raise ValueError("SMSC enabled: set MONGO_URI or mongo.uri, or use --skip-smsc.")
    return MongoClient(str(uri), serverSelectionTimeoutMS=15000)


def connect_postgres(config: dict[str, Any]) -> Any:
    pg = section(config, "postgres")
    timeout = positive_integer(pg.get("connect_timeout", 15), "postgres.connect_timeout")
    dsn = os.getenv("POSTGRES_DSN") or pg.get("dsn")
    if dsn:
        return psycopg2.connect(str(dsn), connect_timeout=timeout)
    arguments = {"connect_timeout": timeout}
    for key, environment, default in [
        ("host", "PGHOST", "localhost"), ("port", "PGPORT", 5432),
        ("dbname", "PGDATABASE", ""), ("user", "PGUSER", ""),
        ("password", "PGPASSWORD", ""), ("sslmode", "PGSSLMODE", ""),
    ]:
        value = os.getenv(environment) or pg.get("database" if key == "dbname" else key, default)
        if value not in (None, ""):
            arguments[key] = value
    if "dbname" not in arguments:
        raise ValueError("Set PGDATABASE or postgres.database, or provide POSTGRES_DSN.")
    return psycopg2.connect(**arguments)


def format_output_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def write_rows_to_csv(output: Path, sources: list[tuple[Any, str]]) -> tuple[int, dict[str, int]]:
    """Replace output only after every cursor finishes successfully."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    count, categories = 0, {}
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output.parent,
            prefix=".cdr-details-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
            writer.writeheader()
            for cursor, table in sources:
                for row in cursor:
                    label = CATEGORY_LABELS[int(row["category_no"])]
                    count += 1
                    writer.writerow({
                        "S.No.": count, "Category No.": row["category_no"], "Service Type": label,
                        "Event/Call Start Date Time": format_output_value(row.get("event_time")),
                        "Call Duration (second) / Total Volume (UL +DL ) in bytes": format_output_value(row.get("usage_value")),
                        "MSISDN A#": format_output_value(row.get("msisdn_a")),
                        "MSISDN B#": format_output_value(row.get("msisdn_b")),
                        "IMSI": format_output_value(row.get("imsi")),
                        "Source Database": row.get("source_database", "PostgreSQL"),
                        "Source Table / Collection": table,
                        "Source Record ID": format_output_value(row.get("source_record_id")),
                        "Postgres Record ID": format_output_value(row.get("postgres_record_id")),
                        "Mongo Record ID": format_output_value(row.get("mongo_record_id")),
                    })
                    categories[label] = categories.get(label, 0) + 1
                    if count % 100000 == 0:
                        LOGGER.info("Exported %s rows", count)
        temporary.replace(output)
        return count, categories
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    args = parse_args()
    started = timer.perf_counter()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    report, variables, tables = (section(config, name) for name in ("report_generation", "variables", "tables"))
    start, end = date_window(
        str(args.start_date or variables.get("start_date", "")),
        str(args.end_date or variables.get("end_date", "")),
    )
    msisdn = args.msisdn_a if args.msisdn_a is not None else str(variables.get("msisdn_a") or "")
    msisdn = msisdn.strip()
    exclude_zero = boolean(report.get("exclude_zero_usage_rows", False), "exclude_zero_usage_rows")
    include_smsc = args.include_smsc if args.include_smsc is not None else boolean(
        report.get("include_smsc", True), "include_smsc"
    )
    batch = positive_integer(report.get("fetch_batch_size", 10000), "fetch_batch_size")
    timeout = positive_integer(report.get("statement_timeout_ms", 600000), "statement_timeout_ms")
    usage_table = str(args.usage_table or tables.get("usage_log_table") or "public.iot_portal_tb_usage_log")
    source_queries = [("cdr_usage_details", usage_table, build_usage_query(usage_table, bool(msisdn), exclude_zero))]
    smsc_collection = str(args.smsc_collection or section(config, "collections").get("smsc_cdr") or "smsc_cdrs")
    smsc_pipeline = build_smsc_pipeline(start, end, msisdn) if include_smsc else None
    mongo_database = os.getenv("MONGO_DB") or section(config, "mongo").get("database") or "eastel-data"
    parameters = {"start_date": start, "end_date_exclusive": end, "msisdn_a": msisdn}
    output = Path(args.output or report.get("output_csv") or "3-OneDay-CDR-Details-output.csv")
    if not output.is_absolute():
        output = config_path.parent / output
    if args.dry_run:
        print("Parameters:", json.dumps(parameters, default=str))
        for _, table, query in source_queries:
            print(f"\n-- Source: {table}\n{query}")
        if include_smsc:
            print(f"\nMongo source: {mongo_database}.{smsc_collection}")
            print(json.dumps(smsc_pipeline, default=str, indent=2))
        return
    LOGGER.info("Date window: %s inclusive to %s exclusive; MSISDN: %s", start, end, msisdn or "(all)")
    LOGGER.info("Usage table: %s; exclude non-positive usage: %s", usage_table, exclude_zero)
    if not include_smsc:
        LOGGER.info("SMSC disabled: categories 13 and 14 will not be exported.")
    connection = connect_postgres(config)
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
        with connection:
            with connection.cursor() as control:
                control.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout),))
            with ExitStack() as stack:
                sources = []
                for name, table, query in source_queries:
                    cursor = stack.enter_context(connection.cursor(name=name, cursor_factory=RealDictCursor))
                    cursor.itersize = batch
                    cursor.execute(query, parameters)
                    sources.append((cursor, table))
                if include_smsc:
                    mongo = stack.enter_context(connect_mongo(config))
                    smsc_cursor = mongo[str(mongo_database)][smsc_collection].aggregate(
                        smsc_pipeline, allowDiskUse=True, maxTimeMS=timeout, batchSize=batch,
                    )
                    stack.callback(smsc_cursor.close)
                    sources.append((smsc_cursor, smsc_collection))
                    LOGGER.info("SMSC Mongo source: %s.%s", mongo_database, smsc_collection)
                total, counts = write_rows_to_csv(output, sources)
    finally:
        connection.close()
    LOGGER.info("Total rows: %s; elapsed: %.3fs", total, timer.perf_counter() - started)
    for category, count in sorted(counts.items()):
        LOGGER.info("Category: %s; rows: %s", category, count)
    print(f"Generated report CSV: {output}")


if __name__ == "__main__":
    main()
