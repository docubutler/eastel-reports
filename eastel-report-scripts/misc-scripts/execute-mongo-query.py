"""
execute-mongo-query.py

Purpose:
- Execute a MongoDB `find` or `aggregate` query using connection settings from
  `misc-scripts/config.yml`.
- Read the default query from `config.yml` or accept a query from the command line.
- Print progress, run `EXPLAIN`, print results to console, and append output to a log file.

Config-driven usage:
- Put the query under `execution.query` in `misc-scripts/config.yml`.
- Then run:
  `python misc-scripts/execute-mongo-query.py`

Supported query input formats:
- YAML/JSON object style:
  `{session_id: {$regex: '1031490875;0c640b03'}}`
- Mongo shell-style regex literals:
  `{session_id: /1031490875;0c640b03/}`
  `{session_id: /1031490875;0c640b03/i}`
- Mongo shell-style date and object id helpers:
  `{created_at: ISODate('2026-01-28T11:01:58.473Z')}`
  `{_id: ObjectId('507f1f77bcf86cd799439011')}`

Common examples:
- Exact match:
  `{imei: '863316052085459'}`
- SQL `LIKE '%abc%'` equivalent:
  `{session_id: {$regex: 'abc'}}`
- SQL `LIKE 'abc%'` equivalent:
  `{session_id: {$regex: '^abc'}}`
- SQL `LIKE '%abc'` equivalent:
  `{session_id: {$regex: 'abc$'}}`

CLI examples:
- Use query from config:
  `python misc-scripts/execute-mongo-query.py`
- Inline query:
  `python misc-scripts/execute-mongo-query.py --query "{imei: '863316052085459'}"`
- Named query from config:
  `python misc-scripts/execute-mongo-query.py --query-name imei_lookup`

Notes:
- Exact matches are usually much faster than partial regex matches.
- Unanchored regex like `/abc/` may scan many documents even if an index exists.
- Results and execution logs are appended to the configured `execution.log_file`
  when that setting is present.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime
import traceback
import re

import yaml
from bson import json_util
from bson.objectid import ObjectId
from bson.regex import Regex
from pymongo import MongoClient


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute a MongoDB find or aggregate query using settings from config.yml."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--collection",
        help="Collection name. Defaults to mongo.default_collection from config.yml.",
    )
    parser.add_argument(
        "--mode",
        choices=["find", "aggregate"],
        default="find",
        help="Query execution mode.",
    )
    parser.add_argument(
        "--query",
        help="Inline JSON query/filter or aggregation pipeline.",
    )
    parser.add_argument(
        "--query-name",
        help="Named query from config.yml under the queries section.",
    )
    parser.add_argument(
        "--query-file",
        help="Path to a file containing JSON query/filter or aggregation pipeline.",
    )
    parser.add_argument(
        "--projection",
        help="Optional JSON projection for find mode.",
    )
    parser.add_argument(
        "--sort",
        help="Optional JSON sort document for find mode.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of documents to return. Use 0 for no limit.",
    )
    return parser.parse_args()


def load_yaml_file(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def load_json_text(args: argparse.Namespace) -> str:
    if args.query_name:
        raise ValueError("Internal error: load_json_text does not handle --query-name.")
    if args.query and args.query_file:
        raise ValueError("Use either --query or --query-file, not both.")
    if not args.query and not args.query_file:
        raise ValueError("One of --query or --query-file is required.")

    if args.query:
        return args.query

    query_file_path = Path(args.query_file).resolve()
    if not query_file_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_file_path}")
    return query_file_path.read_text(encoding="utf-8")


def parse_extended_json(text: str) -> Any:
    return json_util.loads(text)


def _extract_balanced_call(text: str, start_index: int) -> tuple[str, int]:
    depth = 0
    in_single = False
    in_double = False
    escape = False

    for index in range(start_index, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if in_single or in_double:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1], index + 1

    raise ValueError("Unbalanced function-style expression in query text.")


def _replace_shell_literals(text: str) -> str:
    result: list[str] = []
    index = 0
    in_single = False
    in_double = False
    regex_allowed = False

    while index < len(text):
        char = text[index]

        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            index += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            index += 1
            continue

        if in_single or in_double:
            result.append(char)
            index += 1
            continue

        if text.startswith("ISODate(", index):
            call_text, next_index = _extract_balanced_call(text, index + len("ISODate"))
            iso_text = _parse_shell_call_argument(call_text, "ISODate")
            result.append(f"'__ISODATEVALUE__{iso_text}'")
            index = next_index
            regex_allowed = False
            continue

        if text.startswith("ObjectId(", index):
            call_text, next_index = _extract_balanced_call(text, index + len("ObjectId"))
            object_id_text = _parse_shell_call_argument(call_text, "ObjectId")
            result.append(f"'__OBJECTIDVALUE__{object_id_text}'")
            index = next_index
            regex_allowed = False
            continue

        if char == ":" or char == "," or char == "[":
            regex_allowed = True
            result.append(char)
            index += 1
            continue

        if regex_allowed and char in " \t\r\n":
            result.append(char)
            index += 1
            continue

        if regex_allowed and char == "/":
            index += 1
            pattern_chars: list[str] = []
            escape = False
            while index < len(text):
                current = text[index]
                if escape:
                    pattern_chars.append(current)
                    escape = False
                    index += 1
                    continue
                if current == "\\":
                    pattern_chars.append(current)
                    escape = True
                    index += 1
                    continue
                if current == "/":
                    break
                pattern_chars.append(current)
                index += 1

            if index >= len(text) or text[index] != "/":
                raise ValueError("Unterminated regex literal in query text.")

            index += 1
            flags_start = index
            while index < len(text) and text[index].isalpha():
                index += 1
            flags = text[flags_start:index]
            pattern = "".join(pattern_chars)
            marker = f"__REGEX__{pattern}__FLAGS__{flags}"
            result.append(f"'{marker}'")
            regex_allowed = False
            continue

        regex_allowed = False
        result.append(char)
        index += 1

    return "".join(result)


def _parse_shell_call_argument(call_text: str, function_name: str) -> str:
    inner = call_text.strip()
    if not inner.startswith("(") or not inner.endswith(")"):
        raise ValueError(f"Invalid {function_name} expression: {call_text}")
    argument_text = inner[1:-1].strip()
    parsed_argument = yaml.safe_load(argument_text)
    if not isinstance(parsed_argument, str):
        raise ValueError(f"{function_name} requires a quoted string argument.")
    return parsed_argument


def _convert_shell_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert_shell_values(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_convert_shell_values(item) for item in value]
    if isinstance(value, str):
        if value.startswith("__REGEX__") and "__FLAGS__" in value:
            pattern, flags = value[len("__REGEX__") :].split("__FLAGS__", 1)
            return Regex(pattern, flags)
        if value.startswith("__ISODATEVALUE__"):
            iso_text = value[len("__ISODATEVALUE__") :]
            normalized = iso_text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        if value.startswith("__OBJECTIDVALUE__"):
            object_id_text = value[len("__OBJECTIDVALUE__") :]
            return ObjectId(object_id_text)
    return value


def parse_query_text(text: str) -> Any:
    try:
        return json_util.loads(text)
    except Exception:
        normalized_text = _replace_shell_literals(text)
        parsed = yaml.safe_load(normalized_text)
        if parsed is None:
            raise ValueError("Query text is empty.")
        return _convert_shell_values(parsed)


def get_named_query(config: dict[str, Any], query_name: str) -> dict[str, Any]:
    queries = config.get("queries", {})
    if not isinstance(queries, dict):
        raise ValueError("Config key 'queries' must be a YAML object.")

    query_definition = queries.get(query_name)
    if not isinstance(query_definition, dict):
        raise ValueError(f"Named query not found in config.yml: {query_name}")

    return query_definition


def resolve_query_inputs(args: argparse.Namespace, config: dict[str, Any]) -> tuple[str | None, str | None, str | None, Any, Any, int | None]:
    sources_used = sum(
        1 for value in [args.query_name, args.query, args.query_file] if value
    )
    if sources_used != 1:
        raise ValueError("Use exactly one of --query-name, --query, or --query-file.")

    if args.query_name:
        query_definition = get_named_query(config, args.query_name)
        mode = str(query_definition.get("mode") or "find").strip()
        collection = str(query_definition.get("collection") or "").strip() or None
        query_payload = query_definition.get("query")
        projection = query_definition.get("projection")
        sort_spec = query_definition.get("sort")
        limit = query_definition.get("limit")

        if mode not in {"find", "aggregate"}:
            raise ValueError(f"Named query '{args.query_name}' has unsupported mode: {mode}")
        if query_payload is None:
            raise ValueError(f"Named query '{args.query_name}' is missing 'query'.")
        if isinstance(query_payload, str):
            query_payload = parse_query_text(query_payload)
        if limit is not None:
            limit = int(limit)

        return mode, collection, args.query_name, query_payload, projection, limit if limit is not None else None

    raw_query_text = load_json_text(args)
    query_payload = parse_query_text(raw_query_text)
    projection = parse_extended_json(args.projection) if args.projection else None
    return args.mode, args.collection, None, query_payload, projection, args.limit


def get_default_execution(config: dict[str, Any]) -> tuple[str | None, str | None, Any, Any, Any, int | None, Path | None]:
    execution = config.get("execution", {})
    if not isinstance(execution, dict):
        raise ValueError("Config key 'execution' must be a YAML object.")

    mode = str(execution.get("mode") or "").strip() or None
    collection = str(execution.get("collection") or "").strip() or None
    query_text = execution.get("query")
    projection = execution.get("projection")
    sort_spec = execution.get("sort")
    limit = execution.get("limit")
    log_file = execution.get("log_file")

    if isinstance(query_text, str):
        query_payload = parse_query_text(query_text)
    else:
        query_payload = query_text

    if limit is not None:
        limit = int(limit)

    log_path = Path(str(log_file)).resolve() if log_file not in (None, "") else None
    return mode, collection, query_payload, projection, sort_spec, limit, log_path


def get_mongo_settings(config: dict[str, Any]) -> tuple[str, str, str]:
    mongo_config = config.get("mongo", {})
    if not isinstance(mongo_config, dict):
        raise ValueError("Config key 'mongo' must be a YAML object.")

    mongo_uri = str(os.getenv("MONGO_URI") or mongo_config.get("uri") or "").strip()
    mongo_db = str(os.getenv("MONGO_DB") or mongo_config.get("database") or "").strip()
    default_collection = str(mongo_config.get("default_collection") or "").strip()

    if not mongo_uri:
        raise ValueError("Missing MongoDB URI in config: mongo.uri")
    if not mongo_db:
        raise ValueError("Missing MongoDB database in config: mongo.database")

    return mongo_uri, mongo_db, default_collection


def print_documents(documents: list[Any]) -> None:
    for document in documents:
        print(json.dumps(document, default=json_util.default, indent=2))


def emit_log(log_file_path: Path | None, message: str) -> None:
    print(message, flush=True)
    if log_file_path is None:
        return

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    with log_file_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.now().isoformat()}] {message}\n")


def append_log(log_file_path: Path | None, summary: str, documents: list[Any]) -> None:
    if log_file_path is None:
        return

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    with log_file_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.now().isoformat()}] {summary}\n")
        for document in documents:
            handle.write(json.dumps(document, default=json_util.default, indent=2))
            handle.write("\n")
        handle.write("\n")


def summarize_explain_plan(explain_doc: dict[str, Any]) -> dict[str, Any]:
    query_planner = explain_doc.get("queryPlanner", {})
    execution_stats = explain_doc.get("executionStats", {})

    winning_plan = query_planner.get("winningPlan", {})
    stage = winning_plan.get("stage")
    input_stage = winning_plan.get("inputStage", {})
    if stage is None and isinstance(input_stage, dict):
        stage = input_stage.get("stage")

    index_name = winning_plan.get("indexName")
    if index_name is None and isinstance(input_stage, dict):
        index_name = input_stage.get("indexName")

    return {
        "namespace": query_planner.get("namespace"),
        "winning_stage": stage,
        "index_name": index_name,
        "parsed_query": query_planner.get("parsedQuery"),
        "n_returned": execution_stats.get("nReturned"),
        "execution_time_ms": execution_stats.get("executionTimeMillis"),
        "total_keys_examined": execution_stats.get("totalKeysExamined"),
        "total_docs_examined": execution_stats.get("totalDocsExamined"),
    }


def run_explain(
    collection,
    mode: str,
    query_payload: Any,
    projection: Any,
    sort_spec: Any,
    limit: int,
) -> dict[str, Any]:
    if mode == "aggregate":
        explain_command = {
            "aggregate": collection.name,
            "pipeline": query_payload,
            "cursor": {},
        }
        if limit > 0:
            explain_command["cursor"] = {"batchSize": limit}
        return collection.database.command("explain", explain_command, verbosity="executionStats")

    find_command: dict[str, Any] = {
        "find": collection.name,
        "filter": query_payload,
    }
    if projection is not None:
        find_command["projection"] = projection
    if sort_spec is not None:
        find_command["sort"] = sort_spec
    if limit > 0:
        find_command["limit"] = limit
    return collection.database.command("explain", find_command, verbosity="executionStats")


def main() -> None:
    args = parse_args()
    config = load_yaml_file(args.config)
    mongo_uri, mongo_db_name, default_collection = get_mongo_settings(config)

    default_mode, default_exec_collection, default_query_payload, default_projection, default_sort, default_limit, log_file_path = (
        get_default_execution(config)
    )

    sources_used = sum(1 for value in [args.query_name, args.query, args.query_file] if value)
    if sources_used == 0:
        if default_query_payload is None:
            raise ValueError(
                "No query provided. Set execution.query in config.yml or use --query, --query-file, or --query-name."
            )
        resolved_mode = default_mode or "find"
        config_collection = default_exec_collection
        query_name = None
        query_payload = default_query_payload
        projection = default_projection
        config_limit = default_limit
        sort_spec = default_sort
    else:
        resolved_mode, config_collection, query_name, query_payload, projection, config_limit = resolve_query_inputs(
            args,
            config,
        )
        sort_spec = parse_extended_json(args.sort) if args.sort else None

    collection_name = str(args.collection or config_collection or default_collection).strip()
    if not collection_name:
        raise ValueError(
            "Collection not provided. Use --collection or set mongo.default_collection in config.yml."
        )

    if query_name:
        named_query_definition = get_named_query(config, query_name)
        if sort_spec is None:
            sort_spec = named_query_definition.get("sort")
        if args.projection is None and projection is None:
            projection = named_query_definition.get("projection")

    limit = args.limit
    if query_name and args.limit == 20 and config_limit is not None:
        limit = config_limit
    if sources_used == 0 and args.limit == 20 and config_limit is not None:
        limit = config_limit

    if resolved_mode == "aggregate":
        if not isinstance(query_payload, list):
            raise ValueError("Aggregate mode requires a JSON array pipeline.")
    else:
        if not isinstance(query_payload, dict):
            raise ValueError("Find mode requires a JSON object filter.")
        if sort_spec is not None and not isinstance(sort_spec, dict):
            raise ValueError("--sort must be a JSON object, for example: {\"usage_start_time\": -1}")

    emit_log(log_file_path, f"Starting Mongo query execution")
    emit_log(log_file_path, f"Database: {mongo_db_name}")
    emit_log(log_file_path, f"Collection: {collection_name}")
    emit_log(log_file_path, f"Mode: {resolved_mode}")
    emit_log(log_file_path, f"Limit: {limit}")
    emit_log(log_file_path, "Query payload:")
    emit_log(log_file_path, json.dumps(query_payload, default=json_util.default, indent=2))
    if projection is not None:
        emit_log(log_file_path, "Projection:")
        emit_log(log_file_path, json.dumps(projection, default=json_util.default, indent=2))
    if sort_spec is not None:
        emit_log(log_file_path, "Sort:")
        emit_log(log_file_path, json.dumps(sort_spec, default=json_util.default, indent=2))

    try:
        with MongoClient(mongo_uri) as client:
            emit_log(log_file_path, "Connected to MongoDB. Running EXPLAIN...")
            collection = client[mongo_db_name][collection_name]
            explain_doc = run_explain(
                collection=collection,
                mode=resolved_mode,
                query_payload=query_payload,
                projection=projection,
                sort_spec=sort_spec,
                limit=limit,
            )
            explain_summary = summarize_explain_plan(explain_doc)
            emit_log(log_file_path, "EXPLAIN summary:")
            emit_log(log_file_path, json.dumps(explain_summary, default=json_util.default, indent=2))

            emit_log(log_file_path, "Executing query...")
            if resolved_mode == "aggregate":
                cursor = collection.aggregate(query_payload)
                documents = list(cursor) if limit == 0 else list(cursor.limit(limit))
            else:
                cursor = collection.find(query_payload, projection)
                if sort_spec is not None:
                    cursor = cursor.sort(list(sort_spec.items()))
                if limit > 0:
                    cursor = cursor.limit(limit)
                documents = list(cursor)
    except Exception as exc:
        emit_log(log_file_path, f"Execution failed: {exc}")
        emit_log(log_file_path, traceback.format_exc())
        raise

    summary = f"database={mongo_db_name} collection={collection_name} mode={resolved_mode} returned={len(documents)}"
    emit_log(log_file_path, "Query execution finished.")
    emit_log(log_file_path, summary)
    if not documents:
        emit_log(log_file_path, "No documents matched the query.")
    print_documents(documents)
    append_log(log_file_path, summary, documents)


if __name__ == "__main__":
    main()
