from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from hlr_reconciliation.core.exceptions import TransferError
from hlr_reconciliation.models.config import TransferConfig


class SftpTransferClient:
    def __init__(self, config: TransferConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def download_latest(self) -> Path:
        import paramiko

        self.config.local_download_directory.mkdir(parents=True, exist_ok=True)
        transport = None
        try:
            transport = paramiko.Transport((self.config.host, self.config.port))
            transport.banner_timeout = self.config.timeout_seconds
            transport.connect(username=self.config.username, password=self.config.password)
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                entries = sftp.listdir_attr(self.config.remote_directory)
                matches = [
                    entry for entry in entries if fnmatch.fnmatch(entry.filename, self.config.file_pattern)
                ]
                if not matches:
                    raise TransferError("No HLR archive matched configured SFTP pattern")
                latest = max(matches, key=lambda entry: entry.st_mtime)
                remote = f"{self.config.remote_directory.rstrip('/')}/{latest.filename}"
                target = self.config.local_download_directory / latest.filename
                sftp.get(remote, str(target))
                self.logger.info("Downloaded SFTP HLR archive %s", latest.filename)
                return target
        except TransferError:
            raise
        except Exception as exc:
            raise TransferError("SFTP HLR download failed") from exc
        finally:
            if transport is not None:
                transport.close()
