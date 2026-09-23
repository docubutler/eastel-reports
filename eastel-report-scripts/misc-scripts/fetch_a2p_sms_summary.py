"""
Read-only helper: preview the Domestic A2P SMS (Q015) summary for a date window
directly from Mongo, matching the report engine's Q015 aggregation.

Reads connection settings from misc-scripts/config.yml (or MONGO_URI env var).
Default window = August 2026 (exclusive end), matching an invoice recon run.

Usage:
    python misc-scripts/fetch_a2p_sms_summary.py
    python misc-scripts/fetch_a2p_sms_summary.py --start "2026-08-01 00:00:00" --end "2026-09-01 00:00:00"
"""
import argparse
import datetime
import os
from pathlib import Path

import yaml
from pymongo import MongoClient

DEFAULT_CONFIG = Path(__file__).with_name("config.yml")
COLLECTION = "smsc_cdrs"
PARSERS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")


def load_settings():
    if os.getenv("MONGO_URI"):
        return os.environ["MONGO_URI"], "eastel-data"
    with open(DEFAULT_CONFIG, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    mongo = cfg.get("mongo", {}) or {}
    return mongo["uri"], mongo.get("database", "eastel-data")


def parse_dt(text):
    for parser in PARSERS:
        try:
            value = datetime.datetime.strptime(text.strip(), parser)
            return value.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {text}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-08-01 00:00:00")
    parser.add_argument("--end", default="2026-09-01 00:00:00")
    args = parser.parse_args()
    start_date = parse_dt(args.start)
    end_date = parse_dt(args.end)

    uri, dbname = load_settings()
    client = MongoClient(uri, serverSelectionTimeoutMS=60000)
    col = client[dbname][COLLECTION]

    pipeline = [
        {
            "$match": {
                "delivery_date": {"$gte": start_date, "$lt": end_date},
                "message_type": "message",
                "origination_type": "SMPP",
                "message_delivery_status": {"$in": ["success", "success_esme"]},
                "$or": [
                    {"addr_src_digits": {"$regex": "^2"}},
                    {"addr_src_digits": "601170337777"},
                    {"addr_src_digits": {"$regex": "^6"}},
                ],
            }
        },
        {
            "$addFields": {
                "charge_type": {
                    "$switch": {
                        "branches": [
                            {"case": {"$or": [
                                {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^2"}},
                                {"$eq": ["$addr_src_digits", "601170337777"]}]},
                             "then": "Non-Profit A2P SMS MT Bundled"},
                            {"case": {"$and": [
                                {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^6"}},
                                {"$ne": ["$addr_src_digits", "601170337777"]}]},
                             "then": "Commercial A2P SMS MT"}]}},
                "sms_type": {
                    "$switch": {
                        "branches": [
                            {"case": {"$or": [
                                {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^2"}},
                                {"$eq": ["$addr_src_digits", "601170337777"]}]},
                             "then": "Non Profit A2P (22200,22288,22200EASTEL,601170337777)"},
                            {"case": {"$and": [
                                {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^6"}},
                                {"$ne": ["$addr_src_digits", "601170337777"]}]},
                             "then": "Commercial A2P"}]}}}},
        },
        {"$match": {"charge_type": {"$ne": None}}},
        {"$group": {"_id": {"charge_type": "$charge_type", "sms_type": "$sms_type"}, "sms_count": {"$sum": 1}}},
        {"$project": {
            "_id": 0,
            "service_type": {"$literal": "SMS"},
            "charge_type": "$_id.charge_type",
            "sms_type": "$_id.sms_type",
            "sms_count": 1,
            "sort_order": {"$cond": [{"$eq": ["$_id.charge_type", "Commercial A2P SMS MT"]}, 1, 2]},
        }},
        {"$sort": {"sort_order": 1, "sms_type": 1}},
        {"$project": {"sort_order": 0}},
    ]

    print(f"Window: {start_date.isoformat()} .. {end_date.isoformat()} (db={dbname}, collection={COLLECTION})")
    rows = list(col.aggregate(pipeline, allowDiskUse=True))
    if not rows:
        print("No Domestic A2P SMS records found in this window.")
        return
    total = 0
    for row in rows:
        print(f"{row['charge_type']:<28} | {row['sms_type']:<60} | {row['sms_count']}")
        total += row["sms_count"]
    print(f"TOTAL A2P SMS: {total}")


if __name__ == "__main__":
    main()
