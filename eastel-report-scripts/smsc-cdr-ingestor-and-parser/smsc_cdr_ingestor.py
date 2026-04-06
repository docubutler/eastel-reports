import os
import csv
import mysql.connector
from datetime import datetime

# ======================
# CONFIG
# ======================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "port": 3212,
    "database": "eastel"
}

INPUT_DIR = r"D:\DB_repos\eastel-reports\smsc1_march_01_29\logs-shared\logs-shared"
TABLE_NAME = "smsc_record"   # configurable table name
BATCH_SIZE = 1000

SUMMARY_FILE = os.path.join(INPUT_DIR, "ingestion_summary.txt")
ERROR_FILE = os.path.join(INPUT_DIR, "ingestion_errors.txt")


# ======================
# DB SETUP
# ======================
def create_tables(cursor):
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        raw_cdr TEXT,
        source_file VARCHAR(255),
        ingested_at DATETIME
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS smsc_processed_file (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        file_name VARCHAR(255),
        file_size BIGINT,
        last_modified_time DATETIME,
        processed_at DATETIME,
        UNIQUE KEY unique_file (file_name, file_size, last_modified_time)
    )
    """)


# ======================
# FILE CHECK
# ======================
def is_file_processed(cursor, file_name, file_size, mtime):
    cursor.execute("""
        SELECT 1 FROM smsc_processed_file
        WHERE file_name=%s AND file_size=%s AND last_modified_time=%s
        LIMIT 1
    """, (file_name, file_size, mtime))
    return cursor.fetchone() is not None


def mark_file_processed(cursor, file_name, file_size, mtime):
    cursor.execute("""
        INSERT INTO smsc_processed_file
        (file_name, file_size, last_modified_time, processed_at)
        VALUES (%s, %s, %s, %s)
    """, (file_name, file_size, mtime, datetime.now()))


# ======================
# PARSING
# ======================
def extract_cdr(line):
    try:
        return line.split('] ', 1)[1].strip()
    except Exception:
        return None


# ======================
# INSERT
# ======================
def insert_batch(cursor, batch):
    query = f"""
    INSERT INTO {TABLE_NAME} (raw_cdr, source_file, ingested_at)
    VALUES (%s, %s, %s)
    """
    cursor.executemany(query, batch)


# ======================
# PROCESS FILE
# ======================
def process_file(cursor, conn, file_path, error_writer):
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

    stats = {
        "file": file_name,
        "total": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0
    }

    if is_file_processed(cursor, file_name, file_size, mtime):
        print(f"[SKIP] Already processed: {file_name}")
        stats["skipped"] = -1
        return stats

    print(f"[START] Processing: {file_name}")

    batch = []

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, start=1):
            stats["total"] += 1

            cdr = extract_cdr(line)

            if not cdr:
                stats["errors"] += 1
                error_writer.write(f"{file_name}|LINE {line_num}|INVALID_PREFIX|{line}")
                continue

            try:
                parsed = list(csv.reader([cdr]))[0]

                # basic sanity check (expected many columns)
                if len(parsed) < 10:
                    raise ValueError("Too few columns")

            except Exception as e:
                stats["errors"] += 1
                error_writer.write(f"{file_name}|LINE {line_num}|CSV_ERROR|{line}")
                continue

            batch.append((cdr, file_name, datetime.now()))

            if len(batch) >= BATCH_SIZE:
                insert_batch(cursor, batch)
                conn.commit()
                stats["inserted"] += len(batch)
                print(f"   → Inserted {stats['inserted']} rows so far...")
                batch.clear()

    if batch:
        insert_batch(cursor, batch)
        conn.commit()
        stats["inserted"] += len(batch)

    mark_file_processed(cursor, file_name, file_size, mtime)
    conn.commit()

    print(f"[DONE] {file_name} | Total: {stats['total']} | Inserted: {stats['inserted']} | Errors: {stats['errors']}")

    return stats


# ======================
# MAIN
# ======================
def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    create_tables(cursor)

    files = []
    # Walk through the input directory and gather all files irrespeective of subfolders and extensions
    for root, _, filenames in os.walk(INPUT_DIR):
        for f in filenames:
            files.append(os.path.join(root, f))

    total_files = len(files)
    print(f"\nTotal files found: {total_files}\n")

    all_stats = []

    with open(ERROR_FILE, "w", encoding="utf-8") as error_writer:
        for idx, file_path in enumerate(files, start=1):
            print(f"\nProcessing file {idx}/{total_files}")
            stats = process_file(cursor, conn, file_path, error_writer)
            all_stats.append(stats)

    # ======================
    # SUMMARY REPORT
    # ======================
    with open(SUMMARY_FILE, "w", encoding="utf-8") as summary:
        summary.write("SMSC INGESTION SUMMARY\n")
        summary.write(f"Run Time: {datetime.now()}\n\n")

        for s in all_stats:
            if s["skipped"] == -1:
                summary.write(f"{s['file']} → SKIPPED (already processed)\n")
            else:
                summary.write(
                    f"{s['file']} → Total: {s['total']}, "
                    f"Inserted: {s['inserted']}, "
                    f"Errors: {s['errors']}\n"
                )

    print("\n=== INGESTION COMPLETE ===")
    print(f"Summary file: {SUMMARY_FILE}")
    print(f"Error file: {ERROR_FILE}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()