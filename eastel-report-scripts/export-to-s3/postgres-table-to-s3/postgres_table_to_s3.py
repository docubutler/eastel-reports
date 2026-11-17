"""Export a PostgreSQL table to size-split, gzipped CSV (or JSONL) parts in S3.

Resumable and idempotent: progress is tracked as the last exported key value plus
the parts already uploaded, in a manifest stored next to the parts.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extensions
import yaml


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
MANIFEST_NAME = "manifest.json"
LOG = logging.getLogger("postgres_table_to_s3")

CONTENT_TYPES = {"csv": "text/csv", "jsonl": "application/x-ndjson"}
SUFFIXES = {"csv": "csv.gz", "jsonl": "jsonl.gz"}


# --------------------------------------------------------------------------- config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--restart", action="store_true", help="Ignore the manifest and start from part 1.")
    parser.add_argument("--status", action="store_true", help="Print manifest progress and exit.")
    parser.add_argument("--verify", action="store_true", help="Compare manifest row counts with the table and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated COPY statements and exit.")
    parser.add_argument("--local-dir", default="", help="Write parts here instead of S3 (testing / air-gapped).")
    parser.add_argument("--max-part-bytes", type=int, default=0, help="Override export.max_part_bytes.")
    parser.add_argument("--limit-parts", type=int, default=0, help="Stop after N parts (testing).")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}. Copy config-sample.yml to config.yml first.")
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("Config must contain a YAML mapping.")
    return config


def section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping.")
    return value


def positive_int(value: Any, name: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value).strip()):
        raise ValueError(f"{name} must be an integer.")
    number = int(str(value).strip())
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'>= 0' if allow_zero else '> 0'}.")
    return number


def quote_identifier(value: str) -> str:
    parts = value.strip().split(".")
    if len(parts) not in (1, 2) or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return ".".join(f'"{part}"' for part in parts)


# --------------------------------------------------------------------------- settings


class Settings:
    def __init__(self, config: dict[str, Any], args: argparse.Namespace) -> None:
        self.postgres = section(config, "postgres")
        self.s3 = section(config, "s3")
        export = section(config, "export")

        self.table = str(export.get("source_table") or "").strip()
        if not self.table:
            raise ValueError("export.source_table is required.")
        self.table_ident = quote_identifier(self.table)

        self.format = str(export.get("format") or "csv").strip().lower()
        if self.format not in ("csv", "jsonl"):
            raise ValueError("export.format must be 'csv' or 'jsonl'.")

        self.resume_column = str(export.get("resume_column") or "").strip()
        if not self.resume_column:
            raise ValueError("export.resume_column is required (a unique, indexed column).")

        self.columns = [str(c).strip() for c in (export.get("columns") or []) if str(c).strip()]
        self.where = str(export.get("where") or "").strip()
        self.max_part_bytes = args.max_part_bytes or positive_int(
            export.get("max_part_bytes", 52428800), "export.max_part_bytes"
        )
        self.batch_rows = positive_int(export.get("initial_batch_rows", 100000), "export.initial_batch_rows")
        self.header = bool(export.get("header", True))
        self.compress = bool(export.get("compress", True))
        self.gzip_level = positive_int(export.get("gzip_level", 6), "export.gzip_level", allow_zero=True)
        self.multipart_part_bytes = positive_int(
            export.get("multipart_part_bytes", 8388608), "export.multipart_part_bytes"
        )
        self.overshoot_tolerance = float(str(export.get("overshoot_tolerance", 0.05)))
        if not 0 <= self.overshoot_tolerance <= 1:
            raise ValueError("export.overshoot_tolerance must be between 0 and 1.")
        self.statement_timeout_ms = positive_int(
            export.get("statement_timeout_ms", 0), "export.statement_timeout_ms", allow_zero=True
        )
        self.padding = positive_int(export.get("part_name_padding", 5), "export.part_name_padding")

        self.bucket = str(self.s3.get("bucket") or "").strip()
        self.prefix = str(self.s3.get("prefix") or "").strip().strip("/")
        self.region = str(self.s3.get("region") or "").strip()
        self.endpoint_url = str(self.s3.get("endpoint_url") or "").strip()
        self.storage_class = str(self.s3.get("storage_class") or "").strip()
        self.sse = str(self.s3.get("sse") or "").strip()

        self.local_dir = Path(args.local_dir).expanduser().resolve() if args.local_dir else None
        if self.local_dir is None and not self.bucket:
            raise ValueError("s3.bucket is required (or pass --local-dir).")
        if self.local_dir is None and self.multipart_part_bytes < 5 * 1024 * 1024:
            raise ValueError("export.multipart_part_bytes must be at least 5 MiB (S3 multipart minimum).")

    @property
    def bare_table(self) -> str:
        return self.table.split(".")[-1]

    def part_key(self, index: int) -> str:
        name = f"{self.bare_table}_{index:0{self.padding}d}.{SUFFIXES[self.format]}"
        return f"{self.prefix}/{name}" if self.prefix else name


# --------------------------------------------------------------------------- postgres


def connect_postgres(pg: dict[str, Any], statement_timeout_ms: int) -> Any:
    timeout = positive_int(pg.get("connect_timeout", 15), "postgres.connect_timeout")
    dsn = os.getenv("POSTGRES_DSN") or pg.get("dsn")
    if dsn:
        connection = psycopg2.connect(str(dsn), connect_timeout=timeout)
    else:
        arguments = {"connect_timeout": timeout, "application_name": "postgres_table_to_s3"}
        for key, environment, default in [
            ("host", "PGHOST", "localhost"), ("port", "PGPORT", 5432),
            ("dbname", "PGDATABASE", ""), ("user", "PGUSER", ""),
            ("password", "PGPASSWORD", ""), ("sslmode", "PGSSLMODE", ""),
        ]:
            value = os.getenv(environment) or pg.get("database" if key == "dbname" else key, default)
            if value not in (None, ""):
                arguments[key] = value
        if "dbname" not in arguments:
            raise ValueError("Set PGDATABASE or postgres.database, or provide POSTGRES_DSN.")
        connection = psycopg2.connect(**arguments)

    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SET client_encoding TO 'UTF8'")
        if statement_timeout_ms:
            cursor.execute("SET statement_timeout = %s", (statement_timeout_ms,))
    return connection


def resolve_columns(connection: Any, settings: Settings) -> list[str]:
    """Fixed column list, so every part has an identical CSV header."""
    if settings.columns:
        for column in settings.columns:
            quote_identifier(column)
        return settings.columns

    parts = settings.table.split(".")
    schema, table = (parts[0], parts[1]) if len(parts) == 2 else ("public", parts[0])
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s
               ORDER BY ordinal_position""",
            (schema, table),
        )
        columns = [row[0] for row in cursor.fetchall()]
    if not columns:
        raise ValueError(f"No columns found for {settings.table}. Check export.source_table.")
    return columns


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return psycopg2.extensions.adapt(value).getquoted().decode()


