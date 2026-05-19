import argparse
import csv
import logging
import os
import re
import time as timer
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg.rows import dict_row


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
PLACEHOLDER_PATTERN = re.compile(r"%(\d+)\.([A-Za-z0-9_]+)%")
VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")
QUERY_TITLE_PATTERN = re.compile(r"^--\s*Query\s+\d+\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
LOGGER = logging.getLogger("postgres_report_generation")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute split SQL queries and populate a report CSV from the template.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file.",
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


def get_report_config(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    report_config = config.get("report_generation", {})
    if not isinstance(report_config, dict):
        raise ValueError("Config key 'report_generation' must be a YAML object.")

    base_dir = config_path.resolve().parent
    query_column_name = str(report_config.get("query_column_name") or "Query")

    return {
        "split_queries_dir": resolve_path(
            base_dir,
            str(report_config.get("split_queries_dir") or "generated-queries"),
        ),
        "template_csv": resolve_path(
            base_dir,
            str(report_config.get("template_csv") or "report-template.csv"),
        ),
        "output_csv": resolve_path(
            base_dir,
            str(report_config.get("output_csv") or "report-output.csv"),
        ),
        "query_column_name": query_column_name,
        "default_table": str(report_config.get("default_table") or ""),
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
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"Unsupported ISO date/datetime value: {value}") from exc
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)

    if parsed_datetime.tzinfo is None:
        return parsed_datetime.replace(tzinfo=timezone.utc)
    return parsed_datetime.astimezone(timezone.utc)


def build_runtime_variables(config: dict[str, Any], report_config: dict[str, Any]) -> dict[str, str]:
    variables = config.get("variables", {})
    if variables is None:
        variables = {}
    if not isinstance(variables, dict):
        raise ValueError("Config key 'variables' must be a YAML object.")

    tables = config.get("tables", {})
    if tables is None:
        tables = {}
    if not isinstance(tables, dict):
        raise ValueError("Config key 'tables' must be a YAML object.")

    merged: dict[str, str] = {}
    for source in (tables, variables):
        for key, value in source.items():
            merged[str(key)] = str(value)

    default_table = report_config.get("default_table")
    if default_table:
        merged.setdefault("default_table", str(default_table))

    end_date_value = merged.get("end_date")
    if end_date_value and "end_date_exclusive" not in merged:
        end_date_dt = parse_iso_date_or_datetime(end_date_value)
        merged["end_date_exclusive"] = (end_date_dt + timedelta(days=1)).date().isoformat()

    return merged


def render_sql_template(sql_text: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        if variable_name not in variables:
            raise ValueError(f"Missing SQL variable '{variable_name}' in config.yml.")
        return variables[variable_name]

    return VARIABLE_PATTERN.sub(replace, sql_text)


def aggregate_values(values: list[Any]) -> Any:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return ""

    if all(isinstance(value, (int, float, Decimal)) for value in present_values):
        total = sum(present_values)
        if isinstance(total, Decimal):
            return total.normalize()
        return total

    text_values = [str(value) for value in present_values]
    unique_values: list[str] = []
    for value in text_values:
        if value not in unique_values:
            unique_values.append(value)
    if len(unique_values) == 1:
        return unique_values[0]
    return "; ".join(unique_values)


def aggregate_query_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}

    first_row = rows[0]
    aggregated: dict[str, Any] = {}
    for key in first_row.keys():
        aggregated[key] = aggregate_values([row.get(key) for row in rows])
    return aggregated


def normalize_result_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in row.items()}


def format_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def extract_referenced_query_ids(template_csv: Path) -> list[str]:
    referenced_query_ids: list[str] = []

    with template_csv.open("r", encoding="utf-8-sig", newline="") as source_handle:
        reader = csv.DictReader(source_handle)
        if reader.fieldnames is None:
            raise ValueError(f"Template CSV is missing a header row: {template_csv}")

        for row in reader:
            for cell_value in row.values():
                if cell_value is None:
                    continue
                for match in PLACEHOLDER_PATTERN.finditer(cell_value):
                    query_id = match.group(1)
                    if query_id not in referenced_query_ids:
                        referenced_query_ids.append(query_id)

    return referenced_query_ids


def extract_query_title(sql_text: str, query_id: str) -> str:
    match = QUERY_TITLE_PATTERN.search(sql_text)
    if match:
        return match.group(1).strip()
    return f"Query {query_id}"


