import argparse
import csv

import mysql.connector


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "port": 3212,
    "database": "eastel",
}

TABLE_NAME = "country_code_reference"

EXPECTED_HEADERS = {
    "Country": "country",
    "Country code": "country_code",
}

INSERT_COLUMNS = [
    "country",
    "country_code",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load country code reference data into MySQL."
    )
    parser.add_argument("file_path", help="Path to the country code CSV file.")
    return parser.parse_args()


def create_table(cursor):
    cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    cursor.execute(
        f"""
        CREATE TABLE {TABLE_NAME} (
            country VARCHAR(255) NOT NULL,
            country_code VARCHAR(32) NOT NULL,
            PRIMARY KEY (country, country_code)
        )
        """
    )


def load_rows(file_path):
    with open(file_path, "r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)

        if reader.fieldnames is None:
            raise ValueError("Input file does not contain a header row.")

        missing_headers = [header for header in EXPECTED_HEADERS if header not in reader.fieldnames]
        if missing_headers:
            raise ValueError(f"Missing expected headers: {', '.join(missing_headers)}")

        rows = []
        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            country = (row.get("Country") or "").strip()
            country_code = (row.get("Country code") or "").strip()

            if not country:
                raise ValueError(f"Row {line_number}: Missing Country.")
            if not country_code:
                raise ValueError(f"Row {line_number}: Missing Country code.")

            rows.append((country, country_code))

    return rows


def truncate_and_insert(cursor, rows):
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
