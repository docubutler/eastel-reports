from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient

from .config_loader import AppConfig, QueryDefinition


LOGGER = logging.getLogger(__name__)

ScalarResult = dict[str, Any]
TableResult = list[dict[str, Any]]
QueryPayload = ScalarResult | TableResult


@dataclass(frozen=True)
class QueryExecutionResult:
    query_id: str
    payload: QueryPayload
    duration_seconds: float


@dataclass
class ExecutionContext:
    config: AppConfig
    pg_conn: psycopg.Connection[Any]
    mongo_client: MongoClient[Any] | None

    @property
    def mongo_db(self) -> Any:
        if self.mongo_client is None:
            raise ValueError("MongoDB is not configured.")
        return self.mongo_client[self.config.mongo.database]

    def close(self) -> None:
        self.pg_conn.close()
        if self.mongo_client is not None:
            self.mongo_client.close()


def _get_config_value(raw_value: str, env_name: str, default: str = "") -> str:
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    return raw_value or default


def _build_postgres_dsn(config: AppConfig) -> str:
    env_dsn = os.getenv("POSTGRES_DSN")
    if env_dsn:
        return env_dsn
    if config.postgres.dsn:
        return config.postgres.dsn

    host = _get_config_value(config.postgres.host, "PGHOST", "localhost")
    port = _get_config_value(config.postgres.port, "PGPORT", "5432")
    dbname = _get_config_value(config.postgres.database, "PGDATABASE")
    user = _get_config_value(config.postgres.user, "PGUSER")
    password = _get_config_value(config.postgres.password, "PGPASSWORD")
    sslmode = _get_config_value(config.postgres.sslmode, "PGSSLMODE")

    missing = [name for name, value in {"PGDATABASE": dbname, "PGUSER": user, "PGPASSWORD": password}.items() if not value]
    if missing:
        raise ValueError(f"Missing PostgreSQL settings: {', '.join(missing)}")

    parts = [f"host={host}", f"port={port}", f"dbname={dbname}", f"user={user}", f"password={password}"]
    if sslmode:
        parts.append(f"sslmode={sslmode}")
    return " ".join(parts)


def _parse_datetime(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _normalize_value(value) for key, value in row.items()}


def _ensure_reference_temp_tables(context: ExecutionContext) -> None:
    if context.mongo_client is None:
        LOGGER.info("MongoDB is not configured; reference temp tables will be empty.")
        return

    db = context.mongo_db
    country_collection = context.config.collections.get("country_code", "country_code")
    roaming_collection = context.config.collections.get("roaming_destination", "roaming_destination")

    country_rows = [
        (str(doc.get("country") or "").strip(), str(doc.get("country_code") or "").strip())
        for doc in db[country_collection].find({}, {"_id": 0, "country": 1, "country_code": 1})
        if str(doc.get("country_code") or "").strip()
    ]
    roaming_rows = [
        (
            int(doc.get("roaming_destination_id")),
            str(doc.get("roaming_destination_name") or "").strip(),
            str(doc.get("country") or "").strip(),
        )
        for doc in db[roaming_collection].find(
            {},
            {"_id": 0, "roaming_destination_id": 1, "roaming_destination_name": 1, "country": 1},
        )
        if doc.get("roaming_destination_id") is not None
    ]

    with context.pg_conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS temp_country_code (
                country text,
                country_code text
            ) ON COMMIT PRESERVE ROWS
            """
        )
        cursor.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS temp_roaming_destination (
                roaming_destination_id numeric(20,0),
                roaming_destination_name text,
                country text
            ) ON COMMIT PRESERVE ROWS
            """
        )
        cursor.execute("TRUNCATE temp_country_code")
        cursor.execute("TRUNCATE temp_roaming_destination")
        if country_rows:
            cursor.executemany(
                "INSERT INTO temp_country_code (country, country_code) VALUES (%s, %s)",
                country_rows,
            )
        if roaming_rows:
            cursor.executemany(
                """
                INSERT INTO temp_roaming_destination
                    (roaming_destination_id, roaming_destination_name, country)
                VALUES (%s, %s, %s)
                """,
                roaming_rows,
            )

    context.pg_conn.commit()
    LOGGER.info("Loaded Mongo references into Postgres temp tables | countries=%s | roaming_destinations=%s", len(country_rows), len(roaming_rows))


