from __future__ import annotations

import re
from dataclasses import dataclass

from .config_loader import AppConfig, QueryDefinition


VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


@dataclass(frozen=True)
class RenderedQuery:
    query_id: str
    query_file: str
    rendered_query: str


def build_replacements(config: AppConfig) -> dict[str, str]:
    replacements: dict[str, str] = {}
    replacements.update(config.collections)
    replacements.update(config.variables)

    if config.report_generation.default_collection:
        replacements.setdefault("default_collection", config.report_generation.default_collection)

    return replacements


def render_query_text(query_text: str, replacements: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        if variable_name not in replacements:
            raise ValueError(f"Missing query placeholder '{variable_name}' in config variables/collections.")
        return replacements[variable_name]

    return VARIABLE_PATTERN.sub(replace, query_text)


def render_query_definition(query_definition: QueryDefinition, replacements: dict[str, str]) -> RenderedQuery:
    query_text = query_definition.file.read_text(encoding="utf-8")
    rendered_query = render_query_text(query_text, replacements)
    return RenderedQuery(
        query_id=query_definition.query_id,
        query_file=str(query_definition.file),
        rendered_query=rendered_query,
    )
