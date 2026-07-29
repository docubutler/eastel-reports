from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from hlr_reconciliation.models.config import (
    AppConfig,
    EmailConfig,
    GeneralConfig,
    HlrConfig,
    LoggingConfig,
    MongoCollectionsConfig,
    MongoConfig,
    MySqlConfig,
    PostgresConfig,
    ReportingConfig,
    SchedulerConfig,
    TransferConfig,
)

ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")

    base_dir = path.parent
    general = _mapping(data, "general")
    scheduler = _mapping(data, "scheduler")
    transfer = _mapping(data, "transfer")
    hlr = _mapping(data, "hlr")
    boss = _mapping(data, "boss")
    iot = _mapping(data, "iot")
    mongo = _mapping(data, "mongo")
    reporting = _mapping(data, "reporting")
    email = _mapping(data, "email")
    logging = _mapping(data, "logging")
    collections = _mapping(mongo, "collections")

    local_source_file = _optional_path(base_dir, _expand(transfer.get("local_source_file", "")))

    return AppConfig(
        config_path=path,
        base_dir=base_dir,
        general=GeneralConfig(
            application_name=_string(general, "application_name"),
            version=_string(general, "version"),
            environment=_string(general, "environment"),
            timezone=_string(general, "timezone"),
        ),
        scheduler=SchedulerConfig(
            processing_day=_int(scheduler, "processing_day", 1),
            processing_time=_string(scheduler, "processing_time", "02:00"),
        ),
        transfer=TransferConfig(
            protocol=_string(transfer, "protocol", "sftp").lower(),
            host=_string(transfer, "host", ""),
            port=_int(transfer, "port", 22),
            username=_string(transfer, "username", ""),
            password=_string(transfer, "password", ""),
            remote_directory=_string(transfer, "remote_directory", ""),
            local_download_directory=_path(base_dir, transfer, "local_download_directory", "./data/downloads"),
            archive_directory=_path(base_dir, transfer, "archive_directory", "./data/archive"),
            temporary_directory=_path(base_dir, transfer, "temporary_directory", "./data/tmp"),
            file_pattern=_string(transfer, "file_pattern", "*.tar.gz"),
            timeout_seconds=_int(transfer, "timeout_seconds", 60),
            retry_count=_int(transfer, "retry_count", 3),
            local_source_file=local_source_file,
        ),
        hlr=HlrConfig(
            csv_delimiter=_string(hlr, "csv_delimiter", ","),
            encoding=_string(hlr, "encoding", "utf-8"),
            required_headers=tuple(str(value) for value in hlr.get("required_headers", [])),
            archive_retention_days=_int(hlr, "archive_retention_days", 365),
        ),
        boss=MySqlConfig(
            host=_string(boss, "host", ""),
            port=_int(boss, "port", 3306),
            database=_string(boss, "database", ""),
            username=_string(boss, "username", ""),
            password=_string(boss, "password", ""),
            connection_timeout_seconds=_int(boss, "connection_timeout_seconds", 30),
            sql_query=_string(boss, "sql_query", ""),
        ),
        iot=PostgresConfig(
            host=_string(iot, "host", ""),
            port=_int(iot, "port", 5432),
            database=_string(iot, "database", ""),
            username=_string(iot, "username", ""),
            password=_string(iot, "password", ""),
            connection_timeout_seconds=_int(iot, "connection_timeout_seconds", 30),
            sslmode=_string(iot, "sslmode", "prefer"),
            sql_query=_string(iot, "sql_query", ""),
        ),
        mongo=MongoConfig(
            uri=_string(mongo, "uri", ""),
            database=_string(mongo, "database", ""),
            collections=MongoCollectionsConfig(
                execution_history=_string(collections, "execution_history", "execution_history"),
                hlr_records=_string(collections, "hlr_records", "hlr_records"),
                comparison_results=_string(collections, "comparison_results", "comparison_results"),
            ),
            insert_batch_size=_int(mongo, "insert_batch_size", 5000),
        ),
        reporting=ReportingConfig(
            report_directory=_path(base_dir, reporting, "report_directory", "./reports"),
            filename_format=_string(reporting, "filename_format", "HLR_SYNC_REPORT_{batch_id}.csv"),
            csv_delimiter=_string(reporting, "csv_delimiter", ","),
            output_columns=tuple(str(value) for value in reporting.get("output_columns", [])),
        ),
        email=EmailConfig(
            enabled=_bool(email, "enabled", True),
            smtp_server=_string(email, "smtp_server", ""),
            port=_int(email, "port", 587),
            use_tls=_bool(email, "use_tls", True),
            use_ssl=_bool(email, "use_ssl", False),
            username=_string(email, "username", ""),
            password=_string(email, "password", ""),
            sender=_string(email, "sender", ""),
            recipients=tuple(str(value) for value in email.get("recipients", [])),
            cc=tuple(str(value) for value in email.get("cc", [])),
            bcc=tuple(str(value) for value in email.get("bcc", [])),
            subject_template=_string(email, "subject_template", ""),
            body_template=_string(email, "body_template", ""),
        ),
        logging=LoggingConfig(
            log_directory=_path(base_dir, logging, "log_directory", "./logs"),
            log_filename=_string(logging, "log_filename", "hlr_reconciliation.log"),
            log_level=_string(logging, "log_level", "INFO").upper(),
            rotation_when=_string(logging, "rotation_when", "midnight"),
            rotation_interval=_int(logging, "rotation_interval", 1),
            retention_count=_int(logging, "retention_count", 30),
        ),
    )


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config key '{key}' must be a YAML object.")
    return value


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        match = ENV_PATTERN.match(value.strip())
        if match:
            return os.getenv(match.group(1), "")
    return value


def _string(data: dict[str, Any], key: str, default: str = "") -> str:
    value = _expand(data.get(key, default))
    return str(value or "").strip()


def _int(data: dict[str, Any], key: str, default: int) -> int:
    value = _expand(data.get(key, default))
    return int(value)


def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = _expand(data.get(key, default))
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _path(base_dir: Path, data: dict[str, Any], key: str, default: str) -> Path:
    raw = _string(data, key, default)
    path = Path(raw)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _optional_path(base_dir: Path, raw_value: Any) -> Path | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()
