import pymysql
from pymongo import MongoClient

# MySQL connection
mysql_conn = pymysql.connect(
    host="localhost",
    user="root",
    password="root",
    database="eastel",
    port=3212,
    cursorclass=pymysql.cursors.DictCursor
)

# MongoDB connection
mongo_client = MongoClient("mongodb+srv://mongoAdmin:mongoAdmin@cluster0.awzu7vd.mongodb.net/")
mongo_db = mongo_client["eastel-data"]
collection = mongo_db["usage_logs"]

# -------- classification functions -------- #

def classify_service(row):
    sub = row["service_type_sub_cd"]

    if sub in ["MO", "MT"]:
        return "VOICE"
    elif row["rating_group"] in ["SMS", "SM"]:
        return "SMS"
    else:
        return "DATA"

def classify_geo(row):
    mccmnc = row["roaming_mccmnc"]

    if not mccmnc:
        return "LOCAL"

    if str(mccmnc).startswith("92"):
        return "LOCAL"

    return "ROAMING"

def classify_rat(rat):
    if not rat:
        return None
    if "5G" in rat:
        return "5G"
    if "4G" in rat or "LTE" in rat:
        return "4G"
    return rat

# -------- migration -------- #

with mysql_conn.cursor() as cursor:
    cursor.execute("SELECT * FROM iot_portal_tb_usage_log_rep")

    batch = []
    batch_size = 1000

    for row in cursor:
        doc = {
            "usage_log_id": row["usage_log_id"],
            "sim_id": row["sim_id"],
            "customer_id": row["customer_id"],

            "identifiers": {
                "iccid": row["iccid"],
                "msisdn": row["msisdn"]
            },

            "service": {
                "type": classify_service(row),
                "direction": row["service_type_sub_cd"],
                "rat": classify_rat(row["rat_type"])
            },

            "geography": {
                "type": classify_geo(row),
                "mccmnc": row["roaming_mccmnc"]
            },

            "usage": {
                "unit": float(row["usage_unit"] or 0),
                "actual_unit": float(row["act_usage_unit"] or 0),
                "timestamp": row["usage_start_time"]
            }
        }

        batch.append(doc)

        if len(batch) >= batch_size:
            collection.insert_many(batch)
            batch = []
            print("Inserted batch")

    if batch:
        collection.insert_many(batch)

print("Migration complete")