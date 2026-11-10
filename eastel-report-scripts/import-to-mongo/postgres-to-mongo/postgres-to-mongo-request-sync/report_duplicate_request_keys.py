import argparse
import os
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import MongoClient


DEFAULT_SOURCE_TABLE = "iot_portal_tb_request_log"
DEFAULT_MONGO_DB = "eastel-data"
DEFAULT_MONGO_COLLECTION = "request_logs"
DEFAULT_STATE_COLLECTION = "request_log_sync_state"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
DEFAULT_GROUP_LIMIT = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report source rows that share the same "
            "(session_id, session_req_num, rating_group). The Mongo collection indexes that "
            "triple without a unique constraint, so these rows are mirrored into MongoDB and "
            "may inflate per-session report totals. Read-only."
        )
    )
    parser.add_argument(
        "--source-table",
        default=os.getenv("PG_SOURCE_TABLE", DEFAULT_SOURCE_TABLE),
        help="PostgreSQL source table name.",
    )
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", DEFAULT_MONGO_DB))
    parser.add_argument("--mongo-collection", default=os.getenv("MONGO_COLLECTION", DEFAULT_MONGO_COLLECTION))
    parser.add_argument("--state-collection", default=os.getenv("MONGO_STATE_COLLECTION", DEFAULT_STATE_COLLECTION))
    parser.add_argument(
        "--min-request-log-id",
        type=int,
        default=None,
        help=(
            "Only inspect rows above this id. Defaults to the stored sync checkpoint, which is "
            "the part of the table the sync still has to push."
        ),
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Inspect the whole table instead of the rows after the sync checkpoint. Slow on large tables.",
    )
    parser.add_argument(
        "--group-limit",
        type=int,
        default=DEFAULT_GROUP_LIMIT,
        help="Number of duplicate groups to print in detail.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file used when env vars are not set.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def get_config_value(config: dict[str, Any], section: str, key: str, env_name: str, default: Any = None) -> Any:
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    section_data = config.get(section, {})
    if isinstance(section_data, dict) and key in section_data and section_data[key] not in (None, ""):
        return section_data[key]
    return default


def get_postgres_dsn(config: dict[str, Any]) -> str:
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn
    dsn = config.get("postgres", {}).get("dsn")
    if dsn:
        return str(dsn)

    host = get_config_value(config, "postgres", "host", "PGHOST", "localhost")
    port = get_config_value(config, "postgres", "port", "PGPORT", "5432")
    dbname = get_config_value(config, "postgres", "database", "PGDATABASE")
    user = get_config_value(config, "postgres", "user", "PGUSER")
    password = get_config_value(config, "postgres", "password", "PGPASSWORD")
    sslmode = get_config_value(config, "postgres", "sslmode", "PGSSLMODE")

    parts = [f"host={host}", f"port={port}", f"dbname={dbname}", f"user={user}", f"password={password}"]
    if sslmode:
        parts.append(f"sslmode={sslmode}")
    return " ".join(parts)


def get_mongo_client(config: dict[str, Any]) -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI") or config.get("mongo", {}).get("uri")
    if not mongo_uri:
        raise ValueError("Missing MongoDB setting: MONGO_URI")
    return MongoClient(mongo_uri)


def get_request_log_source_table(config: dict[str, Any], default: str) -> str:
    sync_config = config.get("sync", {})
    if isinstance(sync_config, dict):
        value = sync_config.get("postgres_request_source_table")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_mongo_db_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_database")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_request_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_request_log_state_collection_name(config: dict[str, Any], default: str) -> str:
    mongo_config = config.get("mongo", {})
    if isinstance(mongo_config, dict):
        value = mongo_config.get("eastel_request_state_collection")
        if value not in (None, ""):
            return str(value)
    return default


def get_last_synced_id(state_collection, source_table: str, mongo_collection: str) -> int:
    state = state_collection.find_one(
        {"_id": f"{source_table}->{mongo_collection}"},
        {"last_request_log_id": 1},
    )
    if not state:
        return 0
    return int(state.get("last_request_log_id", 0))


def print_source_constraints(cursor, source_table: str) -> None:
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = %s::regclass
        ORDER BY conname
        """,
        (source_table,),
    )
    rows = cursor.fetchall()
    print(f"--- constraints on {source_table} ---")
    if not rows:
        print(" (none)")
    for row in rows:
        print(f" {row['conname']}: {row['definition']}")


def print_duplicate_summary(cursor, table: sql.Composable, min_request_log_id: int) -> None:
    cursor.execute(
        sql.SQL(
            """
            SELECT count(*) AS duplicate_groups,
                   coalesce(sum(row_count), 0) AS duplicate_rows
            FROM (
                SELECT count(*) AS row_count
                FROM {table}
                WHERE request_log_id > %s
                GROUP BY session_id, session_req_num, rating_group
                HAVING count(*) > 1
            ) AS duplicates
            """
        ).format(table=table),
        (min_request_log_id,),
    )
    summary = cursor.fetchone()
    print("--- duplicate business keys ---")
    print(f" rows above request_log_id {min_request_log_id}: duplicate groups="
          f"{int(summary['duplicate_groups'] or 0)}, rows in those groups="
          f"{int(summary['duplicate_rows'] or 0)}")


def print_duplicate_groups(cursor, table: sql.Composable, min_request_log_id: int, group_limit: int) -> None:
    cursor.execute(
        sql.SQL(
            """
            SELECT session_id, session_req_num, rating_group, count(*) AS row_count
            FROM {table}
            WHERE request_log_id > %s
            GROUP BY session_id, session_req_num, rating_group
            HAVING count(*) > 1
            ORDER BY count(*) DESC, max(request_log_id) DESC
            LIMIT %s
            """
        ).format(table=table),
        (min_request_log_id, group_limit),
    )
    groups = cursor.fetchall()
    print(f"--- {len(groups)} duplicate group(s) in detail ---")
    for group in groups:
        cursor.execute(
            sql.SQL(
                """
                SELECT request_log_id, req_type, req_time, cr_time, total_used_volume,
                       price_total_used_money, notes, operation_status
                FROM {table}
                WHERE session_id IS NOT DISTINCT FROM %s
                  AND session_req_num IS NOT DISTINCT FROM %s
                  AND rating_group IS NOT DISTINCT FROM %s
                ORDER BY request_log_id
                """
            ).format(table=table),
            (group["session_id"], group["session_req_num"], group["rating_group"]),
        )
        print(
            f"\n session_id={group['session_id']} "
            f"session_req_num={group['session_req_num']} "
            f"rating_group={group['rating_group']} rows={group['row_count']}"
        )
        for row in cursor.fetchall():
            print(
                f"   request_log_id={row['request_log_id']} req_type={row['req_type']} "
                f"req_time={row['req_time']} cr_time={row['cr_time']} "
                f"total_used_volume={row['total_used_volume']} "
                f"price_total_used_money={row['price_total_used_money']} "
                f"notes={row['notes']} operation_status={row['operation_status']}"
            )


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    mongo_db_name = get_request_log_mongo_db_name(
        config,
        str(get_config_value(config, "mongo", "database", "MONGO_DB", args.mongo_db)),
    )
    mongo_collection_name = get_request_log_collection_name(
        config,
        str(get_config_value(config, "mongo", "collection", "MONGO_COLLECTION", args.mongo_collection)),
    )
    state_collection_name = get_request_log_state_collection_name(
        config,
        str(get_config_value(config, "mongo", "state_collection", "MONGO_STATE_COLLECTION", args.state_collection)),
    )
    source_table = get_request_log_source_table(
        config,
        str(get_config_value(config, "sync", "source_table", "PG_SOURCE_TABLE", args.source_table)),
    )

    with get_mongo_client(config) as mongo_client:
        state_collection = mongo_client[mongo_db_name][state_collection_name]
        checkpoint = get_last_synced_id(
            state_collection=state_collection,
            source_table=source_table,
            mongo_collection=mongo_collection_name,
        )

    min_request_log_id = args.min_request_log_id
    if min_request_log_id is None:
        min_request_log_id = 0 if args.scan_all else checkpoint

    print(f"source table: {source_table}")
    print(f"mongo collection: {mongo_db_name}.{mongo_collection_name}")
    print(f"sync checkpoint: {checkpoint}")
    print(f"scanning request_log_id > {min_request_log_id}")
    print()

    with psycopg.connect(get_postgres_dsn(config), row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            print_source_constraints(cursor, source_table)
            print()
            print_duplicate_summary(cursor, sql.Identifier(source_table), min_request_log_id)
            print()
            print_duplicate_groups(cursor, sql.Identifier(source_table), min_request_log_id, args.group_limit)


if __name__ == "__main__":
    main()
