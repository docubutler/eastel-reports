import csv
import mysql.connector
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "port" : 3212,
    "database": "eastel"
}

BATCH_SIZE = 1000


def safe(fields, idx):
    try:
        val = fields[idx]
        if val == "null" or val == "":
            return None
        return val
    except:
        return None


def parse_row(raw_cdr):
    try:
        fields = list(csv.reader([raw_cdr]))[0]

        return (
            safe(fields, 0),   # delivery_date
            safe(fields, 1),
            safe(fields, 2),
            safe(fields, 3),
            safe(fields, 4),
            safe(fields, 5),
            safe(fields, 6),
            safe(fields, 7),
            safe(fields, 8),
            safe(fields, 9),
            safe(fields, 10),
            safe(fields, 11),
            safe(fields, 12),
            safe(fields, 13),
            safe(fields, 14),
            safe(fields, 15),
            safe(fields, 16),
            safe(fields, 17),
            safe(fields, 18),
            safe(fields, 19),
            safe(fields, 20),
            safe(fields, 21),
            safe(fields, 22),
            safe(fields, 23),
            safe(fields, 24),
            safe(fields, 25),
            safe(fields, 26),
            safe(fields, 27),
            safe(fields, 28),
            safe(fields, 29)
        )
    except:
        return None


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    select_query = """
    SELECT id, raw_cdr
    FROM smsc_record
    WHERE processed_flag = 0
    LIMIT %s
    """

    insert_query = """
    INSERT INTO smsc_record_parsed (
        raw_id,
        delivery_date,
        addr_src_digits,
        addr_src_ton,
        addr_src_npi,
        addr_dst_digits,
        addr_dst_ton,
        addr_dst_npi,
        message_delivery_status,
        origination_type,
        message_type,
        orig_system_id,
        message_id,
        dvl_message_id,
        receipt_local_message_id,
        nnn_digits,
        imsi,
        corr_id,
        originator_sccp_address,
        mt_service_center_address,
        orig_network_id,
        network_id,
        mproc_notes,
        msg_parts,
        char_numbers,
        processing_time,
        delivery_delay,
        schedule_delivery_delay,
        delivery_count,
        sms_text,
        reason_for_failure
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    while True:
        cursor.execute(select_query, (BATCH_SIZE,))
        rows = cursor.fetchall()

        if not rows:
            print("No more records to process.")
            break

        insert_batch = []
        processed_ids = []

        for row_id, raw_cdr in rows:
            parsed = parse_row(raw_cdr)

            if parsed:
                insert_batch.append((row_id, *parsed))
                processed_ids.append(row_id)

        if insert_batch:
            cursor.executemany(insert_query, insert_batch)

        if processed_ids:
            format_strings = ','.join(['%s'] * len(processed_ids))
            cursor.execute(
                f"UPDATE smsc_record SET processed_flag = 1 WHERE id IN ({format_strings})",
                processed_ids
            )

        conn.commit()

        print(f"Processed batch of {len(rows)} rows")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()