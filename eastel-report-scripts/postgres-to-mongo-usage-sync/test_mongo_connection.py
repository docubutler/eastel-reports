from pymongo import MongoClient


MONGO_URI = "mongodb+srv://prodUser:CxNFHCraErGeEsYI@easteldataanalysis.zwi2ei.mongodb.net/?appName=EastelDataAnalysis"
MONGO_DATABASE = "eastel-data"


def main() -> None:
    try:
        with MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) as client:
            client.admin.command("ping")
            print("MongoDB connection successful.")
            print(f"Configured database: {MONGO_DATABASE}")
            print("Available databases:")
            for db_name in client.list_database_names():
                print(f" - {db_name}")
    except Exception as exc:
        print(f"MongoDB connection failed: {exc}")
        raise


if __name__ == "__main__":
    main()
