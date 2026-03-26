from __future__ import annotations

import argparse
import csv
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

import mysql.connector
from mysql.connector import MySQLConnection

from table_schemas import TABLE_SPECS, TableSpec


BASE_DIR = Path(__file__).resolve().parent
MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3212,
    "user": "root",
    "password": "root",
    "database": "eastel",
}
BAD_ROWS_FILE = BASE_DIR / "bad_rows_log.csv"


class RowParseError(ValueError):
    def __init__(self, column_name: str, raw_value: object, message: str) -> None:
        super().__init__(message)
        self.column_name = column_name
        self.raw_value = raw_value


class RecordSource:
    def iter_rows(self, table_spec: TableSpec) -> Iterator[dict[str, object]]:
        raise NotImplementedError


class CsvRecordSource(RecordSource):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def iter_rows(self, table_spec: TableSpec) -> Iterator[dict[str, object]]:
        # Keep source reading isolated so CSV can be replaced by PostgreSQL later.
        source_name = (table_spec.source_name or "").strip()
        if not source_name:
            print(f"[{table_spec.table_name}] skipping import: source_name is empty")
            return

        configured_path = Path(source_name)
        csv_path = configured_path if configured_path.is_absolute() else self.base_dir / configured_path

        if not csv_path.exists():
            print(f"[{table_spec.table_name}] skipping import: source file does not exist: {csv_path}")
            return

        print(f"[{table_spec.table_name}] opening CSV: {csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield dict(row)


def append_bad_row(
    table_name: str,
    row_number: int,
    row_identifier: object,
    column_name: str,
    bad_value: object,
    error_message: str,
) -> None:
    file_exists = BAD_ROWS_FILE.exists()
    with BAD_ROWS_FILE.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(
                ["table_name", "row_number", "row_identifier", "column_name", "bad_value", "error_message"]
            )
        writer.writerow([table_name, row_number, row_identifier, column_name, repr(bad_value), error_message])


MYSQL_TYPE_CASTERS = {
    "BIGINT": int,
    "INT": int,
    "TINYINT": int,
    "DECIMAL": Decimal,
}


def parse_value(raw_value: object, column: ColumnSpec) -> object:
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        value = raw_value.strip()
        if value == "" or value.upper() == "NULL":
            return None
    else:
        value = raw_value

    mysql_base_type = column.mysql_type.split("(", 1)[0]
    caster = MYSQL_TYPE_CASTERS.get(mysql_base_type)
    if caster is None:
        return value

    try:
        return caster(value)
    except (ValueError, InvalidOperation) as exc:
        raise RowParseError(column.name, value, f"Invalid value for column '{column.name}': {value!r}") from exc


def connect_mysql(args: argparse.Namespace) -> MySQLConnection:
    return mysql.connector.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        autocommit=False,
    )


def build_column_definition(column) -> str:
    nullable_sql = "NULL" if column.nullable else "NOT NULL"
    return f"`{column.name}` {column.mysql_type} {nullable_sql}"


def sync_table_columns(connection: MySQLConnection, cursor, table_spec: TableSpec) -> None:
    cursor.execute(
        """
        SELECT column_name, column_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        """,
        (connection.database, table_spec.table_name),
    )
    existing_columns = {
        row[0]: {"column_type": str(row[1]).upper(), "is_nullable": row[2] == "YES"}
        for row in cursor.fetchall()
    }

    for column in table_spec.columns:
        desired_type = column.mysql_type.upper()
        desired_nullable = column.nullable
        desired_definition = build_column_definition(column)
        existing = existing_columns.get(column.name)

        if existing is None:
            print(f"[{table_spec.table_name}] adding missing column {column.name}")
            cursor.execute(f"ALTER TABLE `{table_spec.table_name}` ADD COLUMN {desired_definition}")
            continue

        if existing["column_type"] != desired_type or existing["is_nullable"] != desired_nullable:
            print(f"[{table_spec.table_name}] aligning column {column.name} to schema")
            cursor.execute(f"ALTER TABLE `{table_spec.table_name}` MODIFY COLUMN {desired_definition}")


