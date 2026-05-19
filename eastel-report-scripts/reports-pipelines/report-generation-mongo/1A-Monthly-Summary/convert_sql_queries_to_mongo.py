import argparse
import re
from pathlib import Path
from typing import Any

import yaml


TITLE_PATTERN = re.compile(r"^\s*--\s*Query\s+(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
CLAUSE_PATTERN = re.compile(
    r"SELECT\s+(?P<select>.+?)\s+FROM\s+(?P<from>.+?)(?:\s+WHERE\s+(?P<where>.+?))?(?:\s+GROUP\s+BY\s+(?P<group_by>.+?))?\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER_REPLACEMENTS = {
    "{{request_log_table}}": "{{request_log}}",
    "{{smsc_cdr_table}}": "{{smsc_cdr}}",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert constrained PostgreSQL report queries into Mongo aggregation YAML files.",
    )
    parser.add_argument(
        "--source-dir",
        default="generated-queries",
        help="Directory containing .sql query files.",
    )
    parser.add_argument(
        "--output-dir",
        default="queries",
        help="Directory to write .yml Mongo query files.",
    )
    return parser.parse_args()


def split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == "'":
            current.append(char)
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                current.append(text[i + 1])
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == separator and depth == 0:
                parts.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(char)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def strip_sql_comments(sql_text: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", sql_text, flags=re.DOTALL)
    lines = []
    for line in without_block_comments.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def strip_outer_parentheses(text: str) -> str:
    candidate = text.strip()
    while candidate.startswith("(") and candidate.endswith(")"):
        depth = 0
        balanced = True
        for index, char in enumerate(candidate):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(candidate) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        candidate = candidate[1:-1].strip()
    return candidate


def normalize_identifier(identifier: str) -> str:
    value = identifier.strip()
    if "." in value:
        value = value.split(".")[-1]
    return value.strip('"')


def parse_number(text: str) -> int | float:
    return float(text) if "." in text else int(text)


def parse_literal(token: str) -> Any:
    token = token.strip()
    if token.startswith("'") and token.endswith("'"):
        inner = token[1:-1]
        if inner == "{{start_date}}":
            return {"$dateVar": "start_date"}
        if inner == "{{end_date_exclusive}}":
            return {"$dateVar": "end_date_exclusive"}
        return inner
    if NUMBER_PATTERN.match(token):
        return parse_number(token)
    return token


def replace_boundary_dates(where_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        operator = match.group(1)
        literal = match.group(2)
        if not DATE_PATTERN.match(literal):
            return match.group(0)
        if operator == ">=":
            return ">='{{start_date}}'"
        if operator == "<":
            return "<'{{end_date_exclusive}}'"
        return match.group(0)

    return re.sub(
        r"(>=|<)\s*'(\d{4}-\d{2}-\d{2})'",
        replace,
        where_text,
    )


def sql_like_to_regex(pattern: str) -> str:
    regex = []
    for char in pattern:
        if char == "%":
            regex.append(".*")
        elif char == "_":
            regex.append(".")
        else:
            regex.append(re.escape(char))
    return "^" + "".join(regex) + "$"


def tokenize(expression: str) -> list[str]:
    token_pattern = re.compile(
        r"""
        \s*(
            \{\{[A-Za-z0-9_]+\}\} |
            '(?:''|[^'])*' |
            >= | <= | <> | = | < | > |
            \( | \) | , |
            [A-Za-z_][A-Za-z0-9_\.]* |
            \d+(?:\.\d+)?
        )
        """,
        re.VERBOSE,
    )
    tokens: list[str] = []
    index = 0
    while index < len(expression):
        match = token_pattern.match(expression, index)
        if not match:
            raise ValueError(f"Unsupported WHERE syntax near: {expression[index:index + 40]!r}")
        tokens.append(match.group(1))
        index = match.end()
    return tokens


class WhereParser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0

    def peek(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def consume(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of WHERE clause.")
        if expected is not None and token.upper() != expected.upper():
            raise ValueError(f"Expected token {expected!r}, got {token!r}")
        self.position += 1
        return token

    def parse(self) -> dict[str, Any]:
        parsed = self.parse_or()
        if self.peek() is not None:
            raise ValueError(f"Unexpected trailing token: {self.peek()!r}")
        return parsed

    def parse_or(self) -> dict[str, Any]:
        terms = [self.parse_and()]
        while self.peek() and self.peek().upper() == "OR":
            self.consume("OR")
            terms.append(self.parse_and())
        if len(terms) == 1:
            return terms[0]
        return {"$or": terms}

    def parse_and(self) -> dict[str, Any]:
        terms = [self.parse_term()]
        while self.peek() and self.peek().upper() == "AND":
            self.consume("AND")
            terms.append(self.parse_term())
        if len(terms) == 1:
            return terms[0]
        return {"$and": terms}

    def parse_term(self) -> dict[str, Any]:
        if self.peek() == "(":
            self.consume("(")
            expression = self.parse_or()
            self.consume(")")
            return expression
        return self.parse_condition()

    def parse_condition(self) -> dict[str, Any]:
        token = self.consume()
        if token.upper() == "LENGTH":
            self.consume("(")
            field = normalize_identifier(self.consume())
            self.consume(")")
            operator = self.consume()
            value = parse_literal(self.consume())
            return {
                "$expr": {
                    mongo_operator(operator): [
                        {"$strLenCP": {"$ifNull": [f"${field}", ""]}},
                        value,
                    ]
                }
            }

        field = normalize_identifier(token)
        next_token = self.consume()
        if next_token.upper() == "NOT":
            keyword = self.consume()
            if keyword.upper() == "IN":
                return {field: {"$nin": self.parse_value_list()}}
            if keyword.upper() == "LIKE":
                pattern = parse_like_pattern(self)
                return {field: {"$not": {"$regex": sql_like_to_regex(pattern)}}}
            raise ValueError(f"Unsupported NOT expression: {keyword}")

        if next_token.upper() == "IN":
            return {field: {"$in": self.parse_value_list()}}
        if next_token.upper() == "LIKE":
            pattern = parse_like_pattern(self)
            return {field: {"$regex": sql_like_to_regex(pattern)}}

        value = parse_literal(self.consume())
        if next_token == "=":
            return {field: value}
        return {field: {mongo_operator(next_token): value}}

    def parse_value_list(self) -> list[Any]:
        values: list[Any] = []
        self.consume("(")
        while True:
            values.append(parse_literal(self.consume()))
            if self.peek() == ",":
                self.consume(",")
                continue
            break
        self.consume(")")
        return values


def mongo_operator(operator: str) -> str:
    return {
        ">": "$gt",
        ">=": "$gte",
        "<": "$lt",
        "<=": "$lte",
        "<>": "$ne",
    }[operator]


def parse_where_clause(where_text: str) -> dict[str, Any]:
    return WhereParser(tokenize(where_text)).parse()


def parse_like_pattern(parser: "WhereParser") -> str:
    if parser.peek() == "(":
        parser.consume("(")
        token = parser.consume()
        parser.consume(")")
    else:
        token = parser.consume()
    pattern = parse_literal(token)
    if not isinstance(pattern, str):
        raise ValueError("LIKE expects a string literal.")
    return pattern


def parse_mongo_expression(expression: str) -> Any:
    candidate = strip_outer_parentheses(expression)
    divide_parts = split_top_level(candidate, "/")
    if len(divide_parts) == 2:
        return {
            "$divide": [
                parse_mongo_expression(divide_parts[0]),
                parse_mongo_expression(divide_parts[1]),
            ]
        }

    candidate = candidate.strip()
    if NUMBER_PATTERN.match(candidate):
        return parse_number(candidate)
    return f"${normalize_identifier(candidate)}"


def parse_select_item(
    item: str,
    group_stage: dict[str, Any],
    project_stage: dict[str, Any],
    group_fields: list[str],
) -> None:
    alias_match = re.match(r"(?is)(.+?)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item)
    if alias_match:
        expression = alias_match.group(1).strip()
        alias = alias_match.group(2).strip()
    else:
        expression = item.strip()
        alias = normalize_identifier(expression)

    count_match = re.fullmatch(r"(?is)COUNT\s*\(\s*\*\s*\)", expression)
    if count_match:
        group_stage[alias] = {"$sum": 1}
        project_stage[alias] = 1
        return

    sum_round_match = re.fullmatch(r"(?is)SUM\s*\(\s*ROUND\s*\(\s*(.+?)\s*,\s*(\d+)\s*\)\s*\)", expression)
    if sum_round_match:
        inner_expression = sum_round_match.group(1).strip()
        scale = int(sum_round_match.group(2))
        group_stage[alias] = {
            "$sum": {
                "$round": [
                    parse_mongo_expression(inner_expression),
                    scale,
                ]
            }
        }
        project_stage[alias] = 1
        return

    round_sum_divide_match = re.fullmatch(
        r"(?is)ROUND\s*\(\s*SUM\s*\(\s*(.+?)\s*\)\s*/\s*(\d+(?:\.\d+)?)\s*,\s*(\d+)\s*\)",
        expression,
    )
    if round_sum_divide_match:
        inner_expression = round_sum_divide_match.group(1).strip()
        divisor = parse_number(round_sum_divide_match.group(2))
        scale = int(round_sum_divide_match.group(3))
        raw_alias = f"__raw_{alias}"
        group_stage[raw_alias] = {"$sum": parse_mongo_expression(inner_expression)}
        project_stage[alias] = {
            "$round": [
                {"$divide": [f"${raw_alias}", divisor]},
                scale,
            ]
        }
        return

    round_sum_match = re.fullmatch(r"(?is)ROUND\s*\(\s*SUM\s*\(\s*(.+?)\s*\)\s*,\s*(\d+)\s*\)", expression)
    if round_sum_match:
        inner_expression = round_sum_match.group(1).strip()
        scale = int(round_sum_match.group(2))
        raw_alias = f"__raw_{alias}"
        group_stage[raw_alias] = {"$sum": parse_mongo_expression(inner_expression)}
        project_stage[alias] = {"$round": [f"${raw_alias}", scale]}
        return

    sum_match = re.fullmatch(r"(?is)SUM\s*\(\s*(.+?)\s*\)", expression)
    if sum_match:
        group_stage[alias] = {"$sum": parse_mongo_expression(sum_match.group(1).strip())}
        project_stage[alias] = 1
        return

    field_name = normalize_identifier(expression)
    if field_name in group_fields:
        project_stage[alias] = f"$_id.{field_name}" if len(group_fields) > 1 else f"$_id.{field_name}"
        return

    raise ValueError(f"Unsupported SELECT expression: {item}")


def parse_group_by(group_by_text: str | None) -> list[str]:
    if not group_by_text:
        return []
    return [normalize_identifier(part) for part in split_top_level(group_by_text, ",")]


def parse_collection_name(from_clause: str) -> str:
    token = from_clause.strip().split()[0]
    collection = PLACEHOLDER_REPLACEMENTS.get(token, token)
    return collection


def build_pipeline(sql_text: str) -> tuple[str, str, list[dict[str, Any]]]:
    title_match = TITLE_PATTERN.search(sql_text)
    if not title_match:
        raise ValueError("Missing query title comment.")

    title = title_match.group(2).strip()
    clean_sql = strip_sql_comments(sql_text)
    match = CLAUSE_PATTERN.search(clean_sql)
    if not match:
        raise ValueError("Unsupported SQL structure.")

    select_clause = match.group("select").strip()
    from_clause = match.group("from").strip()
    where_clause = (match.group("where") or "").strip()
    group_by_clause = (match.group("group_by") or "").strip()
    where_clause = replace_boundary_dates(where_clause)

    collection = parse_collection_name(from_clause)
    group_fields = parse_group_by(group_by_clause)
    select_items = split_top_level(select_clause, ",")

    pipeline: list[dict[str, Any]] = []
    if where_clause:
        pipeline.append({"$match": parse_where_clause(where_clause)})

    if group_fields:
        group_id = {field: f"${field}" for field in group_fields}
    else:
        group_id = None

    group_stage: dict[str, Any] = {"_id": group_id}
    project_stage: dict[str, Any] = {"_id": 0}
    for item in select_items:
        parse_select_item(item, group_stage, project_stage, group_fields)

    pipeline.append({"$group": group_stage})
    pipeline.append({"$project": project_stage})

    if group_fields:
        pipeline.append({"$sort": {field: 1 for field in group_fields}})

    return title, collection, pipeline


def convert_sql_file(sql_file: Path, output_dir: Path) -> Path:
    sql_text = sql_file.read_text(encoding="utf-8")
    query_id = sql_file.stem
    title, collection, pipeline = build_pipeline(sql_text)
    payload = {
        "query_id": int(query_id) if query_id.isdigit() else query_id,
        "title": title,
        "collection": collection,
        "pipeline": pipeline,
    }
    output_path = output_dir / f"{query_id}.yml"
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    source_dir = (base_dir / args.source_dir).resolve()
    output_dir = (base_dir / args.output_dir).resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    sql_files = sorted(
        source_dir.glob("*.sql"),
        key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem,
    )
    if not sql_files:
        raise ValueError(f"No .sql files found in: {source_dir}")

    for sql_file in sql_files:
        output_path = convert_sql_file(sql_file, output_dir)
        print(f"Converted {sql_file.name} -> {output_path.name}")


if __name__ == "__main__":
    main()