def _filters(settings: Settings, last_key: Any, upper_key: Any) -> str:
    """Build the WHERE clause, optionally bounded by the chunk keys."""
    clauses = []
    resume = quote_identifier(settings.resume_column)
    if last_key is not None:
        clauses.append(f"{resume} > {_literal(last_key)}")
    if upper_key is not None:
        clauses.append(f"{resume} <= {_literal(upper_key)}")
    if settings.where:
        clauses.append(f"({settings.where})")
    return " AND ".join(clauses) if clauses else "TRUE"


def find_upper_key(cursor: Any, settings: Settings, last_key: Any, rows: int) -> Any:
    """Key of the rows-th row after last_key, or None when the table is exhausted."""
    cursor.execute(
        f"""SELECT {quote_identifier(settings.resume_column)} FROM {settings.table_ident}
            WHERE {_filters(settings, last_key, None)}
            ORDER BY {quote_identifier(settings.resume_column)}
            OFFSET {max(rows - 1, 0)} LIMIT 1"""
    )
    row = cursor.fetchone()
    return row[0] if row else None


def find_max_key(cursor: Any, settings: Settings, last_key: Any) -> Any:
    cursor.execute(
        f"SELECT max({quote_identifier(settings.resume_column)}) FROM {settings.table_ident} "
        f"WHERE {_filters(settings, last_key, None)}"
    )
    row = cursor.fetchone()
    return row[0] if row else None


def count_rows(cursor: Any, settings: Settings, last_key: Any, upper_key: Any) -> int:
    cursor.execute(
        f"SELECT count(*) FROM {settings.table_ident} WHERE {_filters(settings, last_key, upper_key)}"
    )
    return int(cursor.fetchone()[0])


