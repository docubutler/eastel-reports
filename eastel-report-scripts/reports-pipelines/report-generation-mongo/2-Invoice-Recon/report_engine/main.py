from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parent.parent))
    from report_engine.config_loader import AppConfig, QueryDefinition, load_config
    from report_engine.daily_execution import (
        DailyCheckpointStore,
        aggregate_scalar_payloads,
        aggregate_table_payloads,
        iter_day_windows,
        summarize_payload,
    )
    from report_engine.excel_processor import (
        apply_scalar_query_result,
        apply_table_query_result,
        scan_workbook_references,
        write_actual_queries_workbook,
    )
    from report_engine.query_executor import QueryExecutionResult, execute_query
    from report_engine.query_renderer import RenderedQuery, build_replacements, render_query_definition
    from report_engine.validators import validate_config, validate_workbook_references
else:
    from .config_loader import AppConfig, QueryDefinition, load_config
    from .daily_execution import (
        DailyCheckpointStore,
        aggregate_scalar_payloads,
        aggregate_table_payloads,
        iter_day_windows,
        summarize_payload,
    )
    from .excel_processor import (
        apply_scalar_query_result,
        apply_table_query_result,
        scan_workbook_references,
        write_actual_queries_workbook,
    )
    from .query_executor import QueryExecutionResult, execute_query
    from .query_renderer import RenderedQuery, build_replacements, render_query_definition
    from .validators import validate_config, validate_workbook_references


LOGGER = logging.getLogger("invoice_recon_report_engine")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yml"


@dataclass
class QueryCacheItem:
    rendered_queries: list[RenderedQuery]
    execution_result: QueryExecutionResult


@dataclass(frozen=True)
class QueryFailure:
    query_id: str
    error_message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Mongo invoice reconciliation Excel report.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.yml",
    )
    return parser.parse_args()


def configure_logging(config: AppConfig) -> Path | None:
    log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    effective_log_path: Path | None = None

    if config.logging.file_path is not None:
        candidate = config.logging.file_path
        if not candidate.is_absolute():
            candidate = (config.base_dir / candidate).resolve()
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            log_handlers.append(logging.FileHandler(candidate, encoding="utf-8"))
            effective_log_path = candidate
        except OSError:
            fallback = (config.base_dir / "report-generation.log").resolve()
            fallback.parent.mkdir(parents=True, exist_ok=True)
            log_handlers.append(logging.FileHandler(fallback, encoding="utf-8"))
            effective_log_path = fallback

    logging.basicConfig(
        level=getattr(logging, config.logging.level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=log_handlers,
        force=True,
    )
    return effective_log_path


def _normalize_scalar_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        key_text = str(key)
        normalized[key_text] = value
        normalized[key_text.lower()] = value
    return normalized


def _normalize_table_payload(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(key): value for key, value in row.items()} for row in payload]


