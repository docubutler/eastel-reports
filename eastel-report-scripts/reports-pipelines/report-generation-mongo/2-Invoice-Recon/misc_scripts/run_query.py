from __future__ import annotations

"""
Standalone single-query runner for the 2-Invoice-Recon Mongo report engine.

What this script does:
- loads config.yml
- resolves the provided query file to a configured query id such as Q013
- substitutes config variables and collection placeholders inside the query text
- executes the rendered Mongo query through mongosh
- prints the final result as JSON to stdout

What this script does not do:
- it does not update the report output Excel workbook
- it does not replace placeholders in the template/output report
- it does not write the "actual queries used" workbook

This is mainly for query development and debugging when you want to test one
query in isolation without running the full report pipeline.

Typical usage from repo root:
    py reports-pipelines/report-generation-mongo/2-Invoice-Recon/report_engine/run_query.py ^
       reports-pipelines/report-generation-mongo/2-Invoice-Recon/queries/13.js

Typical usage from inside the 2-Invoice-Recon folder:
    py .\\report_engine\\run_query.py .\\queries\\13.js

Optional:
    --show-rendered-query
        prints the fully substituted Mongo query before the final JSON result

Day-wise behavior:
- if the query has execute_day_wise: true in config.yml, the script follows the
  same day-slicing and resume logic as the main report engine
- successful day results are persisted into the daily checkpoint workbook
- reruns reuse saved successful day slices instead of recalculating them
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from bson import json_util

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
    from report_engine.main import DEFAULT_CONFIG_PATH, configure_logging
    from report_engine.query_executor import QueryExecutionResult, execute_query
    from report_engine.query_renderer import build_replacements, render_query_definition
    from report_engine.validators import validate_config
else:
    from .config_loader import AppConfig, QueryDefinition, load_config
    from .daily_execution import (
        DailyCheckpointStore,
        aggregate_scalar_payloads,
        aggregate_table_payloads,
        iter_day_windows,
        summarize_payload,
    )
    from .main import DEFAULT_CONFIG_PATH, configure_logging
    from .query_executor import QueryExecutionResult, execute_query
    from .query_renderer import build_replacements, render_query_definition
    from .validators import validate_config


LOGGER = logging.getLogger("invoice_recon_query_runner")


def parse_args() -> argparse.Namespace:
    """Parse CLI options for the standalone query runner."""
    parser = argparse.ArgumentParser(description="Render and execute one Mongo report query from config.yml.")
    parser.add_argument(
        "query_file",
        help="Path to a query file such as queries/13.js or 13.js",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.yml",
    )
    parser.add_argument(
        "--show-rendered-query",
        action="store_true",
        help="Print the fully rendered query before executing it.",
    )
    return parser.parse_args()


def _resolve_query_definition(config: AppConfig, query_file_arg: str) -> QueryDefinition:
    """
    Resolve a user-provided query file path to the matching query definition from config.yml.

    The runner intentionally only supports files that are already registered in
    config.yml. That keeps execution behavior aligned with the main report
    engine, including output type and day-wise settings.

    Accepted path styles:
    - absolute path
    - repo-root relative path
    - path relative to the config folder
    - path relative to report_generation.queries_dir
    """
    query_path = Path(query_file_arg)
    if not query_path.is_absolute():
        candidate_paths = [
            query_path.resolve(),
            (config.base_dir / query_path).resolve(),
            (config.report_generation.queries_dir / query_path).resolve(),
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                query_path = candidate
                break
        else:
            query_path = candidate_paths[0]

    for query_definition in config.queries.values():
        if query_definition.file.resolve() == query_path.resolve():
            return query_definition

    raise ValueError(
        f"Query file is not mapped in config.yml: {query_path}. "
        "Pass a file that is already defined under the 'queries' section."
    )


def _execute_single_query(config: AppConfig, query_definition: QueryDefinition) -> tuple[QueryExecutionResult, list[str]]:
    """Render and execute one query exactly once for the full configured date range."""
    replacements = build_replacements(config)
    rendered_query = render_query_definition(query_definition, replacements)
    result = execute_query(
        query_id=query_definition.query_id,
        rendered_query=rendered_query.rendered_query,
        query_definition=query_definition,
        mongo_config=config.mongo,
    )
    return result, [rendered_query.rendered_query]


def _execute_day_wise_query(config: AppConfig, query_definition: QueryDefinition) -> tuple[QueryExecutionResult, list[str]]:
    """
    Execute one configured query day by day and aggregate the results.

    Sequence:
    1. Split the configured date range into 1-day windows.
    2. Check the daily checkpoint workbook for already completed days.
    3. Reuse saved day results where available.
    4. Execute only missing days.
    5. Save each successful day immediately.
    6. Aggregate all day results into one final payload.

    The returned list of rendered queries contains one entry per executed or
    reused day slice. The final payload is what would conceptually represent the
    whole requested period for this single query.
    """
    LOGGER.info("Day-wise execution enabled for query %s", query_definition.query_id)
    replacements = build_replacements(config)
    day_windows = iter_day_windows(
        start_date_text=config.variables["start_date"],
        end_date_text=config.variables["end_date"],
    )
    checkpoint_store = DailyCheckpointStore(config.report_generation.daily_checkpoint_xlsx)
    successful_records = checkpoint_store.load_successful_records(query_definition.query_id)

    day_payloads = []
    rendered_queries: list[str] = []
    total_duration = 0.0

    for day_window in day_windows:
        # Resume behavior: if this day already completed successfully in an
        # earlier run, do not execute it again.
        cached_record = successful_records.get(day_window.day_key)
        if cached_record is not None and cached_record.payload is not None:
            LOGGER.info(
                "Reusing saved day result | query=%s | day=%s | summary=%s",
                query_definition.query_id,
                day_window.day_key,
                summarize_payload(cached_record.payload),
            )
            day_payloads.append(cached_record.payload)
            rendered_queries.append(cached_record.rendered_query)
            total_duration += cached_record.duration_seconds
            continue

        # For a day-wise slice, only start_date/end_date change. Collection
        # placeholders and any other variables still come from config.yml.
        day_replacements = dict(replacements)
        day_replacements["start_date"] = day_window.start_iso
        day_replacements["end_date"] = day_window.end_iso
        rendered_query = render_query_definition(query_definition, day_replacements)
        rendered_queries.append(rendered_query.rendered_query)

        LOGGER.info(
            "Executing day slice | query=%s | day=%s | start=%s | end=%s",
            query_definition.query_id,
            day_window.day_key,
            day_window.start_iso,
            day_window.end_iso,
        )
        result = execute_query(
            query_id=query_definition.query_id,
            rendered_query=rendered_query.rendered_query,
            query_definition=query_definition,
            mongo_config=config.mongo,
        )
        checkpoint_store.save_success(
            query_id=query_definition.query_id,
            day_key=day_window.day_key,
            payload=result.payload,
            rendered_query=rendered_query.rendered_query,
            duration_seconds=result.duration_seconds,
        )
        LOGGER.info(
            "Saved day checkpoint | query=%s | day=%s | summary=%s",
            query_definition.query_id,
            day_window.day_key,
            summarize_payload(result.payload),
        )
        day_payloads.append(result.payload)
        total_duration += result.duration_seconds

    # Current generic aggregation rule:
    # - scalar payloads: sum numeric fields
    # - table payloads: treat non-numeric configured columns as grouping keys
    #   and numeric configured columns as measures to sum
    if query_definition.output == "scalar":
        payload = aggregate_scalar_payloads(payload for payload in day_payloads if isinstance(payload, dict))
    else:
        payload = aggregate_table_payloads(
            (payload for payload in day_payloads if isinstance(payload, list)),
            query_definition.columns,
        )

    return (
        QueryExecutionResult(
            query_id=query_definition.query_id,
            payload=payload,
            duration_seconds=total_duration,
        ),
        rendered_queries,
    )


def main() -> None:
    """
    Run the standalone query executor.

    Expected outputs:
    - logs on stdout, and optionally to the configured log file
    - final JSON result on stdout
    - if execute_day_wise is enabled, checkpoints written to the configured
      daily checkpoint workbook
    """
    args = parse_args()
    config = load_config(args.config)
    configure_logging(config)
    validate_config(config)

    query_definition = _resolve_query_definition(config, args.query_file)
    LOGGER.info("Resolved query | id=%s | file=%s", query_definition.query_id, query_definition.file)

    if query_definition.execute_day_wise:
        result, rendered_queries = _execute_day_wise_query(config, query_definition)
    else:
        result, rendered_queries = _execute_single_query(config, query_definition)

    # For day-wise queries this shows the last day-slice query, not a synthetic
    # "combined" query, because the combined result is an aggregation performed
    # in Python after the per-day executions finish.
    if args.show_rendered_query:
        print("=== Rendered Query ===")
        print(rendered_queries[-1])
        print()

    # The JSON printed here is the primary output of this helper script.
    # It is meant to be easy to inspect manually or pipe into a file if needed.
    print(
        json.dumps(
            {
                "query_id": query_definition.query_id,
                "query_file": str(query_definition.file),
                "output": query_definition.output,
                "execute_day_wise": query_definition.execute_day_wise,
                "duration_seconds": round(result.duration_seconds, 3),
                "result": result.payload,
            },
            indent=2,
            default=json_util.default,
        )
    )


if __name__ == "__main__":
    main()
