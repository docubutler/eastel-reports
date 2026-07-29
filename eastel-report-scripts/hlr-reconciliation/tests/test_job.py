import csv
import tarfile
from pathlib import Path

import pytest

from fakes import FakeDb

from hlr_reconciliation.core.exceptions import IdempotencyError
from hlr_reconciliation.core.job import MonthlyReconciliationJob
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
from hlr_reconciliation.models.records import SubscriberKey


class FakeMongoClient:
    db = FakeDb()

    def __init__(self, uri: str) -> None:
        self.uri = uri

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def __getitem__(self, name: str):
        return self.db


class FakeTransfer:
    def __init__(self, archive_path: Path) -> None:
        self.archive_path = archive_path

    def download_latest(self) -> Path:
        return self.archive_path


class FakeSource:
    def __init__(self, keys: list[SubscriberKey]) -> None:
        self.keys = keys

    def fetch_active_subscribers(self) -> list[SubscriberKey]:
        return self.keys


class FakeEmail:
    sent: list[Path] = []

    def __init__(self, config) -> None:
        self.config = config

    def send_report(self, report_path: Path, summary) -> None:
        self.sent.append(report_path)


def test_job_run_completes_with_mocked_dependencies(tmp_path: Path, monkeypatch) -> None:
    archive_path = _make_hlr_archive(tmp_path)
    config = _make_config(tmp_path, email_enabled=True)
    FakeMongoClient.db = FakeDb()
    FakeEmail.sent = []

    import pymongo
    import hlr_reconciliation.core.job as job_module

    monkeypatch.setattr(pymongo, "MongoClient", FakeMongoClient)
    monkeypatch.setattr(job_module, "build_transfer_client", lambda config, logger: FakeTransfer(archive_path))
    monkeypatch.setattr(
        job_module,
        "BossMySqlClient",
        lambda config: FakeSource([SubscriberKey(imsi="502181", msisdn="6011")]),
    )
    monkeypatch.setattr(
        job_module,
        "IotPostgresClient",
        lambda config: FakeSource([SubscriberKey(imsi="502182", msisdn="6012")]),
    )
    monkeypatch.setattr(job_module, "SmtpEmailSender", FakeEmail)

    summary = MonthlyReconciliationJob(config, _null_logger()).run("2026-07")

    assert summary.batch_id == "202607"
    assert summary.hlr_record_count == 1
    assert summary.crm_record_count == 1
    assert summary.iot_record_count == 1
    assert summary.comparison_record_count == 2
    assert Path(summary.report_filename).exists()
    assert FakeEmail.sent == [Path(summary.report_filename)]
    assert FakeMongoClient.db["execution_history"].find_one({"status": "SUCCESS"}) is not None


def test_job_run_aborts_when_successful_month_exists(tmp_path: Path, monkeypatch) -> None:
    config = _make_config(tmp_path, email_enabled=False)
    FakeMongoClient.db = FakeDb()
    FakeMongoClient.db["execution_history"].insert_one(
        {
            "processing_month": "2026-07",
            "batch_id": "202607",
            "status": "SUCCESS",
        }
    )

    import pymongo

    monkeypatch.setattr(pymongo, "MongoClient", FakeMongoClient)

    with pytest.raises(IdempotencyError):
        MonthlyReconciliationJob(config, _null_logger()).run("2026-07")

    assert len(FakeMongoClient.db["hlr_records"].documents) == 0


def _make_hlr_archive(tmp_path: Path) -> Path:
    csv_path = tmp_path / "hlr.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["IMSI", "MSISDN", "IMEISV"])
        writer.writerow(["502181", "6011", "1234"])
    archive_path = tmp_path / "MVNO_ANCHOR_2026070102.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(csv_path, arcname="hlr.csv")
    return archive_path


def _make_config(tmp_path: Path, *, email_enabled: bool) -> AppConfig:
    collections = MongoCollectionsConfig("execution_history", "hlr_records", "comparison_results")
    return AppConfig(
        config_path=tmp_path / "config.yml",
        base_dir=tmp_path,
        general=GeneralConfig("HLR", "1", "test", "UTC"),
        scheduler=SchedulerConfig(1, "02:00"),
        transfer=TransferConfig(
            protocol="local",
            host="",
            port=22,
            username="",
            password="",
            remote_directory="",
            local_download_directory=tmp_path / "downloads",
            archive_directory=tmp_path / "archive",
            temporary_directory=tmp_path / "tmp",
            file_pattern="*.tar.gz",
            timeout_seconds=1,
            retry_count=1,
            local_source_file=tmp_path / "source.tar.gz",
        ),
        hlr=HlrConfig(",", "utf-8", ("IMSI", "MSISDN", "IMEISV"), 365),
        boss=MySqlConfig("host", 3306, "db", "user", "password", 30, "select msisdn, imsi from boss"),
        iot=PostgresConfig("host", 5432, "db", "user", "password", 30, "prefer", "select msisdn, imsi from iot"),
        mongo=MongoConfig("mongodb://fake", "db", collections, 100),
        reporting=ReportingConfig(
            tmp_path / "reports",
            "HLR_SYNC_REPORT_{batch_id}.csv",
            ",",
            ("MSISDN", "IMSI", "inBSS", "inCRM", "inHLR"),
        ),
        email=EmailConfig(
            enabled=email_enabled,
            smtp_server="smtp",
            port=587,
            use_tls=False,
            use_ssl=False,
            username="",
            password="",
            sender="sender@example.com",
            recipients=("ops@example.com",),
            cc=(),
            bcc=(),
            subject_template="HLR {processing_month}",
            body_template="Done {batch_id}",
        ),
        logging=LoggingConfig(tmp_path / "logs", "test.log", "INFO", "midnight", 1, 1),
    )


def _null_logger():
    import logging

    logger = logging.getLogger("test_hlr_job")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return logger
