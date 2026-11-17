"""Restore table parts written by postgres_table_to_s3.py back into PostgreSQL.

Streams each part straight from S3 through gunzip into COPY ... FROM STDIN: no
local staging. Resumable via a state object next to the manifest, and each part is
loaded in its own transaction so a checksum mismatch rolls that part back.
"""
import argparse
import hashlib
import json
import logging
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import yaml

import postgres_table_to_s3 as exporter


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
MANIFEST_NAME = "manifest.json"
DEFAULT_STATE_NAME = "restore-state.json"
DEFAULT_CHUNK_BYTES = 1048576
HEADER_PROBE_BYTES = 1 << 18
LOG = logging.getLogger("restore_from_s3")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--restart", action="store_true", help="Ignore the restore state and start from part 1.")
    parser.add_argument("--status", action="store_true", help="Print restore progress and exit.")
    parser.add_argument("--verify", action="store_true", help="Compare the manifest against the target table and exit.")
    parser.add_argument("--target-table", default="", help="Override restore.target_table.")
    parser.add_argument("--truncate", action="store_true", help="Truncate the target table before loading.")
    parser.add_argument("--limit-parts", type=int, default=0, help="Stop after N parts (testing).")
    return parser.parse_args()


# --------------------------------------------------------------------------- settings


class RestoreSettings:
    def __init__(self, config: dict[str, Any], args: argparse.Namespace) -> None:
        self.postgres = exporter.section(config, "postgres")
        self.s3 = exporter.section(config, "s3")
        restore = exporter.section(config, "restore")

        self.target_table = (args.target_table or restore.get("target_table") or "").strip()
        if not self.target_table:
            raise ValueError("restore.target_table is required (or pass --target-table).")
        self.target_ident = exporter.quote_identifier(self.target_table)

        self.truncate_first = bool(args.truncate or restore.get("truncate_first", False))
        self.verify_checksums = bool(restore.get("verify_checksums", True))
        self.state_name = str(restore.get("state_key") or DEFAULT_STATE_NAME).strip()
        self.chunk_bytes = exporter.positive_int(restore.get("chunk_bytes", DEFAULT_CHUNK_BYTES), "restore.chunk_bytes")
        self.statement_timeout_ms = exporter.positive_int(
            restore.get("statement_timeout_ms", 0), "restore.statement_timeout_ms", allow_zero=True
        )

        self.bucket = str(self.s3.get("bucket") or "").strip()
        if not self.bucket:
            raise ValueError("s3.bucket is required.")
        self.prefix = str(self.s3.get("prefix") or "").strip().strip("/")
        self.region = str(self.s3.get("region") or "").strip()
        self.endpoint_url = str(self.s3.get("endpoint_url") or "").strip()

    def key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name


# --------------------------------------------------------------------------- S3


