import pytest

from hlr_reconciliation.boss.mysql_client import _rows_to_keys as boss_rows_to_keys
from hlr_reconciliation.core.exceptions import SourceDatabaseError
from hlr_reconciliation.iot.postgres_client import _rows_to_keys as iot_rows_to_keys
from hlr_reconciliation.models.records import SubscriberKey


def test_boss_rows_use_msisdn_first_imsi_second() -> None:
    assert boss_rows_to_keys([("6011", "502181", "ignored")]) == [
        SubscriberKey(imsi="502181", msisdn="6011")
    ]


def test_iot_rows_use_msisdn_first_imsi_second() -> None:
    assert iot_rows_to_keys([("6012", "502182")]) == [
        SubscriberKey(imsi="502182", msisdn="6012")
    ]


def test_source_rows_reject_missing_second_column() -> None:
    with pytest.raises(SourceDatabaseError):
        boss_rows_to_keys([("6011",)])
