from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class QueryDefinition:
    query_id: str
    file: Path
    output: str
    anchor: str | None
    columns: list[str]


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    database: str


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    file_path: Path | None


@dataclass(frozen=True)
class ReportGenerationConfig:
    queries_dir: Path
    template_xlsx: Path
    output_xlsx: Path
    actual_queries_output_xlsx: Path
    default_collection: str


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    base_dir: Path
    mongo: MongoConfig
    logging: LoggingConfig
    report_generation: ReportGenerationConfig
    collections: dict[str, str]
    variables: dict[str, str]
    queries: dict[str, QueryDefinition]


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_yaml_file(config_path: Path) -> dict[str, Any]:
    resolved_path = config_path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {resolved_path}")
    return data


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Config key '{key}' must be a YAML object.")
    return value


def _stringify_mapping(mapping: dict[str, Any], key: str) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise ValueError(f"Config key '{key}' must be a YAML object.")
    return {str(inner_key): str(inner_value) for inner_key, inner_value in mapping.items()}


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    data = load_yaml_file(path)
    base_dir = path.parent

    mongo_raw = _require_mapping(data, "mongo")
    mongo_uri = str(mongo_raw.get("uri") or "").strip()
    mongo_database = str(mongo_raw.get("database") or "").strip()

    report_raw = _require_mapping(data, "report_generation")
    queries_dir = resolve_path(base_dir, str(report_raw.get("queries_dir") or "queries"))
    template_xlsx = resolve_path(base_dir, str(report_raw.get("template_xlsx") or "template.xlsx"))
    output_xlsx = resolve_path(base_dir, str(report_raw.get("output_xlsx") or "report-output.xlsx"))
    actual_queries_output_xlsx = resolve_path(
        base_dir,
        str(report_raw.get("actual_quries_used_output_file") or "actual-queries-used.xlsx"),
    )
    default_collection = str(report_raw.get("default_collection") or "").strip()

    collections = _stringify_mapping(data.get("collections") or {}, "collections")
    variables = _stringify_mapping(data.get("variables") or {}, "variables")

    logging_raw = _require_mapping(data, "logging")
    logging_file_path_raw = str(logging_raw.get("file_path") or "").strip()
    logging_file_path = Path(logging_file_path_raw) if logging_file_path_raw else None

    queries_raw = _require_mapping(data, "queries")
    query_definitions: dict[str, QueryDefinition] = {}
    for query_id, query_value in queries_raw.items():
        if not isinstance(query_value, dict):
            raise ValueError(f"Config key 'queries.{query_id}' must be a YAML object.")

        query_id_text = str(query_id)
        query_file_raw = str(query_value.get("file") or "").strip()
        if not query_file_raw:
            raise ValueError(f"Config key 'queries.{query_id_text}.file' is required.")

        query_definitions[query_id_text] = QueryDefinition(
            query_id=query_id_text,
            file=resolve_path(base_dir, query_file_raw),
            output=str(query_value.get("output") or "").strip(),
            anchor=str(query_value.get("anchor")).strip() if query_value.get("anchor") is not None else None,
            columns=[str(column) for column in (query_value.get("columns") or [])],
        )

    return AppConfig(
        config_path=path,
        base_dir=base_dir,
        mongo=MongoConfig(uri=mongo_uri, database=mongo_database),
        logging=LoggingConfig(level=str(logging_raw.get("level") or "INFO").upper(), file_path=logging_file_path),
        report_generation=ReportGenerationConfig(
            queries_dir=queries_dir,
            template_xlsx=template_xlsx,
            output_xlsx=output_xlsx,
            actual_queries_output_xlsx=actual_queries_output_xlsx,
            default_collection=default_collection,
        ),
        collections=collections,
        variables=variables,
        queries=query_definitions,
    )