class Store:
    def __init__(self, settings: RestoreSettings) -> None:
        import boto3

        self.bucket = settings.bucket
        self.settings = settings
        self.client = boto3.client(
            "s3", region_name=settings.region or None, endpoint_url=settings.endpoint_url or None
        )

    def get_json(self, name: str) -> dict[str, Any] | None:
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.settings.key(name))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return json.loads(response["Body"].read().decode("utf-8"))

    def put_json(self, name: str, payload: dict[str, Any]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.settings.key(name),
            Body=json.dumps(payload, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    def open_part(self, key: str) -> Any:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]


class GunzipReader:
    """File-like reader: S3 body -> gunzip -> COPY, hashing the stored bytes."""

    def __init__(self, body: Any, chunk_bytes: int) -> None:
        self.body = body
        self.chunk_bytes = chunk_bytes
        self._decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self._buffer = bytearray()
        self._finished = False
        self.sha256 = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        want = self.chunk_bytes if size is None or size < 0 else size
        while len(self._buffer) < want and not self._finished:
            chunk = self.body.read(self.chunk_bytes)
            if not chunk:
                self._buffer += self._decompressor.flush()
                self._finished = True
                break
            self.sha256.update(chunk)
            self.bytes_read += len(chunk)
            self._buffer += self._decompressor.decompress(chunk)
        out = bytes(self._buffer[:want])
        del self._buffer[:want]
        return out


def probe_header(store: Store, key: str, columns: list[str], chunk_bytes: int) -> bool:
    """Decide whether parts carry a CSV header, without trusting config."""
    reader = GunzipReader(store.open_part(key), chunk_bytes)
    head = reader.read(HEADER_PROBE_BYTES).decode("utf-8", errors="replace")
    reader.body.close()
    first_line = head.splitlines()[0] if head else ""
    expected = ",".join(columns)
    return first_line.strip() == expected.strip()


# --------------------------------------------------------------------------- restore loop


def new_state(settings: RestoreSettings, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "target_table": settings.target_table,
        "manifest_parts": manifest["totals"]["parts"],
        "manifest_rows": manifest["totals"]["rows"],
        "loaded_parts": 0,
        "rows_loaded": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "completed": False,
    }


def load_part(
    connection: Any, settings: RestoreSettings, store: Store, part: dict[str, Any],
    columns: list[str], has_header: bool,
) -> None:
    body = store.open_part(part["key"])
    reader = GunzipReader(body, settings.chunk_bytes)
    column_list = ", ".join(exporter.quote_identifier(column) for column in columns)
    copy_sql = (
        f"COPY {settings.target_ident} ({column_list}) FROM STDIN "
        f"WITH (FORMAT csv, HEADER {'true' if has_header else 'false'})"
    )
    try:
        with connection.cursor() as cursor:
            cursor.copy_expert(copy_sql, reader)
        if settings.verify_checksums and reader.sha256.hexdigest() != part["sha256"]:
            raise ValueError(
                f"checksum mismatch for {part['key']}: expected {part['sha256']}, got {reader.sha256.hexdigest()}"
            )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        body.close()


def print_status(settings: RestoreSettings, store: Store) -> int:
    state = store.get_json(settings.state_name)
    if not state:
        print(f"No restore state at {settings.prefix}/{settings.state_name}")
        return 1
    print(f"target table : {state['target_table']}")
    print(f"parts loaded : {state['loaded_parts']} / {state['manifest_parts']}")
    print(f"rows loaded  : {state['rows_loaded']:,} / {state['manifest_rows']:,}")
    print(f"completed    : {state['completed']}")
    print(f"updated      : {state['updated_at']}")
    return 0


def verify(settings: RestoreSettings, store: Store, connection: Any) -> int:
    manifest = store.get_json(MANIFEST_NAME)
    if not manifest:
        print(f"No manifest at {settings.prefix}/{MANIFEST_NAME}")
        return 1
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {settings.target_ident}")
        target_rows = int(cursor.fetchone()[0])
    expected = manifest["totals"]["rows"]
    print(f"manifest rows : {expected:,}")
    print(f"target rows   : {target_rows:,}")
    if target_rows == expected:
        print("MATCH - restore is complete and consistent.")
        return 0
    print("MISMATCH - resume the restore or investigate the target table.")
    return 2


def restore(args: argparse.Namespace, settings: RestoreSettings, store: Store, connection: Any) -> int:
    manifest = store.get_json(MANIFEST_NAME)
    if not manifest:
        LOG.error("No manifest at %s/%s; nothing to restore.", settings.prefix, MANIFEST_NAME)
        return 2
    if manifest["source"]["format"] != "csv":
        LOG.error("Only csv parts can be restored; manifest format is %s.", manifest["source"]["format"])
        return 2

    settings_columns = manifest["source"]["columns"]
    parts = manifest["parts"]

    state = None if args.restart else store.get_json(settings.state_name)
    if state and state.get("target_table") != settings.target_table:
        LOG.error("Restore state belongs to %s; re-run with --restart.", state["target_table"])
        return 2
    if not state:
        state = new_state(settings, manifest)
        if settings.truncate_first:
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE {settings.target_ident}")
            connection.commit()
            LOG.info("Truncated %s", settings.target_table)
        LOG.info("Restoring %s part(s) into %s from %s", len(parts), settings.target_table, settings.prefix)
    else:
        LOG.info(
            "Resuming restore: %s/%s part(s), %s row(s)",
            state["loaded_parts"], state["manifest_parts"], f"{state['rows_loaded']:,}",
        )

    has_header = probe_header(store, parts[0]["key"], settings_columns, settings.chunk_bytes)
    LOG.info("Parts carry a CSV header: %s", has_header)

    started = time.perf_counter()
    pending = [part for part in parts if part["index"] > state["loaded_parts"]]
    if args.limit_parts:
        pending = pending[: args.limit_parts]

    for part in pending:
        part_started = time.perf_counter()
        load_part(connection, settings, store, part, settings_columns, has_header)
        elapsed = max(time.perf_counter() - part_started, 1e-9)

        state["loaded_parts"] = part["index"]
        state["rows_loaded"] += part["rows"]
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["completed"] = state["loaded_parts"] >= state["manifest_parts"]
        store.put_json(settings.state_name, state)

        LOG.info(
            "part %s | rows %s (+%s) | %s rows/s | %s",
            f"{part['index']:05d}",
            f"{state['rows_loaded']:,}",
            f"{part['rows']:,}",
            f"{int(part['rows'] / elapsed):,}",
            part["key"],
        )

    elapsed = max(time.perf_counter() - started, 1e-9)
    LOG.info(
        "Done | loaded %s/%s part(s) | %s row(s) | %s row/s",
        state["loaded_parts"], state["manifest_parts"], f"{state['rows_loaded']:,}",
        f"{int(sum(p['rows'] for p in pending) / elapsed):,}" if pending else "0",
    )
    if not state["completed"]:
        LOG.info("Restore not finished. Re-run the same command to resume from part %s.",
                 state["loaded_parts"] + 1)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    config = exporter.load_config(Path(args.config).expanduser().resolve())
    settings = RestoreSettings(config, args)
    store = Store(settings)

    if args.status:
        return print_status(settings, store)

    connection = exporter.connect_postgres(settings.postgres, settings.statement_timeout_ms)
    try:
        connection.autocommit = False
        if args.verify:
            return verify(settings, store, connection)
        return restore(args, settings, store, connection)
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
