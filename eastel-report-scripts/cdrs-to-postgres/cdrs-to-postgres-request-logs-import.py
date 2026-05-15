import argparse
import csv
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg import sql


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")

REQUEST_LOG_COLUMNS = [
    "request_log_id",
    "currency_id",
    "service_type_id",
    "service_provider_id",
    "rate_plan_id",
    "account_id",
    "sim_id",
    "sim_service_plan_id",
    "customer_id",
    "user_id",
    "cr_user",
    "cr_time",
    "up_user",
    "up_time",
    "record_status",
    "display_order",
    "req_type",
    "req_time",
    "session_id",
    "session_req_num",
    "iccid",
    "msisdn",
    "imei",
    "imsi",
    "roaming_mccmnc",
    "rat_type",
    "init_granted_volume",
    "update_used_volume",
    "total_used_volume",
    "exchange_rate",
    "cost_currency_cd",
    "cost_exchange_rate",
    "price_currency_cd",
    "price_exchange_rate",
    "cost_init_granted_money",
    "cost_update_used_money",
    "cost_total_used_money",
    "price_init_granted_money",
    "price_update_used_money",
    "price_total_used_money",
    "validity_time",
    "rating_group",
    "user_location_info",
    "apn",
    "service_context",
    "charging_characteristic",
    "sgsn_address",
    "notes",
    "addon_imsi",
    "addon_msisdn",
    "service_type_sub_cd",
    "opposite_number",
    "roaming_destination_id",
    "act_update_used_volume",
    "act_total_used_volume",
    "act_price_update_used_money",
    "act_price_total_used_money",
    "act_cost_update_used_money",
    "act_cost_total_used_money",
    "additional_sim_id",
    "additional_roaming_destination_id",
    "operation_status",
]

INTEGER_COLUMNS = {
    "request_log_id",
    "currency_id",
    "service_type_id",
    "service_provider_id",
    "rate_plan_id",
    "account_id",
    "sim_id",
    "sim_service_plan_id",
    "customer_id",
    "user_id",
    "cr_user",
    "up_user",
    "record_status",
    "display_order",
    "session_req_num",
    "validity_time",
    "roaming_destination_id",
    "additional_sim_id",
    "additional_roaming_destination_id",
}

DECIMAL_COLUMNS = {
    "init_granted_volume",
    "update_used_volume",
    "total_used_volume",
    "exchange_rate",
    "cost_exchange_rate",
    "price_exchange_rate",
    "cost_init_granted_money",
    "cost_update_used_money",
    "cost_total_used_money",
    "price_init_granted_money",
    "price_update_used_money",
    "price_total_used_money",
    "act_update_used_volume",
    "act_total_used_volume",
    "act_price_update_used_money",
    "act_price_total_used_money",
    "act_cost_update_used_money",
    "act_cost_total_used_money",
}

