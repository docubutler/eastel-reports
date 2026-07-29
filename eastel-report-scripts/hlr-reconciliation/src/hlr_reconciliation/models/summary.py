from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionSummary:
    processing_month: str
    batch_id: str
    hlr_record_count: int
    crm_record_count: int
    iot_record_count: int
    comparison_record_count: int
    missing_in_hlr: int
    missing_in_crm: int
    missing_in_bss: int
    duration_seconds: float
    report_filename: str
