from __future__ import annotations

from hlr_reconciliation.models.config import AppConfig


def validate_config(config: AppConfig, *, require_runtime_secrets: bool = False) -> None:
    if config.transfer.protocol not in {"sftp", "ftp", "local"}:
        raise ValueError("transfer.protocol must be one of: sftp, ftp, local")
    if not config.hlr.required_headers:
        raise ValueError("hlr.required_headers must not be empty")
    if config.hlr.csv_delimiter == "":
        raise ValueError("hlr.csv_delimiter must not be empty")
    if not config.mongo.database:
        raise ValueError("mongo.database is required")
    if not config.reporting.output_columns:
        raise ValueError("reporting.output_columns must not be empty")
    if "msisdn" not in config.boss.sql_query.lower() or "imsi" not in config.boss.sql_query.lower():
        raise ValueError("boss.sql_query must select msisdn as the first column and imsi as the second column")
    if "msisdn" not in config.iot.sql_query.lower() or "imsi" not in config.iot.sql_query.lower():
        raise ValueError("iot.sql_query must select msisdn as the first column and imsi as the second column")

    if not require_runtime_secrets:
        return

    if config.transfer.protocol in {"sftp", "ftp"}:
        _require("transfer.host", config.transfer.host)
        _require("transfer.username", config.transfer.username)
        _require("transfer.password", config.transfer.password)
    if config.transfer.protocol == "local":
        if config.transfer.local_source_file is None:
            raise ValueError("transfer.local_source_file is required when transfer.protocol is local")
    _require("boss.host", config.boss.host)
    _require("boss.database", config.boss.database)
    _require("boss.username", config.boss.username)
    _require("boss.password", config.boss.password)
    _require("iot.host", config.iot.host)
    _require("iot.database", config.iot.database)
    _require("iot.username", config.iot.username)
    _require("iot.password", config.iot.password)
    _require("mongo.uri", config.mongo.uri)
    if config.email.enabled:
        _require("email.smtp_server", config.email.smtp_server)
        _require("email.sender", config.email.sender)
        if not config.email.recipients:
            raise ValueError("email.recipients must not be empty when email.enabled is true")


def _require(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} is required")
