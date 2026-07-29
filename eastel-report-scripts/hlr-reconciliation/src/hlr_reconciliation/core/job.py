from __future__ import annotations

import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from hlr_reconciliation.boss import BossMySqlClient
from hlr_reconciliation.comparison import compare_subscribers
from hlr_reconciliation.config.validator import validate_config
from hlr_reconciliation.core.batch import derive_batch_id, derive_processing_month
from hlr_reconciliation.core.exceptions import IdempotencyError
from hlr_reconciliation.email import SmtpEmailSender
from hlr_reconciliation.hlr import extract_hlr_archive, parse_hlr_csv
from hlr_reconciliation.iot import IotPostgresClient
from hlr_reconciliation.models.config import AppConfig
from hlr_reconciliation.models.summary import ExecutionSummary
from hlr_reconciliation.mongo import MongoRepositories, initialize_mongo
from hlr_reconciliation.reporting import CsvReportWriter
from hlr_reconciliation.transfer import build_transfer_client
from hlr_reconciliation.utils import sha256_file


class MonthlyReconciliationJob:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def run(self, processing_month: str | None = None) -> ExecutionSummary:
        validate_config(self.config, require_runtime_secrets=True)
        month = derive_processing_month(processing_month)
        batch_id = derive_batch_id(month)
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        timer_start = time.perf_counter()
        self.logger.info("Starting HLR reconciliation for processing_month=%s batch_id=%s", month, batch_id)

        from pymongo import MongoClient

        with MongoClient(self.config.mongo.uri) as mongo_client:
            db = mongo_client[self.config.mongo.database]
            initialize_mongo(db, self.config.mongo.collections, self.logger)
            repositories = MongoRepositories(
                db,
                self.config.mongo.collections,
                self.config.mongo.insert_batch_size,
            )
            if repositories.successful_execution_exists(month, batch_id):
                message = (
                    f"Processing has already been completed for month {month} "
                    f"(Batch ID: {batch_id}). Please execute the monthly cleanup utility "
                    "before reprocessing this month."
                )
                self.logger.warning(message)
                raise IdempotencyError(message)

            repositories.create_execution(
                {
                    "batch_id": batch_id,
                    "execution_id": execution_id,
                    "processing_month": month,
                    "execution_timestamp": started_at,
                    "status": "RUNNING",
                    "remarks": "Execution started.",
                }
            )
            try:
                summary = self._run_after_history_created(
                    repositories=repositories,
                    processing_month=month,
                    batch_id=batch_id,
                    execution_id=execution_id,
                    started_at=started_at,
                    timer_start=timer_start,
                )
                repositories.update_execution(
                    execution_id,
                    {
                        "status": "SUCCESS",
                        "HLR record count": summary.hlr_record_count,
                        "CRM record count": summary.crm_record_count,
                        "IOT record count": summary.iot_record_count,
                        "comparison record count": summary.comparison_record_count,
                        "execution duration": summary.duration_seconds,
                        "report filename": summary.report_filename,
                        "remarks": "Execution completed successfully.",
                    },
                )
                self.logger.info("HLR reconciliation completed successfully: %s", summary)
                return summary
            except Exception as exc:
                repositories.update_execution(
                    execution_id,
                    {
                        "status": "FAILED",
                        "remarks": str(exc),
                        "execution duration": time.perf_counter() - timer_start,
                    },
                )
                self.logger.exception("HLR reconciliation failed")
                raise

    def cleanup_month(self, processing_month: str, *, force: bool) -> dict[str, int]:
        if not force:
            raise ValueError("cleanup-month requires --force")
        month = derive_processing_month(processing_month)
        batch_id = derive_batch_id(month)
        validate_config(self.config, require_runtime_secrets=False)
        if not self.config.mongo.uri:
            raise ValueError("mongo.uri is required for cleanup")
        from pymongo import MongoClient

        with MongoClient(self.config.mongo.uri) as mongo_client:
            db = mongo_client[self.config.mongo.database]
            initialize_mongo(db, self.config.mongo.collections, self.logger)
            repositories = MongoRepositories(db, self.config.mongo.collections, self.config.mongo.insert_batch_size)
            result = repositories.cleanup_month(month, batch_id)
        self.logger.warning("Cleanup completed for processing_month=%s batch_id=%s result=%s", month, batch_id, result)
        return result

    def _run_after_history_created(
        self,
        *,
        repositories: MongoRepositories,
        processing_month: str,
        batch_id: str,
        execution_id: str,
        started_at: datetime,
        timer_start: float,
    ) -> ExecutionSummary:
        transfer_client = build_transfer_client(self.config.transfer, self.logger)
        downloaded_archive = transfer_client.download_latest()
        source_hash = sha256_file(downloaded_archive)
        self.logger.info("Downloaded HLR archive file=%s hash=%s", downloaded_archive.name, source_hash)

        csv_path = extract_hlr_archive(downloaded_archive, self.config.transfer.temporary_directory)
        hlr_records = parse_hlr_csv(
            csv_path,
            delimiter=self.config.hlr.csv_delimiter,
            encoding=self.config.hlr.encoding,
            required_headers=self.config.hlr.required_headers,
        )
        repositories.insert_hlr_records(
            hlr_records,
            batch_id=batch_id,
            processing_month=processing_month,
            import_timestamp=datetime.now(timezone.utc),
        )
        self.logger.info("Imported %s HLR records", len(hlr_records))

        crm_keys = BossMySqlClient(self.config.boss).fetch_active_subscribers()
        bss_keys = IotPostgresClient(self.config.iot).fetch_active_subscribers()
        comparison_records = compare_subscribers(
            (record.key for record in hlr_records),
            crm_keys,
            bss_keys,
        )
        repositories.insert_comparison_results(
            comparison_records,
            batch_id=batch_id,
            processing_month=processing_month,
            execution_timestamp=started_at,
        )
        self.logger.info("Stored %s comparison records", len(comparison_records))

        report_path = CsvReportWriter(self.config.reporting).write(
            comparison_records,
            processing_month=processing_month,
            batch_id=batch_id,
        )
        duration = time.perf_counter() - timer_start
        summary = ExecutionSummary(
            processing_month=processing_month,
            batch_id=batch_id,
            hlr_record_count=len(hlr_records),
            crm_record_count=len(crm_keys),
            iot_record_count=len(bss_keys),
            comparison_record_count=len(comparison_records),
            missing_in_hlr=sum(1 for record in comparison_records if not record.in_hlr),
            missing_in_crm=sum(1 for record in comparison_records if not record.in_crm),
            missing_in_bss=sum(1 for record in comparison_records if not record.in_bss),
            duration_seconds=duration,
            report_filename=str(report_path),
        )
        SmtpEmailSender(self.config.email).send_report(report_path, summary)
        self._archive_source(downloaded_archive)
        repositories.update_execution(
            execution_id,
            {
                "source_filename": downloaded_archive.name,
                "source_file_hash": source_hash,
            },
        )
        return summary

    def _archive_source(self, archive_path: Path) -> None:
        self.config.transfer.archive_directory.mkdir(parents=True, exist_ok=True)
        target = self.config.transfer.archive_directory / archive_path.name
        if archive_path.resolve() != target.resolve():
            shutil.copy2(archive_path, target)
            self.logger.info("Archived HLR source file to %s", target)