def _execute_and_cache_query(
    config: AppConfig,
    query_definition: QueryDefinition,
    replacements: dict[str, str],
    cache: dict[str, QueryCacheItem],
    daily_checkpoint_store: DailyCheckpointStore,
) -> QueryCacheItem:
    if query_definition.query_id in cache:
        LOGGER.info("Using cached result for query %s", query_definition.query_id)
        return cache[query_definition.query_id]

    if query_definition.execute_day_wise:
        LOGGER.info("Day-wise execution enabled for query %s", query_definition.query_id)
        day_windows = iter_day_windows(
            start_date_text=config.variables["start_date"],
            end_date_text=config.variables["end_date"],
        )
        successful_records = daily_checkpoint_store.load_successful_records(query_definition.query_id)
        day_payloads: list[Any] = []
        rendered_queries: list[RenderedQuery] = []
        started_at = time.perf_counter()

        for day_window in day_windows:
            cached_record = successful_records.get(day_window.day_key)
            if cached_record is not None:
                LOGGER.info(
                    "Reusing saved day-wise result | query=%s | day=%s | summary=%s",
                    query_definition.query_id,
                    day_window.day_key,
                    summarize_payload(cached_record.payload if cached_record.payload is not None else {}),
                )
                if cached_record.payload is not None:
                    day_payloads.append(cached_record.payload)
                rendered_queries.append(
                    RenderedQuery(
                        query_id=f"{query_definition.query_id} [{day_window.day_key}]",
                        query_file=str(query_definition.file),
                        rendered_query=cached_record.rendered_query,
                    )
                )
                continue

            day_replacements = dict(replacements)
            day_replacements["start_date"] = day_window.start_iso
            day_replacements["end_date"] = day_window.end_iso
            rendered_query = render_query_definition(query_definition, day_replacements)

            LOGGER.info(
                "Executing day-wise slice | query=%s | day=%s | start=%s | end=%s",
                query_definition.query_id,
                day_window.day_key,
                day_window.start_iso,
                day_window.end_iso,
            )
            try:
                execution_result = execute_query(
                    query_id=query_definition.query_id,
                    rendered_query=rendered_query.rendered_query,
                    query_definition=query_definition,
                    mongo_config=config.mongo,
                )
                daily_checkpoint_store.save_success(
                    query_id=query_definition.query_id,
                    day_key=day_window.day_key,
                    payload=execution_result.payload,
                    rendered_query=rendered_query.rendered_query,
                    duration_seconds=execution_result.duration_seconds,
                )
                LOGGER.info(
                    "Saved day-wise checkpoint | query=%s | day=%s | summary=%s",
                    query_definition.query_id,
                    day_window.day_key,
                    summarize_payload(execution_result.payload),
                )
            except Exception as exc:
                daily_checkpoint_store.save_failure(
                    query_id=query_definition.query_id,
                    day_key=day_window.day_key,
                    rendered_query=rendered_query.rendered_query,
                    error_message=str(exc),
                )
                raise

            day_payloads.append(execution_result.payload)
            rendered_queries.append(
                RenderedQuery(
                    query_id=f"{query_definition.query_id} [{day_window.day_key}]",
                    query_file=rendered_query.query_file,
                    rendered_query=rendered_query.rendered_query,
                )
            )

        aggregated_payload: Any
        if query_definition.output == "scalar":
            aggregated_payload = aggregate_scalar_payloads(payload for payload in day_payloads if isinstance(payload, dict))
        else:
            aggregated_payload = aggregate_table_payloads(
                (payload for payload in day_payloads if isinstance(payload, list)),
                query_definition.columns,
            )

        execution_result = QueryExecutionResult(
            query_id=query_definition.query_id,
            payload=aggregated_payload,
            duration_seconds=time.perf_counter() - started_at,
        )
        cache[query_definition.query_id] = QueryCacheItem(
            rendered_queries=rendered_queries,
            execution_result=execution_result,
        )
        LOGGER.info(
            "Completed day-wise aggregation | query=%s | days=%s | summary=%s",
            query_definition.query_id,
            len(day_windows),
            summarize_payload(aggregated_payload),
        )
        return cache[query_definition.query_id]

    rendered_query = render_query_definition(query_definition, replacements)
    execution_result = execute_query(
        query_id=query_definition.query_id,
        rendered_query=rendered_query.rendered_query,
        query_definition=query_definition,
        mongo_config=config.mongo,
    )
    cache[query_definition.query_id] = QueryCacheItem(
        rendered_queries=[rendered_query],
        execution_result=execution_result,
    )
    return cache[query_definition.query_id]


def _ensure_output_workbook(config: AppConfig) -> Path:
    output_path = config.report_generation.output_xlsx
    if not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config.report_generation.template_xlsx, output_path)
        LOGGER.info("Copied template workbook to output path: %s", output_path)
    return output_path


def _apply_query_checkpoint(
    workbook_path: Path,
    query_definition: QueryDefinition,
    payload: Any,
) -> int:
    if query_definition.output == "scalar":
        if not isinstance(payload, dict):
            raise ValueError(f"Query {query_definition.query_id} returned a non-scalar payload.")
        return apply_scalar_query_result(
            workbook_path=workbook_path,
            query_id=query_definition.query_id,
            scalar_result=_normalize_scalar_payload(payload),
        )

    if not isinstance(payload, list):
        raise ValueError(f"Query {query_definition.query_id} returned a non-table payload.")
    return apply_table_query_result(
        workbook_path=workbook_path,
        query_id=query_definition.query_id,
        rows=_normalize_table_payload(payload),
        columns=query_definition.columns,
    )