def build_copy_sql(settings: Settings, columns: list[str], last_key: Any, upper_key: Any) -> str:
    select_list = ", ".join(quote_identifier(column) for column in columns)
    order = quote_identifier(settings.resume_column)
    base = (
        f"SELECT {select_list} FROM {settings.table_ident} "
        f"WHERE {_filters(settings, last_key, upper_key)} "
        f"ORDER BY {order}"
    )
    if settings.format == "jsonl":
        return f"COPY (SELECT row_to_json(t) FROM ({base}) t) TO STDOUT"
    options = ["FORMAT csv", "NULL ''"]
    if settings.header:
        options.append("HEADER true")
    return f"COPY ({base}) TO STDOUT WITH ({', '.join(options)})"


# --------------------------------------------------------------------------- sinks


class LocalSink:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "parts").mkdir(exist_ok=True)

    @property
    def location(self) -> str:
        return str(self.directory)

    def open_part(self, key: str, content_type: str) -> "LocalPartWriter":
        return LocalPartWriter(self.directory / "parts" / Path(key).name)

    def get_manifest(self) -> dict[str, Any] | None:
        path = self.directory / MANIFEST_NAME
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put_manifest(self, manifest: dict[str, Any]) -> None:
        path = self.directory / MANIFEST_NAME
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temporary.replace(path)


class S3Sink:
    def __init__(self, settings: Settings) -> None:
        import boto3  # imported lazily so --local-dir works without AWS deps configured

        self.bucket = settings.bucket
        self.prefix = settings.prefix
        self.storage_class = settings.storage_class
        self.sse = settings.sse
        self.part_size = settings.multipart_part_bytes
        self.client = boto3.client(
            "s3",
            region_name=settings.region or None,
            endpoint_url=settings.endpoint_url or None,
        )

    @property
    def location(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}"

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def open_part(self, key: str, content_type: str) -> "S3MultipartWriter":
        extra: dict[str, Any] = {"ContentType": content_type}
        if self.storage_class:
            extra["StorageClass"] = self.storage_class
        if self.sse:
            extra["ServerSideEncryption"] = self.sse
        return S3MultipartWriter(
            client=self.client,
            bucket=self.bucket,
            key=key,
            part_size=self.part_size,
            extra=extra,
        )

    def get_manifest(self) -> dict[str, Any] | None:
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(MANIFEST_NAME))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return json.loads(response["Body"].read().decode("utf-8"))

    def put_manifest(self, manifest: dict[str, Any]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(MANIFEST_NAME),
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )


# --------------------------------------------------------------------------- export loop


class PartTooLarge(Exception):
    """Raised mid-COPY when a part grows past its ceiling, before anything is committed."""

    def __init__(self, bytes_written: int, rows: int) -> None:
        super().__init__(f"part exceeded its size ceiling after {bytes_written} bytes")
        self.bytes_written = bytes_written
        self.rows = rows


class CountingWriter:
    """Counts uncompressed bytes and rows, and stops a runaway part early."""

    def __init__(self, raw: Any, limit_bytes: int = 0) -> None:
        self.raw = raw
        self.limit_bytes = limit_bytes
        self.bytes_written = 0
        self.rows = 0

    def write(self, data: bytes) -> int:
        self.bytes_written += len(data)
        self.rows += data.count(b"\n")
        if self.limit_bytes and self.bytes_written > self.limit_bytes:
            raise PartTooLarge(self.bytes_written, self.rows)
        return self.raw.write(data)

    def flush(self) -> None:
        self.raw.flush()


