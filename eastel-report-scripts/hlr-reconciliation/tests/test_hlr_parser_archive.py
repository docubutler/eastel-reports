import csv
import tarfile
from pathlib import Path

import pytest

from hlr_reconciliation.core.exceptions import HlrFileError
from hlr_reconciliation.hlr import extract_hlr_archive, parse_hlr_csv


def test_parse_hlr_csv_validates_and_parses_records(tmp_path: Path) -> None:
    csv_path = tmp_path / "hlr.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["IMSI", "MSISDN", "IMEISV"])
        writer.writerow([" 502181880368282 ", " 601176062977 ", "8683800674025856"])

    records = parse_hlr_csv(
        csv_path,
        delimiter=",",
        encoding="utf-8",
        required_headers=("IMSI", "MSISDN", "IMEISV"),
    )

    assert len(records) == 1
    assert records[0].imsi == "502181880368282"
    assert records[0].msisdn == "601176062977"
    assert records[0].imeisv == "8683800674025856"


def test_parse_hlr_csv_rejects_missing_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "hlr.csv"
    csv_path.write_text("IMSI,MSISDN\n1,2\n", encoding="utf-8")

    with pytest.raises(HlrFileError, match="missing required headers"):
        parse_hlr_csv(
            csv_path,
            delimiter=",",
            encoding="utf-8",
            required_headers=("IMSI", "MSISDN", "IMEISV"),
        )


def test_extract_hlr_archive_returns_single_csv(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text("IMSI,MSISDN,IMEISV\n1,2,3\n", encoding="utf-8")
    archive = tmp_path / "MVNO_ANCHOR_2026070102.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_csv, arcname="hlr.csv")

    extracted = extract_hlr_archive(archive, tmp_path / "tmp")

    assert extracted.name == "hlr.csv"
    assert extracted.exists()