def create_execution_context(config: AppConfig) -> ExecutionContext:
    pg_conn = psycopg.connect(_build_postgres_dsn(config))
    mongo_uri = os.getenv("MONGO_URI") or config.mongo.uri
    mongo_client: MongoClient[Any] | None = None
    if mongo_uri and config.mongo.database:
        mongo_client = MongoClient(mongo_uri)

    context = ExecutionContext(config=config, pg_conn=pg_conn, mongo_client=mongo_client)
    _ensure_reference_temp_tables(context)
    return context


def _coerce_payload(query_id: str, query_definition: QueryDefinition, rows: list[dict[str, Any]]) -> QueryPayload:
    normalized_rows = [_normalize_row(row) for row in rows]
    if query_definition.output == "scalar":
        if not normalized_rows:
            return {}
        if len(normalized_rows) > 1:
            raise ValueError(f"Scalar query {query_id} returned {len(normalized_rows)} rows.")
        return normalized_rows[0]
    if query_definition.output == "fixed_table":
        return normalized_rows
    raise ValueError(
        f"Unsupported query output '{query_definition.output}' for {query_id}. "
        "Expected 'scalar' or 'fixed_table'."
    )


def _execute_postgres_query(
    query_id: str,
    rendered_query: str,
    query_definition: QueryDefinition,
    context: ExecutionContext,
) -> QueryPayload:
    with context.pg_conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(rendered_query)
        rows = list(cursor.fetchall())
    return _coerce_payload(query_id, query_definition, rows)


def _execute_mongo_a2p_sms(query_definition: QueryDefinition, context: ExecutionContext) -> QueryPayload:
    db = context.mongo_db
    collection_name = context.config.collections.get("smsc_cdr", "smsc_cdrs")
    start_date = _parse_datetime(context.config.variables["start_date"])
    end_date = _parse_datetime(context.config.variables["end_date"])

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
                            {
                                "case": {
                                    "$or": [
                                        {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^2"}},
                                        {"$eq": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": "Non-Profit A2P SMS MT Bundled",
                            },
                            {
                                "case": {
                                    "$and": [
                                        {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^6"}},
                                        {"$ne": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": "Commercial A2P SMS MT",
                            },
                        ],
                        "default": None,
                    }
                },
                "sms_type": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$or": [
                                        {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^2"}},
                                        {"$eq": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": "Non Profit A2P (22200,22288,22200EASTEL,601170337777)",
                            },
                            {
                                "case": {
                                    "$and": [
                                        {"$regexMatch": {"input": {"$ifNull": ["$addr_src_digits", ""]}, "regex": "^6"}},
                                        {"$ne": ["$addr_src_digits", "601170337777"]},
                                    ]
                                },
                                "then": "Commercial A2P",
                            },
                        ],
                        "default": None,
                    }
                },
            }
        },
        {"$match": {"charge_type": {"$ne": None}}},
        {"$group": {"_id": {"charge_type": "$charge_type", "sms_type": "$sms_type"}, "sms_count": {"$sum": 1}}},
        {
            "$project": {
                "_id": 0,
                "service_type": {"$literal": "SMS"},
                "charge_type": "$_id.charge_type",
                "sms_type": "$_id.sms_type",
                "sms_count": 1,
                "sort_order": {"$cond": [{"$eq": ["$_id.charge_type", "Commercial A2P SMS MT"]}, 1, 2]},
            }
        },
        {"$sort": {"sort_order": 1, "sms_type": 1}},
        {"$project": {"sort_order": 0}},
    ]
    rows = list(db[collection_name].aggregate(pipeline))
    return _coerce_payload(query_definition.query_id, query_definition, rows)


def execute_query(
    query_id: str,
    rendered_query: str,
    query_definition: QueryDefinition,
    context: ExecutionContext,
) -> QueryExecutionResult:
    started_at = time.perf_counter()
    LOGGER.info("Executing query %s from %s with engine=%s", query_id, query_definition.file.name, query_definition.engine)

    if query_definition.engine == "postgres":
        payload = _execute_postgres_query(query_id, rendered_query, query_definition, context)
    elif query_definition.engine == "mongo_a2p_sms":
        payload = _execute_mongo_a2p_sms(query_definition, context)
    else:
        raise ValueError(f"Unsupported query engine '{query_definition.engine}' for {query_id}.")

    duration_seconds = time.perf_counter() - started_at
    LOGGER.info("Completed query %s in %.3fs", query_id, duration_seconds)
    return QueryExecutionResult(query_id=query_id, payload=payload, duration_seconds=duration_seconds)
