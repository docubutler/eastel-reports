import csv
import mysql.connector
import os
import re
from mysql.connector import Error

# ==============================
# 🔧 CONFIG
# ==============================
CONFIG = {
    "file_path": r"H:\My Drive\Docubutler\Eastel\Eastel Reports\service_plans_map\data-1774344080742.csv",
    "db": {
        "host": "localhost",
        "port": 3212,
        "user": "root",
        "password": "root",
        "database": "eastel"
    },
    "table_name": "iot_portal_tb_sim_service_plan"
}

BAD_ROWS_FILE = "iot_portal_tb_sim_service_plan_bad_rows.csv"


def get_connection():
    return mysql.connector.connect(
        host=CONFIG["db"]["host"],
        port=CONFIG["db"]["port"],
        user=CONFIG["db"]["user"],
        password=CONFIG["db"]["password"],
        database=CONFIG["db"]["database"],
        allow_local_infile=True  # IMPORTANT
    )


def create_table(cursor, table_name):
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        sim_service_plan_id BIGINT NOT NULL,
        service_provider_id BIGINT NOT NULL,
        service_type_id BIGINT NOT NULL,
        currency_id BIGINT NOT NULL,
        account_id BIGINT NOT NULL,
        customer_id BIGINT NOT NULL,
        provisioning_category_id BIGINT NOT NULL,
        cr_user BIGINT NOT NULL,
        cr_time DATETIME NOT NULL,
        up_user BIGINT NOT NULL,
        up_time DATETIME NOT NULL,
        record_status INT NOT NULL,
        display_order INT NOT NULL,
        service_plan_id BIGINT NOT NULL,
        service_plan_code VARCHAR(100),
        service_plan_desc VARCHAR(500),
        each_quota BIGINT NOT NULL,
        unit VARCHAR(50) NOT NULL,
        volume DECIMAL(30,16),
        validity_time BIGINT NOT NULL,
        tier0_speed VARCHAR(50) NOT NULL,
        tier0_cd VARCHAR(50) NOT NULL,
        imei_lock_enabled INT NOT NULL,
        activate_days INT NOT NULL,
        face_value DECIMAL(30,16),
        selling_price DECIMAL(30,16),
        discounted_ratio DECIMAL(30,16),
        service_end_type INT NOT NULL,
        reserved_period INT NOT NULL,
        notification_type INT NOT NULL,
        frozen_period INT NOT NULL,
        activation_fee DECIMAL(30,16),
        top_up_type INT NOT NULL,
        event_message_status INT NOT NULL,
        effective_days INT NOT NULL,
        service_plan_nature INT NOT NULL,
        service_pool_nature INT NOT NULL,
        stop_data_after_service_end INT NOT NULL,
        bucket_mode INT NOT NULL,
        bundle_code VARCHAR(100),
        bundle_type VARCHAR(100),
        service_plan_type_id BIGINT NOT NULL,
        sim_id BIGINT NOT NULL,
        sim_master_id BIGINT NOT NULL,
        effective_start DATETIME NOT NULL,
        effective_end DATETIME NOT NULL,
        plan_condition INT NOT NULL,
        activate_start DATETIME,
        activate_end DATETIME,
        balance DECIMAL(32,16) NOT NULL,
        used_unit DECIMAL(32,16) NOT NULL,
        used_money DECIMAL(32,16) NOT NULL,
        recurring_date DATETIME,
        PRIMARY KEY (sim_service_plan_id)
    );
    """)

    expected_columns = {
        "sim_service_plan_id": "bigint",
        "service_provider_id": "bigint",
        "service_type_id": "bigint",
        "currency_id": "bigint",
        "account_id": "bigint",
        "customer_id": "bigint",
        "provisioning_category_id": "bigint",
        "cr_user": "bigint",
        "cr_time": "datetime",
        "up_user": "bigint",
        "up_time": "datetime",
        "record_status": "int",
        "display_order": "int",
        "service_plan_id": "bigint",
        "service_plan_code": "varchar(100)",
        "service_plan_desc": "varchar(500)",
        "each_quota": "bigint",
        "unit": "varchar(50)",
        "volume": "decimal(30,16)",
        "validity_time": "bigint",
        "tier0_speed": "varchar(50)",
        "tier0_cd": "varchar(50)",
        "imei_lock_enabled": "int",
        "activate_days": "int",
        "face_value": "decimal(30,16)",
        "selling_price": "decimal(30,16)",
        "discounted_ratio": "decimal(30,16)",
        "service_end_type": "int",
        "reserved_period": "int",
        "notification_type": "int",
        "frozen_period": "int",
        "activation_fee": "decimal(30,16)",
        "top_up_type": "int",
        "event_message_status": "int",
        "effective_days": "int",
        "service_plan_nature": "int",
        "service_pool_nature": "int",
        "stop_data_after_service_end": "int",
        "bucket_mode": "int",
        "bundle_code": "varchar(100)",
        "bundle_type": "varchar(100)",
        "service_plan_type_id": "bigint",
        "sim_id": "bigint",
        "sim_master_id": "bigint",
        "effective_start": "datetime",
        "effective_end": "datetime",
        "plan_condition": "int",
        "activate_start": "datetime",
        "activate_end": "datetime",
        "balance": "decimal(32,16)",
        "used_unit": "decimal(32,16)",
        "used_money": "decimal(32,16)",
        "recurring_date": "datetime",
    }

    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    existing_columns = {row[0]: str(row[1]).lower() for row in cursor.fetchall()}

    for column_name, expected_type in expected_columns.items():
        actual_type = existing_columns.get(column_name)
        if actual_type != expected_type:
            print(f"🔧 Aligning column {column_name}: {actual_type} -> {expected_type}")
            cursor.execute(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {expected_type.upper()}")


def load_csv(cursor, file_path, table_name):
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    file_path = file_path.replace("\\", "/")

    query = f"""
    LOAD DATA LOCAL INFILE '{file_path}'
    INTO TABLE {table_name}
    FIELDS TERMINATED BY ','
    ENCLOSED BY '"'
    LINES TERMINATED BY '\\n'
    IGNORE 1 ROWS
    (
        sim_service_plan_id,
        service_provider_id,
        service_type_id,
        currency_id,
        account_id,
        customer_id,
        provisioning_category_id,
        cr_user,
        cr_time,
        up_user,
        up_time,
        record_status,
        display_order,
        service_plan_id,
        service_plan_code,
        service_plan_desc,
        each_quota,
        unit,
        volume,
        validity_time,
        tier0_speed,
        tier0_cd,
        imei_lock_enabled,
        activate_days,
        face_value,
        selling_price,
        discounted_ratio,
        service_end_type,
        reserved_period,
        notification_type,
        frozen_period,
        activation_fee,
        top_up_type,
        event_message_status,
        effective_days,
        service_plan_nature,
        service_pool_nature,
        stop_data_after_service_end,
        bucket_mode,
        bundle_code,
        bundle_type,
        service_plan_type_id,
        sim_id,
        sim_master_id,
        effective_start,
        effective_end,
        plan_condition,
        activate_start,
        activate_end,
        balance,
        used_unit,
        used_money,
        recurring_date
    )
    SET
        cr_time = NULLIF(cr_time, 'NULL'),
        up_time = NULLIF(up_time, 'NULL'),
        activate_start = NULLIF(activate_start, 'NULL'),
        activate_end = NULLIF(activate_end, 'NULL'),
        recurring_date = NULLIF(recurring_date, 'NULL');
    """

    try:
        cursor.execute(query)
    except Error as exc:
        error_text = str(exc).lower()
        is_local_infile_error = (
            exc.errno in {3948, 2068}
            or "loading local data is disabled" in error_text
            or "local infile" in error_text
            or "file request rejected due to restrictions on access" in error_text
        )
        if not is_local_infile_error:
            raise
        print("⚠️ LOCAL INFILE is disabled; switching to batched INSERT mode...")
        load_csv_fallback(cursor, file_path, table_name)


def normalize_value(value):
    if value is None:
        return None

    value = value.strip()
    if value == "" or value.upper() == "NULL":
        return None
    return value


def log_bad_row(row_number, columns, raw_row, error_message):
    file_exists = os.path.exists(BAD_ROWS_FILE)
    with open(BAD_ROWS_FILE, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["csv_row_number", "error_message", "row_data"])
        row_map = {}
        for index, column in enumerate(columns):
            row_map[column] = raw_row[index] if index < len(raw_row) else None
        writer.writerow([row_number, error_message, repr(row_map)])


def print_row_error(row_number, columns, raw_row, exc):
    print(f"❌ Insert failed at CSV row {row_number}")
    print(f"   MySQL error: {exc}")

    column_match = re.search(r"column '([^']+)'", str(exc), re.IGNORECASE)
    if column_match:
        column_name = column_match.group(1)
        if column_name in columns:
            column_index = columns.index(column_name)
            bad_value = raw_row[column_index] if column_index < len(raw_row) else None
            print(f"   Column: {column_name}")
            print(f"   Value: {bad_value!r}")

    print(f"   Logged to: {BAD_ROWS_FILE}")
    log_bad_row(row_number, columns, raw_row, str(exc))


def load_csv_fallback(cursor, file_path, table_name, batch_size=1000):
    columns = [
        "sim_service_plan_id",
        "service_provider_id",
        "service_type_id",
        "currency_id",
        "account_id",
        "customer_id",
        "provisioning_category_id",
        "cr_user",
        "cr_time",
        "up_user",
        "up_time",
        "record_status",
        "display_order",
        "service_plan_id",
        "service_plan_code",
        "service_plan_desc",
        "each_quota",
        "unit",
        "volume",
        "validity_time",
        "tier0_speed",
        "tier0_cd",
        "imei_lock_enabled",
        "activate_days",
        "face_value",
        "selling_price",
        "discounted_ratio",
        "service_end_type",
        "reserved_period",
        "notification_type",
        "frozen_period",
        "activation_fee",
        "top_up_type",
        "event_message_status",
        "effective_days",
        "service_plan_nature",
        "service_pool_nature",
        "stop_data_after_service_end",
        "bucket_mode",
        "bundle_code",
        "bundle_type",
        "service_plan_type_id",
        "sim_id",
        "sim_master_id",
        "effective_start",
        "effective_end",
        "plan_condition",
        "activate_start",
        "activate_end",
        "balance",
        "used_unit",
        "used_money",
        "recurring_date",
    ]

    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    insert_sql = f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})"

    batch = []

    def flush_batch():
        nonlocal batch
        if not batch:
            return
        try:
            cursor.executemany(insert_sql, [row_values for _, _, row_values in batch])
            batch.clear()
            return
        except Error:
            pass

        for row_number, raw_row, row_values in batch:
            try:
                cursor.execute(insert_sql, row_values)
            except Error as exc:
                print_row_error(row_number, columns, raw_row, exc)
        batch.clear()

    with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(columns):
                message = f"Expected {len(columns)} columns, found {len(row)}"
                print(f"❌ CSV format error at row {row_number}: {message}")
                log_bad_row(row_number, columns, row, message)
                continue

            batch.append((row_number, row, tuple(normalize_value(value) for value in row)))
            if len(batch) >= batch_size:
                flush_batch()

    flush_batch()


def main():
    print("🚀 Starting import...")

    conn = get_connection()
    cursor = conn.cursor()

    print("📦 Creating table...")
    create_table(cursor, CONFIG["table_name"])

    print("⬆️ Loading CSV (fast mode)...")
    load_csv(cursor, CONFIG["file_path"], CONFIG["table_name"])

    conn.commit()
    cursor.close()
    conn.close()

    print("✅ Done!")


if __name__ == "__main__":
    main()
