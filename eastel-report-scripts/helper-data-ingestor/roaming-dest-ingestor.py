import argparse
import csv
from datetime import datetime

import mysql.connector


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "port": 3212,
    "database": "eastel",
}

TABLE_NAME = "roaming_destination"

EXPECTED_HEADERS = {
    "roamingDestinationId": "roaming_destination_id",
    "serviceProvider": "service_provider",
    "country": "country",
    "roaming Destination Name": "roaming_destination_name",
    "mcc": "mcc",
    "remarks": "remarks",
    "Created at": "created_at",
    "Updated at": "updated_at",
}

INSERT_COLUMNS = [
    "roaming_destination_id",
    "service_provider",
    "country",
    "roaming_destination_name",
    "mcc",
    "remarks",
    "created_at",
    "updated_at",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load roaming destination reference data into MySQL."
    )
    parser.add_argument("file_path", help="Path to the CSV/TSV roaming destination file.")
    return parser.parse_args()


def create_table(cursor):
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            roaming_destination_id BIGINT NOT NULL,
            service_provider VARCHAR(255),
            country VARCHAR(255),
            roaming_destination_name VARCHAR(255),
            mcc VARCHAR(32),
            remarks TEXT,
            created_at DATETIME NULL,
            updated_at DATETIME NULL,
            PRIMARY KEY (roaming_destination_id)
        )
        """
    )


def detect_delimiter(file_path):
    with open(file_path, "r", encoding="utf-8-sig", newline="") as source:
        sample = source.read(4096)
        if not sample.strip():
            raise ValueError("Input file is empty.")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        first_line = sample.splitlines()[0]
        if "\t" in first_line:
            return "\t"
        return ","


def parse_datetime(value):
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned or cleaned.upper() == "N/A":
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unsupported datetime value: {value}")


def normalize_row(row):
    normalized = {}
    for raw_header, db_column in EXPECTED_HEADERS.items():
        normalized[db_column] = (row.get(raw_header) or "").strip()

    roaming_destination_id = normalized["roaming_destination_id"]
    if not roaming_destination_id:
        raise ValueError("Missing roamingDestinationId.")

    normalized["roaming_destination_id"] = int(roaming_destination_id)
    normalized["created_at"] = parse_datetime(normalized["created_at"])
    normalized["updated_at"] = parse_datetime(normalized["updated_at"])

    return tuple(normalized[column] for column in INSERT_COLUMNS)


def load_rows(file_path):
    delimiter = detect_delimiter(file_path)

    with open(file_path, "r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=delimiter)

        if reader.fieldnames is None:
            raise ValueError("Input file does not contain a header row.")

        missing_headers = [header for header in EXPECTED_HEADERS if header not in reader.fieldnames]
        if missing_headers:
            raise ValueError(f"Missing expected headers: {', '.join(missing_headers)}")

        rows = []
        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            try:
                rows.append(normalize_row(row))
            except ValueError as exc:
                raise ValueError(f"Row {line_number}: {exc}") from exc

    return rows


def truncate_and_insert(cursor, rows):
    cursor.execute(f"TRUNCATE TABLE {TABLE_NAME}")

    if not rows:
        return 0

    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    columns = ", ".join(INSERT_COLUMNS)
    cursor.executemany(
        f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def main():
    args = parse_args()
    rows = load_rows(args.file_path)

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        create_table(cursor)
        inserted_count = truncate_and_insert(cursor, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    print(f"Loaded {inserted_count} rows into '{TABLE_NAME}' from '{args.file_path}'.")


if __name__ == "__main__":
    main()
