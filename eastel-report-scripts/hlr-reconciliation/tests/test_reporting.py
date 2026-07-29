from pathlib import Path

from hlr_reconciliation.models.config import ReportingConfig
from hlr_reconciliation.models.records import ComparisonRecord, SubscriberKey
from hlr_reconciliation.reporting import CsvReportWriter


def test_csv_report_writer_outputs_required_columns(tmp_path: Path) -> None:
    writer = CsvReportWriter(
        ReportingConfig(
            report_directory=tmp_path,
            filename_format="HLR_SYNC_REPORT_{batch_id}.csv",
            csv_delimiter=",",
            output_columns=("MSISDN", "IMSI", "inBSS", "inCRM", "inHLR"),
        )
    )
    path = writer.write(
        [
            ComparisonRecord(
                key=SubscriberKey(imsi="502181", msisdn="6011"),
                in_hlr=True,
                in_crm=False,
                in_bss=True,
            )
        ],
        processing_month="2026-07",
        batch_id="202607",
    )

    assert path.name == "HLR_SYNC_REPORT_202607.csv"
    assert path.read_text(encoding="utf-8").splitlines() == [
        "MSISDN,IMSI,inBSS,inCRM,inHLR",
        "6011,502181,Yes,No,Yes",
    ]
