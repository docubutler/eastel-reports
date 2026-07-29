from datetime import datetime, timezone
from logging import getLogger

from fakes import FakeDb

from hlr_reconciliation.models.config import MongoCollectionsConfig
from hlr_reconciliation.models.records import HlrRecord
from hlr_reconciliation.mongo import MongoRepositories, initialize_mongo


def test_initialize_mongo_is_idempotent() -> None:
    db = FakeDb()
    collections = MongoCollectionsConfig(
        execution_history="execution_history",
        hlr_records="hlr_records",
        comparison_results="comparison_results",
    )

    initialize_mongo(db, collections, getLogger("test"))
    initialize_mongo(db, collections, getLogger("test"))

    assert set(db.list_collection_names()) == {
        "execution_history",
        "hlr_records",
        "comparison_results",
    }
    assert db["execution_history"].indexes


def test_repository_cleanup_month_deletes_only_target_month() -> None:
    db = FakeDb()
    collections = MongoCollectionsConfig("execution_history", "hlr_records", "comparison_results")
    initialize_mongo(db, collections, getLogger("test"))
    repositories = MongoRepositories(db, collections, insert_batch_size=100)
    repositories.insert_hlr_records(
        [HlrRecord(imsi="1", msisdn="2", imeisv="3")],
        batch_id="202607",
        processing_month="2026-07",
        import_timestamp=datetime.now(timezone.utc),
    )
    repositories.hlr_records.insert_one(
        {
            "batch_id": "202608",
            "processing_month": "2026-08",
            "IMSI": "4",
            "MSISDN": "5",
        }
    )
    repositories.execution_history.insert_one(
        {"batch_id": "202607", "processing_month": "2026-07", "status": "SUCCESS"}
    )

    result = repositories.cleanup_month("2026-07", "202607")

    assert result["hlr_records"] == 1
    assert result["execution_history"] == 1
    assert repositories.hlr_records.find_one({"processing_month": "2026-08"}) is not None
