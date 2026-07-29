from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class SubscriberKey:
    imsi: str
    msisdn: str


@dataclass(frozen=True)
class HlrRecord:
    imsi: str
    msisdn: str
    imeisv: str

    @property
    def key(self) -> SubscriberKey:
        return SubscriberKey(imsi=self.imsi, msisdn=self.msisdn)


@dataclass(frozen=True)
class ComparisonRecord:
    key: SubscriberKey
    in_hlr: bool
    in_crm: bool
    in_bss: bool
