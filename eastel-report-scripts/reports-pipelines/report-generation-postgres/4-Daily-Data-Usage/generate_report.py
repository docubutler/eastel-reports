"""Generate the day-wise 4G / 5G domestic data usage report (CSV) from read-only PostgreSQL.

Output columns: Date, 4G Usage (MBYTE), 5G Usage (MBYTE), Total Usage
"""
import argparse
import csv
import logging
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import yaml


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
LOG = logging.getLogger("daily_data_usage")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--start-date", default="", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--usage-table", default="", help="Override tables.usage_log_table.")
    parser.add_argument("--output", default="", help="Output path, relative to the config directory.")
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


def positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def quote_identifier(value: str) -> str:
    """Validate a config identifier, then quote each part; values remain parameters."""
    parts = value.strip().split(".")
    if len(parts) not in (1, 2) or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
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


def build_query(table: str) -> str:
    query = (BASE_DIR / "queries" / "daily-data-usage.sql").read_text(encoding="utf-8")
    return query.replace("{{usage_log_table}}", quote_identifier(table))


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
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def write_csv(output: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    """Replace the output only after the query completes successfully."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output.parent,
            prefix=".daily-data-usage-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: format_output_value(row.get(key)) for key in headers})
        temporary.replace(output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    report_generation = section(config, "report_generation")
    variables = section(config, "variables")

    start_date = (args.start_date or variables.get("start_date") or "").strip()
    end_date = (args.end_date or variables.get("end_date") or "").strip()
    window_start, window_end = date_window(start_date, end_date)

    table = (args.usage_table or section(config, "tables").get("usage_log_table") or "").strip()
    if not table:
        raise ValueError("Set tables.usage_log_table or pass --usage-table.")

    output = Path(args.output or report_generation.get("output_csv") or "4-Daily-Data-Usage.csv")
    if not output.is_absolute():
        output = config_path.parent / output

    query = build_query(table)
    parameters = {"start_date": window_start, "end_date_exclusive": window_end}
    LOG.info("Usage table: %s", table)
    LOG.info("Report window: %s <= usage_start_time < %s", window_start, window_end)
    LOG.info("Output CSV: %s", output)

    if args.dry_run:
        print(query)
        print(f"-- parameters: {parameters}")
        return

    statement_timeout_ms = positive_integer(
        report_generation.get("statement_timeout_ms", 600000), "report_generation.statement_timeout_ms"
    )
    connection = connect_postgres(config)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SET statement_timeout = %s", (statement_timeout_ms,))
            cursor.execute(query, parameters)
            headers = [column.name for column in cursor.description]
            rows = cursor.fetchall()
    finally:
        connection.rollback()
        connection.close()

    write_csv(output, headers, rows)
    LOG.info("Wrote %s data rows with columns: %s", len(rows), ", ".join(headers))


if __name__ == "__main__":
    main()
