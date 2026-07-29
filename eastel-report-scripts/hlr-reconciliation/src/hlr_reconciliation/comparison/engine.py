from __future__ import annotations

from collections.abc import Iterable

from hlr_reconciliation.models.records import ComparisonRecord, SubscriberKey


def compare_subscribers(
    hlr_keys: Iterable[SubscriberKey],
    crm_keys: Iterable[SubscriberKey],
    bss_keys: Iterable[SubscriberKey],
) -> list[ComparisonRecord]:
    hlr_set = set(hlr_keys)
    crm_set = set(crm_keys)
    bss_set = set(bss_keys)
    all_keys = sorted(hlr_set | crm_set | bss_set)
    return [
        ComparisonRecord(
            key=key,
            in_hlr=key in hlr_set,
            in_crm=key in crm_set,
            in_bss=key in bss_set,
        )
        for key in all_keys
    ]
