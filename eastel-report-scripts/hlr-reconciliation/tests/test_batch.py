from datetime import date

import pytest

from hlr_reconciliation.core.batch import derive_batch_id, derive_processing_month


def test_derive_batch_id() -> None:
    assert derive_batch_id("2026-07") == "202607"


def test_derive_processing_month_from_date() -> None:
    assert derive_processing_month(today=date(2026, 7, 29)) == "2026-07"


def test_invalid_processing_month() -> None:
    with pytest.raises(ValueError):
        derive_batch_id("2026-13")
