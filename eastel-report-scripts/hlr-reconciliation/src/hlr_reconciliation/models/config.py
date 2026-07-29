from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneralConfig:
    application_name: str
    version: str
    environment: str
    timezone: str


@dataclass(frozen=True)
class TransferConfig:
    protocol: str
    host: str
    port: int
    username: str
    password: str
    remote_directory: str
    local_download_directory: Path
    archive_directory: Path
    temporary_directory: Path
    file_pattern: str
    timeout_seconds: int
    retry_count: int
    local_source_file: Path | None


@dataclass(frozen=True)
class HlrConfig:
    csv_delimiter: str
    encoding: str
    required_headers: tuple[str, ...]
    archive_retention_days: int


@dataclass(frozen=True)
class MySqlConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    connection_timeout_seconds: int
    sql_query: str


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    connection_timeout_seconds: int
    sslmode: str
    sql_query: str


@dataclass(frozen=True)
class MongoCollectionsConfig:
    execution_history: str
    hlr_records: str
    comparison_results: str


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    database: str
    collections: MongoCollectionsConfig
    insert_batch_size: int


@dataclass(frozen=True)
class ReportingConfig:
    report_directory: Path
    filename_format: str
    csv_delimiter: str
    output_columns: tuple[str, ...]


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool
    smtp_server: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    password: str
    sender: str
    recipients: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject_template: str
    body_template: str


@dataclass(frozen=True)
class LoggingConfig:
    log_directory: Path
    log_filename: str
    log_level: str
    rotation_when: str
    rotation_interval: int
    retention_count: int


@dataclass(frozen=True)
class SchedulerConfig:
    processing_day: int
    processing_time: str


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    base_dir: Path
    general: GeneralConfig
    scheduler: SchedulerConfig
    transfer: TransferConfig
    hlr: HlrConfig
    boss: MySqlConfig
    iot: PostgresConfig
    mongo: MongoConfig
    reporting: ReportingConfig
    email: EmailConfig
    logging: LoggingConfig
