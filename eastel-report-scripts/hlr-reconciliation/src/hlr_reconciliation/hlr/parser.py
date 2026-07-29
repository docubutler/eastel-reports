from __future__ import annotations

import csv
from pathlib import Path

from hlr_reconciliation.core.exceptions import HlrFileError
from hlr_reconciliation.models.records import HlrRecord


def parse_hlr_csv(
    csv_path: Path,
    *,
    delimiter: str,
    encoding: str,
    required_headers: tuple[str, ...],
) -> list[HlrRecord]:
    if not csv_path.exists():
        raise HlrFileError(f"HLR CSV not found: {csv_path}")

    records: list[HlrRecord] = []
    with csv_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = tuple(reader.fieldnames or [])
        missing = [header for header in required_headers if header not in headers]
        if missing:
            raise HlrFileError(f"HLR CSV missing required headers: {', '.join(missing)}")
        for line_number, row in enumerate(reader, start=2):
            imsi = _normalize(row.get("IMSI"))
            msisdn = _normalize(row.get("MSISDN"))
            imeisv = _normalize(row.get("IMEISV"))
            if not imsi or not msisdn:
                raise HlrFileError(f"HLR CSV row {line_number} has blank IMSI or MSISDN")
            records.append(HlrRecord(imsi=imsi, msisdn=msisdn, imeisv=imeisv))
    return records


def _normalize(value: object) -> str:
    return str(value or "").strip()
