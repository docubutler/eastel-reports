from hlr_reconciliation.comparison import compare_subscribers
from hlr_reconciliation.models.records import SubscriberKey


def test_compare_subscribers_outputs_unique_membership_flags() -> None:
    key_all = SubscriberKey(imsi="502181", msisdn="6011")
    key_crm_only = SubscriberKey(imsi="502182", msisdn="6012")
    key_bss_only = SubscriberKey(imsi="502183", msisdn="6013")

    result = compare_subscribers(
        hlr_keys=[key_all, key_all],
        crm_keys=[key_all, key_crm_only],
        bss_keys=[key_all, key_bss_only],
    )

    assert len(result) == 3
    by_key = {record.key: record for record in result}
    assert by_key[key_all].in_hlr is True
    assert by_key[key_all].in_crm is True
    assert by_key[key_all].in_bss is True
    assert by_key[key_crm_only].in_hlr is False
    assert by_key[key_crm_only].in_crm is True
    assert by_key[key_bss_only].in_bss is True
