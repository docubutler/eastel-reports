from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from pymongo import MongoClient

from hlr_reconciliation.config.loader import load_config
from hlr_reconciliation.logging.setup import configure_logging
from hlr_reconciliation.mongo.initializer import initialize_mongo


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize HLR reconciliation MongoDB collections and indexes.")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.yml")),
        help="Path to YAML config file.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    logger = configure_logging(config.logging)
    with MongoClient(config.mongo.uri) as client:
        initialize_mongo(client[config.mongo.database], config.mongo.collections, logger)
    logger.info("MongoDB initialization completed.")


if __name__ == "__main__":
    main()