def create_table(connection: MySQLConnection, cursor, table_spec: TableSpec) -> None:
    print(f"[{table_spec.table_name}] ensuring table exists")
    column_sql = []
    for column in table_spec.columns:
        column_sql.append(build_column_definition(column))

    primary_key_sql = ""
    if table_spec.primary_keys:
        key_columns = ", ".join(f"`{name}`" for name in table_spec.primary_keys)
        primary_key_sql = f", PRIMARY KEY ({key_columns})"

    sql = (
        f"CREATE TABLE IF NOT EXISTS `{table_spec.table_name}` ("
        + ", ".join(column_sql)
        + primary_key_sql
        + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )
    cursor.execute(sql)
    sync_table_columns(connection, cursor, table_spec)

    print(f"[{table_spec.table_name}] checking indexes")
    for index_columns in table_spec.indexes:
        index_name = "idx_" + "_".join(index_columns)
        indexed_columns = ", ".join(f"`{name}`" for name in index_columns)
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.statistics
            WHERE table_schema = %s
              AND table_name = %s
              AND index_name = %s
            LIMIT 1
            """,
            (connection.database, table_spec.table_name, index_name),
        )
        if cursor.fetchone() is None:
            print(f"[{table_spec.table_name}] creating index {index_name}")
            cursor.execute(
                f"CREATE INDEX `{index_name}` "
                f"ON `{table_spec.table_name}` ({indexed_columns})"
            )
        else:
            print(f"[{table_spec.table_name}] index already exists: {index_name}")


def build_insert_sql(table_spec: TableSpec) -> str:
    column_list = ", ".join(f"`{name}`" for name in table_spec.column_names)
    value_list = ", ".join(["%s"] * len(table_spec.column_names))
    update_list = ", ".join(
        f"`{name}` = VALUES(`{name}`)"
        for name in table_spec.column_names
        if name not in table_spec.primary_keys
    )
    return (
        f"INSERT INTO `{table_spec.table_name}` ({column_list}) VALUES ({value_list}) "
        f"ON DUPLICATE KEY UPDATE {update_list}"
    )


def row_to_tuple(row: dict[str, object], table_spec: TableSpec) -> tuple[object, ...]:
    values = []
    for column in table_spec.columns:
        values.append(parse_value(row.get(column.name), column))
    return tuple(values)


def get_row_identifier(raw_row: dict[str, object], table_spec: TableSpec) -> object:
    if table_spec.primary_keys:
        return raw_row.get(table_spec.primary_keys[0])
    return ""


def load_table(
    connection: MySQLConnection,
    table_spec: TableSpec,
    source: RecordSource,
    batch_size: int,
) -> int:
    insert_sql = build_insert_sql(table_spec)
    total_rows = 0
    skipped_rows = 0
    batch: list[tuple[object, ...]] = []

    with connection.cursor() as cursor:
        create_table(connection, cursor, table_spec)

        print(f"[{table_spec.table_name}] reading source: {table_spec.source_name}")
        for source_row_number, raw_row in enumerate(source.iter_rows(table_spec), start=1):
            try:
                batch.append(row_to_tuple(raw_row, table_spec))
            except Exception as parse_error:
                print(f"[{table_spec.table_name}] failed while parsing source row {source_row_number}")
                print(f"[{table_spec.table_name}] skipping row and writing to {BAD_ROWS_FILE.name}")
                row_identifier = get_row_identifier(raw_row, table_spec)
                if isinstance(parse_error, RowParseError):
                    print(
                        f"[{table_spec.table_name}] bad column {parse_error.column_name}="
                        f"{parse_error.raw_value!r} for row id {row_identifier}"
                    )
                    append_bad_row(
                        table_spec.table_name,
                        source_row_number,
                        row_identifier,
                        parse_error.column_name,
                        parse_error.raw_value,
                        str(parse_error),
                    )
                else:
                    append_bad_row(
                        table_spec.table_name,
                        source_row_number,
                        row_identifier,
                        "",
                        "",
                        str(parse_error),
                    )
                skipped_rows += 1
                continue
            if len(batch) >= batch_size:
                print(f"[{table_spec.table_name}] importing batch of {len(batch)} rows")
                try:
                    cursor.executemany(insert_sql, batch)
                except Exception:
                    print(f"[{table_spec.table_name}] batch insert failed, isolating bad row")
                    successful_rows = 0
                    for row_offset, row_values in enumerate(batch):
                        row_number = total_rows + skipped_rows + successful_rows + 1
                        try:
                            cursor.execute(insert_sql, row_values)
                        except Exception as row_error:
                            print(f"[{table_spec.table_name}] failed at source row {row_number}")
                            print(f"[{table_spec.table_name}] row data: {row_values}")
                            print(f"[{table_spec.table_name}] skipping row and writing to {BAD_ROWS_FILE.name}")
                            append_bad_row(
                                table_spec.table_name,
                                row_number,
                                row_values[0] if row_values else "",
                                "",
                                "",
                                str(row_error),
                            )
                            skipped_rows += 1
                        else:
                            successful_rows += 1
                    total_rows += successful_rows
                    batch.clear()
                    continue
                total_rows += len(batch)
                batch.clear()

        if batch:
            print(f"[{table_spec.table_name}] importing final batch of {len(batch)} rows")
            try:
                cursor.executemany(insert_sql, batch)
            except Exception:
                print(f"[{table_spec.table_name}] final batch insert failed, isolating bad row")
                successful_rows = 0
                for row_offset, row_values in enumerate(batch):
                    row_number = total_rows + skipped_rows + successful_rows + 1
                    try:
                        cursor.execute(insert_sql, row_values)
                    except Exception as row_error:
                        print(f"[{table_spec.table_name}] failed at source row {row_number}")
                        print(f"[{table_spec.table_name}] row data: {row_values}")
                        print(f"[{table_spec.table_name}] skipping row and writing to {BAD_ROWS_FILE.name}")
                        append_bad_row(
                            table_spec.table_name,
                            row_number,
                            row_values[0] if row_values else "",
                            "",
                            "",
                            str(row_error),
                        )
                        skipped_rows += 1
                    else:
                        successful_rows += 1
                total_rows += successful_rows
                batch.clear()
                print(
                    f"[{table_spec.table_name}] import complete: {total_rows} rows, skipped {skipped_rows} bad rows"
                )
                return total_rows
            total_rows += len(batch)

    print(f"[{table_spec.table_name}] import complete: {total_rows} rows, skipped {skipped_rows} bad rows")
    return total_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create MySQL tables for Eastel report extracts and import data."
    )
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", MYSQL_CONFIG["host"]))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", str(MYSQL_CONFIG["port"]))))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", MYSQL_CONFIG["user"]))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", MYSQL_CONFIG["password"]))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", MYSQL_CONFIG["database"]))
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = CsvRecordSource(BASE_DIR)
    print(f"Connecting to MySQL database '{args.database}' on {args.host}:{args.port}")
    connection = connect_mysql(args)

    try:
        for table_spec in TABLE_SPECS:
            loaded_rows = load_table(connection, table_spec, source, args.batch_size)
            print(f"{table_spec.table_name}: imported {loaded_rows} rows from {table_spec.source_name}")
        print("Committing transaction")
        connection.commit()
    except Exception:
        print("Error encountered, rolling back transaction")
        connection.rollback()
        raise
    finally:
        print("Closing MySQL connection")
        connection.close()


if __name__ == "__main__":
    main()
