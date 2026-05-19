import argparse
import csv
import json
import logging
import os
import re
import time as timer
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from bson.decimal128 import Decimal128
from pymongo import MongoClient


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
PLACEHOLDER_PATTERN = re.compile(r"%(\d+)\.([A-Za-z0-9_]+)%")
VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")
LOGGER = logging.getLogger("mongo_rating_group_report")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute Mongo query files and write a CSV report.",
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
    output_columns = report_config.get("output_columns") or []
    if not isinstance(output_columns, list):
        raise ValueError("Config key 'report_generation.output_columns' must be a YAML list.")

    return {
        "queries_dir": resolve_path(
            base_dir,
            str(report_config.get("queries_dir") or "queries"),
        ),
        "template_csv": resolve_path(
            base_dir,
            str(report_config.get("template_csv") or "report-template.csv"),
        ),
        "output_csv": resolve_path(
            base_dir,
            str(report_config.get("output_csv") or "report-output.csv"),
        ),
        "query_column_name": str(report_config.get("query_column_name") or "Query"),
        "default_collection": str(report_config.get("default_collection") or ""),
        "mode": str(report_config.get("mode") or "placeholder"),
        "raw_query_id": str(report_config.get("raw_query_id") or "1"),
        "include_query_column": bool(report_config.get("include_query_column", False)),
        "output_columns": output_columns,
        "allow_disk_use": bool(report_config.get("allow_disk_use", False)),
        "hint": str(report_config.get("hint") or "").strip(),
        "max_time_ms": int(report_config.get("max_time_ms") or 0),
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

    collections = config.get("collections", {})
    if collections is None:
        collections = {}
    if not isinstance(collections, dict):
        raise ValueError("Config key 'collections' must be a YAML object.")

    merged: dict[str, str] = {}
    for source in (collections, variables):
        for key, value in source.items():
            merged[str(key)] = str(value)

    default_collection = report_config.get("default_collection")
    if default_collection:
        merged.setdefault("default_collection", str(default_collection))

    end_date_value = merged.get("end_date")
    if end_date_value and "end_date_exclusive" not in merged:
        end_date_dt = parse_iso_date_or_datetime(end_date_value)
        merged["end_date_exclusive"] = (end_date_dt + timedelta(days=1)).isoformat()

    return merged


def render_template(text: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        if variable_name not in variables:
            raise ValueError(f"Missing template variable '{variable_name}' in config.yml.")
        return variables[variable_name]

    return VARIABLE_PATTERN.sub(replace, text)


def resolve_special_values(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"$dateVar"}:
            variable_name = str(value["$dateVar"])
            if variable_name not in variables:
                raise ValueError(f"Missing date variable '{variable_name}' in config.yml.")
            return parse_iso_date_or_datetime(variables[variable_name])
        return {key: resolve_special_values(inner, variables) for key, inner in value.items()}

    if isinstance(value, list):
        return [resolve_special_values(item, variables) for item in value]

    return value


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, list):
        return [normalize_scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(key).lower(): normalize_scalar(inner) for key, inner in value.items()}
    return value


def normalize_result_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): normalize_scalar(value) for key, value in row.items()}


