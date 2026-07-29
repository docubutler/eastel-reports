from __future__ import annotations

from collections.abc import Iterable

from hlr_reconciliation.core.exceptions import SourceDatabaseError
from hlr_reconciliation.models.config import MySqlConfig
from hlr_reconciliation.models.records import SubscriberKey


class BossMySqlClient:
    def __init__(self, config: MySqlConfig) -> None:
        self.config = config

    def fetch_active_subscribers(self) -> list[SubscriberKey]:
        try:
            import mysql.connector

            connection = mysql.connector.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connection_timeout=self.config.connection_timeout_seconds,
            )
            try:
                cursor = connection.cursor()
                cursor.execute(self.config.sql_query)
                return _rows_to_keys(cursor.fetchall())
            finally:
                connection.close()
        except Exception as exc:
            raise SourceDatabaseError("Failed to fetch BOSS CRM subscribers from MySQL") from exc


def _rows_to_keys(rows: Iterable[tuple[object, ...]]) -> list[SubscriberKey]:
    keys: list[SubscriberKey] = []
    for row in rows:
        if len(row) < 2:
            raise SourceDatabaseError("BOSS query must return msisdn as column 1 and imsi as column 2")
        msisdn = str(row[0] or "").strip()
        imsi = str(row[1] or "").strip()
        if msisdn and imsi:
            keys.append(SubscriberKey(imsi=imsi, msisdn=msisdn))
    return keys
