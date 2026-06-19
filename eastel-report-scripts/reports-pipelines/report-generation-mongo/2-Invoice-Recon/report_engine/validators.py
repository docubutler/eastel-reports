from __future__ import annotations

from .config_loader import AppConfig
from .daily_execution import parse_utc_datetime
from .excel_processor import WorkbookReferences


def validate_config(config: AppConfig) -> None:
    if not config.mongo.uri:
        raise ValueError("Missing MongoDB setting: mongo.uri")
    if not config.mongo.database:
        raise ValueError("Missing MongoDB setting: mongo.database")
    if not config.report_generation.queries_dir.exists():
        raise FileNotFoundError(f"Queries directory not found: {config.report_generation.queries_dir}")
    if not config.report_generation.template_xlsx.exists():
        raise FileNotFoundError(f"Excel template not found: {config.report_generation.template_xlsx}")

    for query_id, query_definition in config.queries.items():
        if query_definition.output not in {"scalar", "fixed_table"}:
            raise ValueError(
                f"Unsupported output '{query_definition.output}' for query {query_id}. "
                "Expected 'scalar' or 'fixed_table'."
            )
        if not query_definition.file.exists():
            raise FileNotFoundError(f"Configured query file for {query_id} not found: {query_definition.file}")
        if query_definition.output == "fixed_table" and not query_definition.columns:
            raise ValueError(f"Query {query_id} is fixed_table but has no columns configured.")
        if query_definition.execute_day_wise:
            start_date = config.variables.get("start_date")
            end_date = config.variables.get("end_date")
            if not start_date or not end_date:
                raise ValueError(
                    f"Query {query_id} has execute_day_wise=true but variables.start_date/end_date are missing."
                )
            parse_utc_datetime(start_date)
            parse_utc_datetime(end_date)


def validate_workbook_references(config: AppConfig, references: WorkbookReferences) -> None:
    for query_id in references.query_ids:
        if query_id not in config.queries:
            raise ValueError(f"Workbook references query {query_id}, but it is missing from config.yml.")

    for anchor in references.table_anchors:
        query_definition = config.queries[anchor.query_id]
        if query_definition.output != "fixed_table":
            raise ValueError(
                f"Workbook anchor {anchor.anchor_text} on sheet '{anchor.sheet_name}' points to {anchor.query_id}, "
                f"but config defines output='{query_definition.output}'."
            )

    for placeholder in references.scalar_placeholders:
        query_definition = config.queries[placeholder.query_id]
        if query_definition.output != "scalar":
            raise ValueError(
                f"Workbook placeholder {placeholder.raw_value} on sheet '{placeholder.sheet_name}' uses "
                f"{placeholder.query_id}, but config defines output='{query_definition.output}'."
            )
