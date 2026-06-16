from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bson import json_util

from .config_loader import MongoConfig, QueryDefinition


LOGGER = logging.getLogger(__name__)

ScalarResult = dict[str, Any]
TableResult = list[dict[str, Any]]
QueryPayload = ScalarResult | TableResult


@dataclass(frozen=True)
class QueryExecutionResult:
    query_id: str
    payload: QueryPayload
    duration_seconds: float


def _resolve_mongosh_path() -> str:
    mongosh_path = shutil.which("mongosh")
    if mongosh_path:
        return mongosh_path
    raise FileNotFoundError("mongosh was not found on PATH. Install MongoDB Shell or add it to PATH.")


def _build_execution_script(rendered_query: str, mongo_database: str) -> str:
    query_text = rendered_query.strip()
    query_start = query_text.rfind("db.")
    if query_start < 0:
        raise ValueError("Rendered query does not contain a Mongo 'db.<collection>.aggregate(...)' statement.")

    prelude = query_text[:query_start].rstrip()
    statement = query_text[query_start:].strip()
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()

    script_lines = [
        f'db = db.getSiblingDB({json.dumps(mongo_database)});',
        "const __runQuery = () => {",
    ]
    if prelude:
        script_lines.append(prelude)
    script_lines.append(f"return {statement};")
    script_lines.append("};")
    script_lines.append("const __cursor = __runQuery();")
    script_lines.append(
        "const __result = (__cursor && typeof __cursor.toArray === 'function') ? __cursor.toArray() : __cursor;"
    )
    script_lines.append("print(EJSON.stringify(__result, null, 2));")
    return "\n".join(script_lines)


def _run_mongosh_script(script_text: str, mongo_config: MongoConfig) -> QueryPayload:
    mongosh_path = _resolve_mongosh_path()

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(script_text)
        script_path = Path(handle.name)

    try:
        command = [
            mongosh_path,
            mongo_config.uri,
            "--quiet",
            "--file",
            str(script_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)

    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr)"
        stdout = result.stdout.strip() or "(no stdout)"
        raise RuntimeError(
            "mongosh query execution failed.\n"
            f"stderr:\n{stderr}\n"
            f"stdout:\n{stdout}"
        )

    raw_output = result.stdout.strip()
    if not raw_output:
        raise RuntimeError("mongosh completed successfully but returned no output.")

    try:
        payload = json_util.loads(raw_output)
    except Exception as exc:
        raise ValueError(f"Failed to parse mongosh JSON output: {raw_output}") from exc

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Unsupported mongosh payload type: {type(payload)!r}")


def execute_query(
    query_id: str,
    rendered_query: str,
    query_definition: QueryDefinition,
    mongo_config: MongoConfig,
) -> QueryExecutionResult:
    started_at = time.perf_counter()
    LOGGER.info("Executing query %s from %s", query_id, query_definition.file.name)

    script_text = _build_execution_script(
        rendered_query=rendered_query,
        mongo_database=mongo_config.database,
    )
    payload = _run_mongosh_script(script_text=script_text, mongo_config=mongo_config)

    if query_definition.output == "scalar":
        if isinstance(payload, list):
            if len(payload) == 0:
                payload = {}
            elif len(payload) == 1 and isinstance(payload[0], dict):
                payload = payload[0]
            else:
                raise ValueError(f"Scalar query {query_id} returned {len(payload)} rows.")
        if not isinstance(payload, dict):
            raise ValueError(f"Scalar query {query_id} returned a non-dict payload.")
    elif query_definition.output == "fixed_table":
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise ValueError(f"Table query {query_id} returned a non-list payload.")
    else:
        raise ValueError(
            f"Unsupported query output '{query_definition.output}' for {query_id}. "
            "Expected 'scalar' or 'fixed_table'."
        )

    duration_seconds = time.perf_counter() - started_at
    LOGGER.info("Completed query %s in %.3fs", query_id, duration_seconds)
    return QueryExecutionResult(
        query_id=query_id,
        payload=payload,
        duration_seconds=duration_seconds,
    )