def execute_queries(
    conn: psycopg.Connection[Any],
    queries_dir: Path,
    variables: dict[str, str],
    selected_query_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    if not queries_dir.exists():
        raise FileNotFoundError(f"Split queries directory not found: {queries_dir}")

    query_results: dict[str, dict[str, Any]] = {}
    rendered_queries: dict[str, str] = {}
    query_timings: list[dict[str, Any]] = []

    sql_files = sorted(
        queries_dir.glob("*.sql"),
        key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem,
    )
    if not sql_files:
        raise ValueError(f"No .sql files found in: {queries_dir}")

    sql_files_to_run = [sql_file for sql_file in sql_files if sql_file.stem in selected_query_ids]
    if not sql_files_to_run:
        LOGGER.info("No referenced queries found in template CSV. Skipping query execution.")
        return query_results, rendered_queries, query_timings

    missing_query_ids = [query_id for query_id in selected_query_ids if query_id not in {path.stem for path in sql_files}]
    if missing_query_ids:
        raise ValueError(
            f"Referenced query ids are missing from {queries_dir}: {', '.join(sorted(missing_query_ids, key=lambda value: int(value) if value.isdigit() else value))}"
        )

    LOGGER.info("Starting query execution. referenced_queries=%s", len(sql_files_to_run))

    with conn.cursor(row_factory=dict_row) as cursor:
        for current_index, sql_file in enumerate(sql_files_to_run, start=1):
            query_started_at = timer.perf_counter()
            query_id = sql_file.stem
            sql_template = sql_file.read_text(encoding="utf-8")
            rendered_sql = render_sql_template(sql_template, variables)
            query_title = extract_query_title(sql_template, query_id)
            LOGGER.info(
                "Executing query %s/%s | id=%s | title=%s",
                current_index,
                len(sql_files_to_run),
                query_id,
                query_title,
            )
            cursor.execute(rendered_sql)
            rows = list(cursor.fetchall())
            aggregated = aggregate_query_rows(rows)
            query_results[query_id] = normalize_result_row(aggregated)
            rendered_queries[query_id] = rendered_sql.strip()
            duration_seconds = timer.perf_counter() - query_started_at
            query_timings.append(
                {
                    "query_id": query_id,
                    "title": query_title,
                    "row_count": len(rows),
                    "duration_seconds": duration_seconds,
                }
            )
            LOGGER.info(
                "Completed query id=%s | title=%s | rows=%s | duration=%.3fs",
                query_id,
                query_title,
                len(rows),
                duration_seconds,
            )

    return query_results, rendered_queries, query_timings


def populate_template(
    template_csv: Path,
    output_csv: Path,
    query_column_name: str,
    query_results: dict[str, dict[str, Any]],
    rendered_queries: dict[str, str],
) -> None:
    with template_csv.open("r", encoding="utf-8-sig", newline="") as source_handle:
        reader = csv.DictReader(source_handle)
        if reader.fieldnames is None:
            raise ValueError(f"Template CSV is missing a header row: {template_csv}")

        fieldnames = list(reader.fieldnames)
        if query_column_name not in fieldnames:
            fieldnames.append(query_column_name)

        rows: list[dict[str, str]] = []
        for row in reader:
            updated_row = {key: row.get(key, "") for key in fieldnames}
            referenced_query_ids: list[str] = []

            for column_name, original_value in row.items():
                if original_value is None:
                    updated_row[column_name] = ""
                    continue

                def replace_placeholder(match: re.Match[str]) -> str:
                    query_id = match.group(1)
                    column_key = match.group(2).lower()
                    if query_id not in referenced_query_ids:
                        referenced_query_ids.append(query_id)
                    result_row = query_results.get(query_id, {})
                    return format_cell_value(result_row.get(column_key, ""))

                updated_row[column_name] = PLACEHOLDER_PATTERN.sub(replace_placeholder, original_value)

            executed_queries = [rendered_queries[query_id] for query_id in referenced_query_ids if query_id in rendered_queries]
            updated_row[query_column_name] = "\n\n".join(executed_queries)
            rows.append(updated_row)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as target_handle:
        writer = csv.DictWriter(target_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    configure_logging()
    args = parse_args()
    script_started_at = datetime.now(timezone.utc)
    overall_started_at = timer.perf_counter()
    config_path = Path(args.config).resolve()
    config = load_config(str(config_path))
    report_config = get_report_config(config, config_path)
    variables = build_runtime_variables(config, report_config)
    postgres_dsn = get_postgres_dsn(config)

    template_csv = report_config["template_csv"]
    output_csv = report_config["output_csv"]
    split_queries_dir = report_config["split_queries_dir"]
    query_column_name = report_config["query_column_name"]

    if not template_csv.exists():
        raise FileNotFoundError(f"Template CSV not found: {template_csv}")

    referenced_query_ids = extract_referenced_query_ids(template_csv)
    LOGGER.info("Report generation started")
    LOGGER.info("Config path: %s", config_path)
    LOGGER.info("Template CSV: %s", template_csv)
    LOGGER.info("Output CSV: %s", output_csv)
    LOGGER.info("Split queries dir: %s", split_queries_dir)
    LOGGER.info(
        "Referenced query ids from CSV: %s",
        ", ".join(referenced_query_ids) if referenced_query_ids else "(none)",
    )
    LOGGER.info(
        "Report date window | start_date=%s | end_date=%s (inclusive) | end_date_exclusive=%s",
        variables.get("start_date", ""),
        variables.get("end_date", ""),
        variables.get("end_date_exclusive", ""),
    )

    with psycopg.connect(postgres_dsn) as conn:
        query_results, rendered_queries, query_timings = execute_queries(
            conn,
            split_queries_dir,
            variables,
            set(referenced_query_ids),
        )

    populate_template(
        template_csv=template_csv,
        output_csv=output_csv,
        query_column_name=query_column_name,
        query_results=query_results,
        rendered_queries=rendered_queries,
    )

    total_duration_seconds = timer.perf_counter() - overall_started_at
    script_finished_at = datetime.now(timezone.utc)
    LOGGER.info("CSV output written: %s", output_csv)
    for timing in query_timings:
        LOGGER.info(
            "Query summary | id=%s | title=%s | rows=%s | duration=%.3fs",
            timing["query_id"],
            timing["title"],
            timing["row_count"],
            timing["duration_seconds"],
        )
    LOGGER.info("Report generation finished")
    LOGGER.info("Script start time (UTC): %s", script_started_at.isoformat())
    LOGGER.info("Script end time (UTC): %s", script_finished_at.isoformat())
    LOGGER.info("Total duration: %.3fs", total_duration_seconds)

    print(f"Generated report CSV: {output_csv}")


if __name__ == "__main__":
    main()
