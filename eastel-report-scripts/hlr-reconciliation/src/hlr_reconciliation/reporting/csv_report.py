from __future__ import annotations

import csv
from pathlib import Path

from hlr_reconciliation.models.config import ReportingConfig
from hlr_reconciliation.models.records import ComparisonRecord


class CsvReportWriter:
    def __init__(self, config: ReportingConfig) -> None:
        self.config = config

    def write(self, records: list[ComparisonRecord], *, processing_month: str, batch_id: str) -> Path:
        self.config.report_directory.mkdir(parents=True, exist_ok=True)
        filename = self.config.filename_format.format(
            processing_month=processing_month,
            batch_id=batch_id,
        )
        path = self.config.report_directory / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(self.config.output_columns),
                delimiter=self.config.csv_delimiter,
            )
            writer.writeheader()
            for record in records:
                writer.writerow(
                    {
                        "MSISDN": record.key.msisdn,
                        "IMSI": record.key.imsi,
                        "inBSS": _yes_no(record.in_bss),
                        "inCRM": _yes_no(record.in_crm),
                        "inHLR": _yes_no(record.in_hlr),
                    }
                )
        return path


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"
