import argparse
import re
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")
PREFERRED_SECTION_PATTERN = re.compile(
    r"(?m)^--\s*QUERY:\s*(\d+)\s*\|\s*(.+?)\s*$"
)
LEGACY_SECTION_PATTERN = re.compile(
    r"/\*\s*=+\s*(\d+)\.\s*(.*?)\s*=+\s*\*/",
    re.DOTALL,
)
START_DATE_PATTERN = re.compile(
    r"(t\.req_time\s*>=\s*)'[^']+'",
    re.IGNORECASE,
)
END_DATE_PATTERN = re.compile(
    r"(t\.req_time\s*<\s*)'[^']+'",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split queries.sql into numbered SQL files with date variables.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def get_report_config(config: dict[str, Any], config_path: Path) -> dict[str, Path]:
    report_config = config.get("report_generation", {})
    if not isinstance(report_config, dict):
        raise ValueError("Config key 'report_generation' must be a YAML object.")

    base_dir = config_path.resolve().parent
    source_queries_file = str(report_config.get("source_queries_file") or "queries.sql")
    split_queries_dir = str(report_config.get("split_queries_dir") or "generated-queries")

    return {
        "source_queries_file": resolve_path(base_dir, source_queries_file),
        "split_queries_dir": resolve_path(base_dir, split_queries_dir),
    }


def replace_date_literals(query_text: str) -> str:
    updated = START_DATE_PATTERN.sub(r"\1'{{start_date}}'", query_text)
    updated = END_DATE_PATTERN.sub(r"\1'{{end_date_exclusive}}'", updated)
    return updated


def extract_numbered_queries(source_text: str) -> list[tuple[int, str, str]]:
    matches = list(PREFERRED_SECTION_PATTERN.finditer(source_text))
    if not matches:
        matches = list(LEGACY_SECTION_PATTERN.finditer(source_text))
    numbered_queries: list[tuple[int, str, str]] = []

    for index, match in enumerate(matches):
        query_number = int(match.group(1))
        title = " ".join(match.group(2).split())
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        query_body = source_text[body_start:body_end].strip()
        if not query_body:
            continue
        numbered_queries.append((query_number, title, query_body))

    if not numbered_queries:
        raise ValueError(
            "No numbered queries were found in the source SQL file. Prefer '-- QUERY: <number> | <title>' section markers."
        )

    return numbered_queries


def write_queries(numbered_queries: list[tuple[int, str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for existing in output_dir.glob("*.sql"):
        existing.unlink()

    for query_number, title, query_body in numbered_queries:
        output_path = output_dir / f"{query_number}.sql"
        normalized_query = replace_date_literals(query_body).strip()
        rendered = f"-- Query {query_number}: {title}\n\n{normalized_query}\n"
        output_path.write_text(rendered, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_config(str(config_path))
    report_config = get_report_config(config, config_path)

    source_queries_file = report_config["source_queries_file"]
    split_queries_dir = report_config["split_queries_dir"]

    if not source_queries_file.exists():
        raise FileNotFoundError(f"Source SQL file not found: {source_queries_file}")

    source_text = source_queries_file.read_text(encoding="utf-8")
    numbered_queries = extract_numbered_queries(source_text)
    write_queries(numbered_queries, split_queries_dir)

    print(f"Split {len(numbered_queries)} queries into: {split_queries_dir}")


if __name__ == "__main__":
    main()