def format_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def serialize_for_query_column(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported value type: {type(value)!r}")


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


def load_query_definition(query_file: Path, variables: dict[str, str]) -> tuple[str, str, list[Any]]:
    query_template = query_file.read_text(encoding="utf-8")
    rendered_query = render_template(query_template, variables)
    definition = yaml.safe_load(rendered_query)
    if not isinstance(definition, dict):
        raise ValueError(f"Query file must contain a YAML object: {query_file}")

    query_title = str(definition.get("title") or f"Query {query_file.stem}")
    collection_name = str(definition.get("collection") or variables.get("default_collection") or "").strip()
    if not collection_name:
        raise ValueError(f"Query {query_file.stem} does not specify a collection and no default_collection is configured.")

    pipeline = resolve_special_values(definition.get("pipeline"), variables)
    if not isinstance(pipeline, list):
        raise ValueError(f"Query {query_file.stem} must define a pipeline list.")

    return query_title, collection_name, pipeline


def execute_query(
    mongo_db: Any,
    query_file: Path,
    variables: dict[str, str],
    report_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    query_started_at = timer.perf_counter()
    query_id = query_file.stem
    query_title, collection_name, pipeline = load_query_definition(query_file, variables)

    LOGGER.info(
        "Executing query id=%s | title=%s | collection=%s | stages=%s | allow_disk_use=%s | hint=%s | max_time_ms=%s",
        query_id,
        query_title,
        collection_name,
        len(pipeline),
        report_config.get("allow_disk_use"),
        report_config.get("hint") or "(none)",
        report_config.get("max_time_ms") or "(none)",
    )
    aggregate_options: dict[str, Any] = {}
    if report_config.get("allow_disk_use"):
        aggregate_options["allowDiskUse"] = True
    if report_config.get("hint"):
        aggregate_options["hint"] = report_config["hint"]
    if report_config.get("max_time_ms"):
        aggregate_options["maxTimeMS"] = report_config["max_time_ms"]

    rows = [normalize_result_row(row) for row in mongo_db[collection_name].aggregate(pipeline, **aggregate_options)]
    rendered_query = json.dumps(
        {
            "collection": collection_name,
            "pipeline": pipeline,
        },
        default=serialize_for_query_column,
        ensure_ascii=True,
        indent=2,
    )
    duration_seconds = timer.perf_counter() - query_started_at
    timing = {
        "query_id": query_id,
        "title": query_title,
        "collection": collection_name,
        "row_count": len(rows),
        "duration_seconds": duration_seconds,
    }
    LOGGER.info(
        "Completed query id=%s | title=%s | rows=%s | duration=%.3fs",
        query_id,
        query_title,
        len(rows),
        duration_seconds,
    )
    return rows, rendered_query, timing


def get_query_file(queries_dir: Path, query_id: str) -> Path:
    query_file = queries_dir / f"{query_id}.yml"
    if not query_file.exists():
        raise FileNotFoundError(f"Query file not found: {query_file}")
    return query_file


def populate_placeholder_template(
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


def read_template_headers(template_csv: Path) -> list[str]:
    with template_csv.open("r", encoding="utf-8-sig", newline="") as source_handle:
        reader = csv.reader(source_handle)
        headers = next(reader, None)
    if not headers:
        raise ValueError(f"Template CSV must contain at least a header row: {template_csv}")
    return [str(header) for header in headers]


def build_output_columns(report_config: dict[str, Any], template_headers: list[str], rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    configured_columns = report_config.get("output_columns") or []
    if configured_columns:
        resolved_columns: list[dict[str, str]] = []
        for entry in configured_columns:
            if not isinstance(entry, dict):
                raise ValueError("Each item in report_generation.output_columns must be a YAML object.")
            source = str(entry.get("source") or "").strip().lower()
            header = str(entry.get("header") or "").strip()
            if not source or not header:
                raise ValueError("Each output_columns item must contain non-empty 'source' and 'header'.")
            resolved_columns.append({"source": source, "header": header})
        return resolved_columns

    if template_headers:
        return [{"source": header.strip().lower(), "header": header.strip()} for header in template_headers]

    if rows:
        return [{"source": key, "header": key} for key in rows[0].keys()]

    raise ValueError("Unable to determine output columns.")


def write_raw_rows_output(
    template_csv: Path,
    output_csv: Path,
    report_config: dict[str, Any],
    rows: list[dict[str, Any]],
    rendered_query: str,
) -> None:
    template_headers = read_template_headers(template_csv)
    output_columns = build_output_columns(report_config, template_headers, rows)
    include_query_column = bool(report_config.get("include_query_column"))
    query_column_name = str(report_config.get("query_column_name") or "Query")

    fieldnames = [column["header"] for column in output_columns]
    if include_query_column and query_column_name not in fieldnames:
        fieldnames.append(query_column_name)

    output_rows: list[dict[str, str]] = []
    for row in rows:
        output_row: dict[str, str] = {}
        for column in output_columns:
            output_row[column["header"]] = format_cell_value(row.get(column["source"], ""))
        if include_query_column:
            output_row[query_column_name] = rendered_query
        output_rows.append(output_row)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as target_handle:
        writer = csv.DictWriter(target_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)


def write_runtime_metadata(
    output_csv: Path,
    script_started_at: datetime,
    script_finished_at: datetime,
    total_duration_seconds: float,
    query_timings: list[dict[str, Any]],
) -> Path:
    metadata_path = output_csv.with_suffix(output_csv.suffix + ".runtime.json")
    payload = {
        "output_csv": str(output_csv),
        "script_start_utc": script_started_at.isoformat(),
        "script_end_utc": script_finished_at.isoformat(),
        "total_duration_seconds": round(total_duration_seconds, 3),
        "queries": [
            {
                "query_id": timing["query_id"],
                "title": timing["title"],
                "collection": timing["collection"],
                "row_count": timing["row_count"],
                "duration_seconds": round(float(timing["duration_seconds"]), 3),
            }
            for timing in query_timings
        ],
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return metadata_path


def main() -> None:
    configure_logging()
    args = parse_args()
    script_started_at = datetime.now(timezone.utc)
    overall_started_at = timer.perf_counter()
    config_path = Path(args.config).resolve()
    config = load_config(str(config_path))
    report_config = get_report_config(config, config_path)
    variables = build_runtime_variables(config, report_config)

    template_csv = report_config["template_csv"]
    output_csv = report_config["output_csv"]
    queries_dir = report_config["queries_dir"]
    mode = str(report_config["mode"]).strip().lower()

    if not template_csv.exists():
        raise FileNotFoundError(f"Template CSV not found: {template_csv}")

    mongo_database = get_config_value(
        config,
        "mongo",
        "database",
        "MONGO_DB",
        None,
    )
    if not mongo_database:
        raise ValueError("Missing MongoDB database name: MONGO_DB or mongo.database")

    LOGGER.info("Report generation started")
    LOGGER.info("Config path: %s", config_path)
    LOGGER.info("Template CSV: %s", template_csv)
    LOGGER.info("Output CSV: %s", output_csv)
    LOGGER.info("Queries dir: %s", queries_dir)
    LOGGER.info("Mongo database: %s", mongo_database)
    LOGGER.info("Mode: %s", mode)
    LOGGER.info(
        "Report date window | start_date=%s | end_date=%s (inclusive) | end_date_exclusive=%s",
        variables.get("start_date", ""),
        variables.get("end_date", ""),
        variables.get("end_date_exclusive", ""),
    )

    with get_mongo_client(config) as mongo_client:
        mongo_db = mongo_client[str(mongo_database)]

        if mode == "raw_rows":
            query_id = str(report_config["raw_query_id"])
            query_file = get_query_file(queries_dir, query_id)
            rows, rendered_query, timing = execute_query(mongo_db, query_file, variables, report_config)
            write_raw_rows_output(
                template_csv=template_csv,
                output_csv=output_csv,
                report_config=report_config,
                rows=rows,
                rendered_query=rendered_query,
            )
            query_timings = [timing]
        elif mode == "placeholder":
            referenced_query_ids = extract_referenced_query_ids(template_csv)
            LOGGER.info(
                "Referenced query ids from CSV: %s",
                ", ".join(referenced_query_ids) if referenced_query_ids else "(none)",
            )

            query_results: dict[str, dict[str, Any]] = {}
            rendered_queries: dict[str, str] = {}
            query_timings: list[dict[str, Any]] = []
            for query_id in referenced_query_ids:
                query_file = get_query_file(queries_dir, query_id)
                rows, rendered_query, timing = execute_query(mongo_db, query_file, variables, report_config)
                rendered_queries[query_id] = rendered_query
                query_timings.append(timing)
                query_results[query_id] = rows[0] if len(rows) == 1 else {}
                if len(rows) > 1:
                    raise ValueError(
                        f"Placeholder mode expects a single row per query. Query {query_id} returned {len(rows)} rows."
                    )

            populate_placeholder_template(
                template_csv=template_csv,
                output_csv=output_csv,
                query_column_name=str(report_config["query_column_name"]),
                query_results=query_results,
                rendered_queries=rendered_queries,
            )
        else:
            raise ValueError("Unsupported report_generation.mode. Use 'raw_rows' or 'placeholder'.")

    total_duration_seconds = timer.perf_counter() - overall_started_at
    script_finished_at = datetime.now(timezone.utc)
    metadata_path = write_runtime_metadata(
        output_csv=output_csv,
        script_started_at=script_started_at,
        script_finished_at=script_finished_at,
        total_duration_seconds=total_duration_seconds,
        query_timings=query_timings,
    )
    LOGGER.info("CSV output written: %s", output_csv)
    LOGGER.info("Runtime metadata written: %s", metadata_path)
    for timing in query_timings:
        LOGGER.info(
            "Query summary | id=%s | title=%s | collection=%s | rows=%s | duration=%.3fs",
            timing["query_id"],
            timing["title"],
            timing["collection"],
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