TIMESTAMP_COLUMNS = {"cr_time", "up_time", "req_time"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import request log CDRs from CSV into PostgreSQL."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        help="Override CSV path from config.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate the target table before loading.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
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


def get_postgres_dsn(config: dict[str, Any]) -> str:
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn

    postgres_config = config.get("postgres", {})
    if isinstance(postgres_config, dict):
        dsn = postgres_config.get("dsn")
        if dsn:
            return str(dsn)

    host = get_config_value(config, "postgres", "host", "PGHOST", "localhost")
    port = get_config_value(config, "postgres", "port", "PGPORT", "5432")
    dbname = get_config_value(config, "postgres", "database", "PGDATABASE")
    user = get_config_value(config, "postgres", "user", "PGUSER")
    password = get_config_value(config, "postgres", "password", "PGPASSWORD")
    sslmode = get_config_value(config, "postgres", "sslmode", "PGSSLMODE")

    missing = [
        name
        for name, value in {
            "PGDATABASE": dbname,
            "PGUSER": user,
            "PGPASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing PostgreSQL settings: {', '.join(missing)}")

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


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def qualified_identifier(name: str) -> sql.Composed:
    parts = [part.strip() for part in name.split(".") if part.strip()]
    if not parts:
        raise ValueError("Identifier cannot be empty.")
    return sql.SQL(".").join(sql.Identifier(part) for part in parts)


def get_import_config(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    import_config = config.get("import", {})
    if not isinstance(import_config, dict):
        raise ValueError("Config key 'import' must be a YAML object.")

    base_dir = Path(args.config).resolve().parent

    csv_value = args.csv_path or import_config.get("csv_path")
    if not csv_value:
        raise ValueError("Missing import.csv_path in config and no --csv override provided.")

    schema_value = import_config.get("schema_sql_path")
    if not schema_value:
        raise ValueError("Missing import.schema_sql_path in config.")

    table_name = str(import_config.get("table_name") or "iot_portal_tb_request_log").strip()
    sequence_name = str(import_config.get("sequence_name") or "iot_portal_seq_request_log").strip()
    batch_size = int(import_config.get("batch_size") or 1000)
    truncate_before_load = bool(import_config.get("truncate_before_load", False) or args.truncate)
    progress_every_rows = int(import_config.get("progress_every_rows") or 5000)
    commit_each_batch = bool(import_config.get("commit_each_batch", False))

    bad_rows_path_value = import_config.get("bad_rows_path") or "request-log-import-bad-rows.csv"

    return {
        "csv_path": resolve_path(base_dir, str(csv_value)),
        "schema_sql_path": resolve_path(base_dir, str(schema_value)),
        "table_name": table_name,
        "sequence_name": sequence_name,
        "batch_size": batch_size,
        "truncate_before_load": truncate_before_load,
        "progress_every_rows": progress_every_rows,
        "commit_each_batch": commit_each_batch,
        "bad_rows_path": resolve_path(base_dir, str(bad_rows_path_value)),
    }


def normalize_cell(column: str, value: str) -> Any:
    if value is None:
        return None
    text = value.strip()
    if text == "" or text.upper() == "NULL":
        return None

    if column in INTEGER_COLUMNS:
        return int(text)
    if column in DECIMAL_COLUMNS:
        return Decimal(text)
    if column in TIMESTAMP_COLUMNS:
        return datetime.fromisoformat(text)
    return text


def log_bad_row(path: Path, row_number: int, row_data: dict[str, Any], error_message: str) -> None:
    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["csv_row_number", "error_message", "row_data"])
        writer.writerow([row_number, error_message, repr(row_data)])


def execute_schema(cursor: psycopg.Cursor[Any], schema_sql_path: Path) -> None:
    schema_sql = schema_sql_path.read_text(encoding="utf-8")
    if not schema_sql.strip():
        raise ValueError(f"Schema SQL file is empty: {schema_sql_path}")
    cursor.execute(schema_sql)


def ensure_sequence(cursor: psycopg.Cursor[Any], sequence_name: str) -> None:
    cursor.execute(
        sql.SQL("CREATE SEQUENCE IF NOT EXISTS {}").format(qualified_identifier(sequence_name))
    )


def truncate_table(cursor: psycopg.Cursor[Any], table_name: str) -> None:
    cursor.execute(sql.SQL("TRUNCATE TABLE {}").format(qualified_identifier(table_name)))


def build_insert_statement(table_name: str) -> sql.Composed:
    return sql.SQL(
        "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
    ).format(
        qualified_identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in REQUEST_LOG_COLUMNS),
        sql.SQL(", ").join(sql.Placeholder() for _ in REQUEST_LOG_COLUMNS),
    )


def load_and_insert_rows(
    conn: psycopg.Connection[Any],
    cursor: psycopg.Cursor[Any],
    csv_path: Path,
    table_name: str,
    bad_rows_path: Path,
    batch_size: int,
    progress_every_rows: int,
    commit_each_batch: bool,
) -> tuple[int, int]:
    statement = build_insert_statement(table_name)
    parsed_rows = 0
    inserted_rows = 0
    batch: list[tuple[Any, ...]] = []

    def flush_batch() -> None:
        nonlocal inserted_rows, batch
        if not batch:
            return
        cursor.executemany(statement, batch)
        inserted_rows += max(cursor.rowcount, 0)
        batch = []
        if commit_each_batch:
            conn.commit()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUEST_LOG_COLUMNS:
            raise ValueError(
                "CSV header does not match request log table columns exactly.\n"
                f"Expected: {REQUEST_LOG_COLUMNS}\n"
                f"Actual:   {reader.fieldnames}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                normalized = tuple(
                    normalize_cell(column, row.get(column, "")) for column in REQUEST_LOG_COLUMNS
                )
            except Exception as exc:
                log_bad_row(bad_rows_path, row_number, row, str(exc))
                print(f"Skipping bad row {row_number}: {exc}")
                continue

            batch.append(normalized)
            parsed_rows += 1

            if len(batch) >= batch_size:
                flush_batch()

            if progress_every_rows > 0 and (
                parsed_rows % progress_every_rows == 0
            ):
                print(
                    f"Parsed {parsed_rows:,} rows; inserted/checked {parsed_rows:,} rows so far..."
                )

    flush_batch()
    return parsed_rows, inserted_rows


def count_rows(cursor: psycopg.Cursor[Any], table_name: str) -> int:
    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(qualified_identifier(table_name)))
    value = cursor.fetchone()
    return int(value[0]) if value else 0