class LocalPartWriter:
    """Writes a part to a local file; used only by --local-dir."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("wb")
        self._sha = hashlib.sha256()
        self.bytes_written = 0

    def write(self, data: bytes) -> int:
        self._sha.update(data)
        self.bytes_written += len(data)
        return self._handle.write(data)

    def flush(self) -> None:
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def abort(self) -> None:
        try:
            self._handle.close()
        finally:
            self.path.unlink(missing_ok=True)

    def hexdigest(self) -> str:
        return self._sha.hexdigest()


class S3MultipartWriter:
    """Streams compressed bytes straight into S3 with a multipart upload.

    Nothing is staged on local disk: bytes go from the COPY stream into a bounded
    in-memory buffer of at most `part_size`, and each full buffer becomes one S3
    part. Local disk use is therefore zero at any table size.
    """

    MIN_PART_BYTES = 5 * 1024 * 1024

    def __init__(self, client: Any, bucket: str, key: str, part_size: int, extra: dict[str, Any]) -> None:
        self.client = client
        self.bucket = bucket
        self.key = key
        self.part_size = max(part_size, self.MIN_PART_BYTES)
        self.extra = extra
        self.bytes_written = 0
        self._sha = hashlib.sha256()
        self._buffer = bytearray()
        self._upload_id: str | None = None
        self._parts: list[dict[str, Any]] = []
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("write() on a closed part")
        self._sha.update(data)
        self.bytes_written += len(data)
        self._buffer += data
        while len(self._buffer) >= self.part_size:
            self._upload_buffered_bytes(self.part_size)
        return len(data)

    def _ensure_upload(self) -> None:
        if self._upload_id is None:
            response = self.client.create_multipart_upload(Bucket=self.bucket, Key=self.key, **self.extra)
            self._upload_id = response["UploadId"]

    def _upload_buffered_bytes(self, size: int) -> None:
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        self._ensure_upload()
        number = len(self._parts) + 1
        response = self.client.upload_part(
            Bucket=self.bucket, Key=self.key, UploadId=self._upload_id,
            PartNumber=number, Body=chunk,
        )
        self._parts.append({"PartNumber": number, "ETag": response["ETag"]})

    def flush(self) -> None:
        """No-op on purpose: uploading a short part would break the 5 MiB minimum."""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._upload_id is None:
            # Whole part fits in one buffer -> a single PUT needs no multipart.
            self.client.put_object(Bucket=self.bucket, Key=self.key, Body=bytes(self._buffer), **self.extra)
            self._buffer.clear()
            return
        if self._buffer:
            self._upload_buffered_bytes(len(self._buffer))  # the last part may be short
        self.client.complete_multipart_upload(
            Bucket=self.bucket, Key=self.key, UploadId=self._upload_id,
            MultipartUpload={"Parts": self._parts},
        )

    def abort(self) -> None:
        self._closed = True
        self._buffer.clear()
        if self._upload_id is not None:
            try:
                self.client.abort_multipart_upload(Bucket=self.bucket, Key=self.key, UploadId=self._upload_id)
            finally:
                self._upload_id = None

    def hexdigest(self) -> str:
        return self._sha.hexdigest()


class GzipWriter:
    """Minimal gzip encoder over zlib.

    Used instead of gzip.GzipFile because there is no clean way to abandon a
    half-written GzipFile: its finalizer writes a trailer into the part we are
    about to abort. This wrapper has no finalizer; you either call finish() or you
    drop it, and nothing is written either way.
    """

    def __init__(self, target: Any, level: int) -> None:
        self.target = target
        self._compressor = zlib.compressobj(level, zlib.DEFLATED, 16 + zlib.MAX_WBITS)

    def write(self, data: bytes) -> int:
        chunk = self._compressor.compress(data)
        if chunk:
            self.target.write(chunk)
        return len(data)

    def flush(self) -> None:
        """No-op: flushing here would emit a partial deflate block."""

    def finish(self) -> None:
        tail = self._compressor.flush()
        if tail:
            self.target.write(tail)


def stream_part(connection: Any, settings: Settings, writer: Any, sql: str, limit_bytes: int) -> tuple[int, int, str]:
    """COPY -> gzip -> writer, with no intermediate file.

    Returns (uncompressed bytes, stored bytes, sha256 of the stored bytes).
    """
    stream: Any = writer
    if settings.compress:
        stream = GzipWriter(writer, settings.gzip_level)
    counter = CountingWriter(stream, limit_bytes)
    try:
        with connection.cursor() as cursor:
            cursor.copy_expert(sql, counter)
    except PartTooLarge:
        raise  # nothing to unwind; the caller aborts the part
    if settings.compress:
        stream.finish()
    return counter.bytes_written, writer.bytes_written, writer.hexdigest()


def new_manifest(settings: Settings, columns: list[str]) -> dict[str, Any]:
    return {
        "version": 1,
        "source": {
            "table": settings.table,
            "format": settings.format,
            "resume_column": settings.resume_column,
            "columns": columns,
            "where": settings.where,
        },
        "target": {"location": "", "prefix": settings.prefix, "bucket": settings.bucket},
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "completed_at": None,
        "parts": [],
        "totals": {"parts": 0, "rows": 0, "bytes": 0, "bytes_stored": 0},
        "last_key": None,
    }


def manifest_is_compatible(manifest: dict[str, Any], settings: Settings, columns: list[str]) -> bool:
    source = manifest.get("source", {})
    return (
        source.get("table") == settings.table
        and source.get("format") == settings.format
        and source.get("resume_column") == settings.resume_column
        and source.get("columns") == columns
        and (source.get("where") or "") == settings.where
    )


def format_bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TiB"


def export_parts(args: argparse.Namespace, settings: Settings, connection: Any, sink: Any, columns: list[str]) -> int:
    manifest = None if args.restart else sink.get_manifest()
    if manifest and not manifest_is_compatible(manifest, settings, columns):
        LOG.error("Existing manifest was written with different settings; re-run with --restart.")
        return 2
    if manifest:
        LOG.info(
            "Resuming: %s part(s), %s row(s), last key %s",
            manifest["totals"]["parts"], f"{manifest['totals']['rows']:,}", manifest["last_key"],
        )
    else:
        manifest = new_manifest(settings, columns)
        LOG.info("Starting a new export of %s -> %s", settings.table, sink.location)

    manifest["target"]["location"] = sink.location
    last_key = manifest["last_key"]
    part_index = manifest["totals"]["parts"] + 1
    batch_rows = settings.batch_rows
    started = time.perf_counter()
    parts_this_run = 0

    with connection.cursor() as cursor:
        while True:
            if args.limit_parts and parts_this_run >= args.limit_parts:
                LOG.info("Stopping after %s part(s) as requested.", parts_this_run)
                break

            attempts = 0
            while True:
                attempts += 1
                upper_key = find_upper_key(cursor, settings, last_key, batch_rows)
                if upper_key is None:
                    rows = count_rows(cursor, settings, last_key, None)
                    chunk_last_key = find_max_key(cursor, settings, last_key)
                else:
                    rows = batch_rows
                    chunk_last_key = upper_key
                if rows == 0:
                    manifest["status"] = "completed"
                    break

                sql = build_copy_sql(settings, columns, last_key, upper_key)
                key = settings.part_key(part_index)
                part_started = time.perf_counter()

                # Stream straight into S3: no part file, no temp directory.
                writer = sink.open_part(key, CONTENT_TYPES[settings.format])
                limit_bytes = 0 if attempts > 5 else int(
                    settings.max_part_bytes * (1 + settings.overshoot_tolerance)
                )
                try:
                    uncompressed, stored, checksum = stream_part(
                        connection, settings, writer, sql, limit_bytes
                    )
                except PartTooLarge as exc:
                    writer.abort()
                    rows_per_byte = exc.rows / max(exc.bytes_written, 1)
                    batch_rows = max(1, int(settings.max_part_bytes * rows_per_byte * 0.95))
                    LOG.warning(
                        "Part %s exceeded %s after %s row(s); retrying the same key range with %s rows.",
                        f"{part_index:0{settings.padding}d}", format_bytes(settings.max_part_bytes),
                        f"{exc.rows:,}", f"{batch_rows:,}",
                    )
                    continue
                except BaseException:
                    writer.abort()
                    raise
                writer.close()
                elapsed = max(time.perf_counter() - part_started, 1e-9)

                if rows > 0 and uncompressed == 0:
                    LOG.error(
                        "Chunk reported %s row(s) but produced no output. Export aborted at key %s; "
                        "check that export.resume_column is unique.",
                        f"{rows:,}", last_key,
                    )
                    return 2

                manifest["parts"].append({
                    "index": part_index,
                    "key": key,
                    "rows": rows,
                    "bytes": uncompressed,
                    "bytes_stored": stored,
                    "after_key": last_key,
                    "last_key": chunk_last_key,
                    "sha256": checksum,
                })
                manifest["totals"]["parts"] = part_index
                manifest["totals"]["rows"] += rows
                manifest["totals"]["bytes"] += uncompressed
                manifest["totals"]["bytes_stored"] += stored
                manifest["last_key"] = chunk_last_key
                manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                if upper_key is None:
                    manifest["status"] = "completed"
                    manifest["completed_at"] = manifest["updated_at"]

                sink.put_manifest(manifest)

                LOG.info(
                    "part %s | rows %s (+%s) | %s -> %s stored | %s rows/s | %s/s | %s",
                    f"{part_index:0{settings.padding}d}",
                    f"{manifest['totals']['rows']:,}",
                    f"{rows:,}",
                    format_bytes(uncompressed),
                    format_bytes(stored),
                    f"{int(rows / elapsed):,}",
                    format_bytes(uncompressed / elapsed),
                    key,
                )

                part_index += 1
                parts_this_run += 1
                if args.limit_parts and parts_this_run >= args.limit_parts:
                    LOG.info("Stopping after %s part(s) as requested; re-run to resume.", parts_this_run)
                    break
                if upper_key is None:
                    break
                last_key = upper_key
                if uncompressed > 0 and rows == batch_rows:
                    rows_per_byte = rows / uncompressed
                    batch_rows = max(1, int(settings.max_part_bytes * rows_per_byte * 0.95))

            if manifest["status"] == "completed":
                break

    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    sink.put_manifest(manifest)

    elapsed = max(time.perf_counter() - started, 1e-9)
    LOG.info(
        "Done | status=%s | parts=%s | rows=%s | %s -> %s stored | %s rows/s | %s/s",
        manifest["status"],
        manifest["totals"]["parts"],
        f"{manifest['totals']['rows']:,}",
        format_bytes(manifest["totals"]["bytes"]),
        format_bytes(manifest["totals"]["bytes_stored"]),
        f"{int(manifest['totals']['rows'] / elapsed):,}" if parts_this_run else "0",
        format_bytes(manifest["totals"]["bytes"] / elapsed) if parts_this_run else "0 B",
    )
    if manifest["status"] == "completed":
        LOG.info("Manifest: %s/%s", sink.location, MANIFEST_NAME)
    else:
        LOG.info("Export not finished. Re-run the same command to resume from part %s.", part_index)
    return 0


def print_status(sink: Any) -> int:
    manifest = sink.get_manifest()
    if not manifest:
        print(f"No manifest at {sink.location}/{MANIFEST_NAME}")
        return 1
    print(f"table     : {manifest['source']['table']}")
    print(f"format    : {manifest['source']['format']}")
    print(f"status    : {manifest['status']}")
    print(f"parts     : {manifest['totals']['parts']}")
    print(f"rows      : {manifest['totals']['rows']:,}")
    print(f"bytes     : {format_bytes(manifest['totals']['bytes'])} -> {format_bytes(manifest['totals']['bytes_stored'])} stored")
    print(f"last key  : {manifest['last_key']}")
    print(f"updated   : {manifest['updated_at']}")
    return 0


def verify(settings: Settings, connection: Any, sink: Any, columns: list[str]) -> int:
    manifest = sink.get_manifest()
    if not manifest:
        print(f"No manifest at {sink.location}/{MANIFEST_NAME}")
        return 1
    if not manifest_is_compatible(manifest, settings, columns):
        print("Manifest was written with different settings.")
        return 1
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {settings.table_ident} WHERE {_filters(settings, None, None)}")
        table_rows = int(cursor.fetchone()[0])
    manifest_rows = manifest["totals"]["rows"]
    print(f"table rows    : {table_rows:,}")
    print(f"manifest rows : {manifest_rows:,}")
    print(f"status        : {manifest['status']}")
    if table_rows == manifest_rows and manifest["status"] == "completed":
        print("MATCH - export is complete and consistent.")
        return 0
    print("MISMATCH - resume the export or investigate the source table.")
    return 2


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    settings = Settings(config, args)

    sink = LocalSink(settings.local_dir) if settings.local_dir else S3Sink(settings)

    if args.status:
        return print_status(sink)

    if args.dry_run:
        print(build_copy_sql(settings, settings.columns or ["<columns resolved at runtime>"], "LAST_KEY", "UPPER_KEY"))
        print(f"-- target: {sink.location}")
        return 0

    connection = connect_postgres(settings.postgres, settings.statement_timeout_ms)
    try:
        columns = resolve_columns(connection, settings)
        if args.verify:
            return verify(settings, connection, sink, columns)
        LOG.info("Table %s | format=%s | columns=%s | part limit=%s",
                 settings.table, settings.format, len(columns), format_bytes(settings.max_part_bytes))
        return export_parts(args, settings, connection, sink, columns)
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
