from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from hlr_reconciliation.models.config import MongoCollectionsConfig
from hlr_reconciliation.models.records import ComparisonRecord, HlrRecord

try:
    from pymongo import InsertOne
except Exception:  # pragma: no cover - production installs pymongo.
    class InsertOne:  # type: ignore[no-redef]
        def __init__(self, document: dict[str, Any]) -> None:
            self._doc = document


class MongoRepositories:
    def __init__(self, db, collections: MongoCollectionsConfig, insert_batch_size: int) -> None:
        self.db = db
        self.collections = collections
        self.insert_batch_size = insert_batch_size

    @property
    def execution_history(self):
        return self.db[self.collections.execution_history]

    @property
    def hlr_records(self):
        return self.db[self.collections.hlr_records]

    @property
    def comparison_results(self):
        return self.db[self.collections.comparison_results]

    def successful_execution_exists(self, processing_month: str, batch_id: str) -> bool:
        return self.execution_history.find_one(
            {"processing_month": processing_month, "batch_id": batch_id, "status": "SUCCESS"},
            {"_id": 1},
        ) is not None

    def create_execution(self, document: dict[str, Any]) -> None:
        self.execution_history.insert_one(document)

    def update_execution(self, execution_id: str, updates: dict[str, Any]) -> None:
        updates["completion_timestamp"] = datetime.now(timezone.utc)
        self.execution_history.update_one({"execution_id": execution_id}, {"$set": updates})

    def insert_hlr_records(
        self,
        records: list[HlrRecord],
        *,
        batch_id: str,
        processing_month: str,
        import_timestamp: datetime,
    ) -> int:
        operations = [
            InsertOne(
                {
                    "batch_id": batch_id,
                    "processing_month": processing_month,
                    "import_timestamp": import_timestamp,
                    "IMSI": record.imsi,
                    "MSISDN": record.msisdn,
                    "IMEISV": record.imeisv,
                }
            )
            for record in records
        ]
        return self._bulk_insert(self.hlr_records, operations)

    def insert_comparison_results(
        self,
        records: list[ComparisonRecord],
        *,
        batch_id: str,
        processing_month: str,
        execution_timestamp: datetime,
    ) -> int:
        operations = [
            InsertOne(
                {
                    "batch_id": batch_id,
                    "processing_month": processing_month,
                    "execution_timestamp": execution_timestamp,
                    "IMSI": record.key.imsi,
                    "MSISDN": record.key.msisdn,
                    "inHLR": record.in_hlr,
                    "inCRM": record.in_crm,
                    "inBSS": record.in_bss,
                }
            )
            for record in records
        ]
        return self._bulk_insert(self.comparison_results, operations)

    def cleanup_month(self, processing_month: str, batch_id: str) -> dict[str, int]:
        return {
            "hlr_records": self.hlr_records.delete_many(
                {"processing_month": processing_month, "batch_id": batch_id}
            ).deleted_count,
            "comparison_results": self.comparison_results.delete_many(
                {"processing_month": processing_month, "batch_id": batch_id}
            ).deleted_count,
            "execution_history": self.execution_history.delete_many(
                {"processing_month": processing_month, "batch_id": batch_id}
            ).deleted_count,
        }

    def _bulk_insert(self, collection, operations: list[InsertOne]) -> int:
        inserted = 0
        for start in range(0, len(operations), self.insert_batch_size):
            chunk = operations[start : start + self.insert_batch_size]
            if chunk:
                result = collection.bulk_write(chunk, ordered=False)
                inserted += result.inserted_count
        return inserted