def align_sequence(cursor: psycopg.Cursor[Any], table_name: str, sequence_name: str) -> None:
    cursor.execute(
        sql.SQL(
            """
            SELECT setval(
                %s::regclass,
                COALESCE((SELECT MAX(request_log_id) FROM {}), 0)::bigint,
                COALESCE((SELECT MAX(request_log_id) FROM {}), 0) > 0
            )
            """
        ).format(qualified_identifier(table_name), qualified_identifier(table_name)),
        (sequence_name,),
    )


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    postgres_dsn = get_postgres_dsn(config)
    import_config = get_import_config(config, args)

    csv_path = import_config["csv_path"]
    schema_sql_path = import_config["schema_sql_path"]
    table_name = import_config["table_name"]
    sequence_name = import_config["sequence_name"]
    batch_size = import_config["batch_size"]
    truncate_before_load = import_config["truncate_before_load"]
    progress_every_rows = import_config["progress_every_rows"]
    commit_each_batch = import_config["commit_each_batch"]
    bad_rows_path = import_config["bad_rows_path"]

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if not schema_sql_path.exists():
        raise FileNotFoundError(f"Schema SQL file not found: {schema_sql_path}")

    print(f"Using CSV: {csv_path}")
    print(f"Using schema SQL: {schema_sql_path}")
    print(f"Target table: {table_name}")

    with psycopg.connect(postgres_dsn) as conn:
        with conn.cursor() as cursor:
            ensure_sequence(cursor, sequence_name)
            execute_schema(cursor, schema_sql_path)
            before_count = 0 if truncate_before_load else count_rows(cursor, table_name)

            if truncate_before_load:
                print(f"Truncating table: {table_name}")
                truncate_table(cursor, table_name)

            if commit_each_batch:
                print("Batch commits enabled; rows will become visible during the run.")
            else:
                print("Single transaction mode; rows become visible after the final commit.")
            parsed_rows, inserted_rows = load_and_insert_rows(
                conn,
                cursor,
                csv_path,
                table_name,
                bad_rows_path,
                batch_size,
                progress_every_rows,
                commit_each_batch,
            )
            align_sequence(cursor, table_name, sequence_name)
            after_count = count_rows(cursor, table_name)

        conn.commit()

    inserted = after_count if truncate_before_load else max(after_count - before_count, 0)
    duplicates = parsed_rows - inserted
    print(f"Valid CSV rows processed: {parsed_rows}")
    print(f"Rows accepted by PostgreSQL during insert: {inserted_rows}")
    print(f"Inserted rows: {inserted}")
    print(f"Skipped rows due to conflicts: {duplicates}")
    print("Import completed.")


if __name__ == "__main__":
    main()
