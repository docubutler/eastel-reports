from __future__ import annotations

import tarfile
from pathlib import Path

from hlr_reconciliation.core.exceptions import HlrFileError


def extract_hlr_archive(archive_path: Path, temporary_directory: Path) -> Path:
    if not archive_path.exists():
        raise HlrFileError(f"HLR archive not found: {archive_path}")
    if not archive_path.name.endswith(".tar.gz"):
        raise HlrFileError(f"HLR archive must be a .tar.gz file: {archive_path.name}")

    destination = temporary_directory / archive_path.stem.replace(".tar", "")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getmembers()
            csv_members = [member for member in members if member.isfile() and member.name.lower().endswith(".csv")]
            if len(csv_members) != 1:
                raise HlrFileError("HLR archive must contain exactly one CSV file")
            for member in members:
                target = (destination / member.name).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise HlrFileError(f"Unsafe path in HLR archive: {member.name}")
            tar.extractall(destination)
            return (destination / csv_members[0].name).resolve()
    except tarfile.TarError as exc:
        raise HlrFileError(f"Failed to extract HLR archive: {archive_path}") from exc