def run_report(config: AppConfig) -> tuple[Path, Path]:
    started_at = time.perf_counter()
    replacements = build_replacements(config)

    validate_config(config)
    output_workbook_path = _ensure_output_workbook(config)
    workbook_references = scan_workbook_references(output_workbook_path)
    validate_workbook_references(config, workbook_references)

    if not workbook_references.query_ids:
        raise ValueError(
            "Output workbook does not contain any placeholders. "
            "Delete the output file if you want to generate a new file."
        )

    LOGGER.info("Report generation started")
    LOGGER.info("Config path: %s", config.config_path)
    LOGGER.info("Template workbook: %s", config.report_generation.template_xlsx)
    LOGGER.info("Output workbook: %s", output_workbook_path)
    LOGGER.info("Rendered queries workbook: %s", config.report_generation.actual_queries_output_xlsx)
    LOGGER.info("Daily checkpoint workbook: %s", config.report_generation.daily_checkpoint_xlsx)
    LOGGER.info("Mongo database configured: %s", config.mongo.database)
    LOGGER.info(
        "Workbook references | scalar_queries=%s | table_queries=%s | total_unique_queries=%s",
        len(workbook_references.scalar_query_ids),
        len(workbook_references.table_query_ids),
        len(workbook_references.query_ids),
    )

    cache: dict[str, QueryCacheItem] = {}
    rendered_queries: list[tuple[str, str, str]] = []
    failures: list[QueryFailure] = []
    successful_queries: list[str] = []
    daily_checkpoint_store = DailyCheckpointStore(config.report_generation.daily_checkpoint_xlsx)

    for query_id in workbook_references.query_ids:
        query_definition = config.queries[query_id]
        LOGGER.info("Preparing query %s from %s", query_id, query_definition.file)
        try:
            cache_item = _execute_and_cache_query(
                config,
                query_definition,
                replacements,
                cache,
                daily_checkpoint_store,
            )
            rendered_queries.extend(
                (
                    rendered_query.query_id,
                    rendered_query.query_file,
                    rendered_query.rendered_query,
                )
                for rendered_query in cache_item.rendered_queries
            )
            replacement_count = _apply_query_checkpoint(
                workbook_path=output_workbook_path,
                query_definition=query_definition,
                payload=cache_item.execution_result.payload,
            )
            successful_queries.append(query_id)
            LOGGER.info(
                "Saved checkpoint after query %s | replacements=%s | workbook=%s",
                query_id,
                replacement_count,
                output_workbook_path,
            )
        except Exception as exc:
            error_message = str(exc)
            failures.append(QueryFailure(query_id=query_id, error_message=error_message))
            LOGGER.exception("Query %s failed. Leaving placeholders unchanged and continuing.", query_id)

    write_actual_queries_workbook(
        output_path=config.report_generation.actual_queries_output_xlsx,
        rendered_queries=rendered_queries,
    )

    total_duration = time.perf_counter() - started_at
    LOGGER.info("Report workbook checkpoint path: %s", output_workbook_path)
    LOGGER.info("Rendered queries workbook written: %s", config.report_generation.actual_queries_output_xlsx)
    LOGGER.info("Executed queries successfully: %s", len(successful_queries))
    LOGGER.info("Queries failed: %s", len(failures))
    for query_id in successful_queries:
        duration = cache[query_id].execution_result.duration_seconds
        LOGGER.info("Query summary | id=%s | duration=%.3fs", query_id, duration)
    for failure in failures:
        LOGGER.error("Query failure | id=%s | error=%s", failure.query_id, failure.error_message)
    LOGGER.info("Report generation finished in %.3fs", total_duration)
    return output_workbook_path, config.report_generation.actual_queries_output_xlsx


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    log_path = configure_logging(config)
    if log_path is not None:
        LOGGER.info("Log file path: %s", log_path)
    run_report(config)


if __name__ == "__main__":
    main()
