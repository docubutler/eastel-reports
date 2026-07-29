from __future__ import annotations

from datetime import date


def derive_processing_month(month: str | None = None, today: date | None = None) -> str:
    if month:
        _validate_month(month)
        return month
    current = today or date.today()
    return f"{current.year:04d}-{current.month:02d}"


def derive_batch_id(processing_month: str) -> str:
    _validate_month(processing_month)
    return processing_month.replace("-", "")


def _validate_month(month: str) -> None:
    parts = month.split("-")
    if len(parts) != 2:
        raise ValueError("Processing month must use YYYY-MM format")
    year, month_number = parts
    if len(year) != 4 or len(month_number) != 2:
        raise ValueError("Processing month must use YYYY-MM format")
    int_month = int(month_number)
    if int_month < 1 or int_month > 12:
        raise ValueError("Processing month must use YYYY-MM format")
