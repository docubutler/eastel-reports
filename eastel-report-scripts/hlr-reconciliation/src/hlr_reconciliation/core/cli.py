from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymongo import MongoClient

from hlr_reconciliation.config import load_config, validate_config
from hlr_reconciliation.core.exceptions import HlrReconciliationError
from hlr_reconciliation.core.job import MonthlyReconciliationJob
from hlr_reconciliation.logging import configure_logging
from hlr_reconciliation.mongo import initialize_mongo


def main(default_config_path: Path | None = None) -> None:
    parser = argparse.ArgumentParser(description="HLR/BOSS/IOT monthly reconciliation")
    parser.add_argument("--config", default=str(default_config_path or Path("config.yml")))
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run monthly reconciliation")
    run_parser.add_argument("--month", help="Processing month in YYYY-MM format")

    subparsers.add_parser("init-db", help="Create MongoDB collections and indexes")

    cleanup_parser = subparsers.add_parser("cleanup-month", help="Remove all records for a processing month")
    cleanup_parser.add_argument("month", help="Processing month in YYYY-MM format")
    cleanup_parser.add_argument("--force", action="store_true", help="Required confirmation for cleanup")

    subparsers.add_parser("validate-config", help="Validate configuration file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        logger = configure_logging(config.logging)
        if args.command == "validate-config":
            validate_config(config, require_runtime_secrets=False)
            logger.info("Configuration is valid.")
            return
        if args.command == "init-db":
            if not config.mongo.uri:
                raise ValueError("mongo.uri is required for init-db")
            with MongoClient(config.mongo.uri) as client:
                initialize_mongo(client[config.mongo.database], config.mongo.collections, logger)
            logger.info("MongoDB initialization completed.")
            return
        job = MonthlyReconciliationJob(config, logger)
        if args.command == "run":
            summary = job.run(args.month)
            print(summary)
            return
        if args.command == "cleanup-month":
            result = job.cleanup_month(args.month, force=args.force)
            print(result)
            return
    except HlrReconciliationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(exc.exit_code)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
