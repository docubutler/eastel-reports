import os
from pathlib import Path
from typing import Any

import psycopg
import yaml


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return data


def get_config_value(config: dict[str, Any], section: str, key: str, env_name: str, default: Any = None) -> Any:
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    section_data = config.get(section, {})
    if isinstance(section_data, dict) and key in section_data and section_data[key] not in (None, ""):
        return section_data[key]
    return default


def get_postgres_dsn(config: dict[str, Any]) -> str:
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn
    dsn = config.get("postgres", {}).get("dsn")
    if dsn:
        return str(dsn)

    host = get_config_value(config, "postgres", "host", "PGHOST", "localhost")
    port = get_config_value(config, "postgres", "port", "PGPORT", "5432")
    dbname = get_config_value(config, "postgres", "database", "PGDATABASE")
    user = get_config_value(config, "postgres", "user", "PGUSER")
    password = get_config_value(config, "postgres", "password", "PGPASSWORD")
    sslmode = get_config_value(config, "postgres", "sslmode", "PGSSLMODE")

    missing = [name for name, value in {
        "PGDATABASE": dbname,
        "PGUSER": user,
        "PGPASSWORD": password,
    }.items() if not value]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"Missing PostgreSQL settings: {missing_text}")

    parts = [
        f"host={host}",
        f"port={port}",
        f"dbname={dbname}",
        f"user={user}",
        f"password={password}",
    ]
    if sslmode:
        parts.append(f"sslmode={sslmode}")
    return " ".join(parts)


def main() -> None:
    config = load_config(str(DEFAULT_CONFIG_PATH))
    postgres_dsn = get_postgres_dsn(config)

    try:
        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, version()")
                database_name, user_name, version = cursor.fetchone()

            print("PostgreSQL connection successful.")
            print(f"Configured database: {database_name}")
            print(f"Connected user: {user_name}")
            print(f"Server version: {version}")
    except Exception as exc:
        print(f"PostgreSQL connection failed: {exc}")
        raise


if __name__ == "__main__":
    main()
