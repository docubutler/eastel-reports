from __future__ import annotations

import logging

from hlr_reconciliation.models.config import MongoCollectionsConfig

ASCENDING = 1


def initialize_mongo(db, collections: MongoCollectionsConfig, logger: logging.Logger) -> None:
    existing = set(db.list_collection_names())
    for name in (
        collections.execution_history,
        collections.hlr_records,
        collections.comparison_results,
    ):
        if name not in existing:
            db.create_collection(name)
            logger.info("Created MongoDB collection %s", name)

    execution_history = db[collections.execution_history]
    execution_history.create_index(
        [("processing_month", ASCENDING), ("batch_id", ASCENDING), ("status", ASCENDING)],
        name="ux_successful_month",
        unique=True,
        partialFilterExpression={"status": "SUCCESS"},
    )
    execution_history.create_index([("execution_id", ASCENDING)], name="ix_execution_id")

    hlr_records = db[collections.hlr_records]
    hlr_records.create_index([("processing_month", ASCENDING), ("batch_id", ASCENDING)], name="ix_hlr_month_batch")
    hlr_records.create_index([("IMSI", ASCENDING), ("MSISDN", ASCENDING)], name="ix_hlr_imsi_msisdn")
    hlr_records.create_index(
        [("processing_month", ASCENDING), ("IMSI", ASCENDING), ("MSISDN", ASCENDING)],
        name="ix_hlr_month_key",
    )

    comparison_results = db[collections.comparison_results]
    comparison_results.create_index(
        [("processing_month", ASCENDING), ("batch_id", ASCENDING)],
        name="ix_comparison_month_batch",
    )
    comparison_results.create_index(
        [("IMSI", ASCENDING), ("MSISDN", ASCENDING)],
        name="ix_comparison_imsi_msisdn",
    )
    comparison_results.create_index(
        [("processing_month", ASCENDING), ("IMSI", ASCENDING), ("MSISDN", ASCENDING)],
        name="ix_comparison_month_key",
    )
