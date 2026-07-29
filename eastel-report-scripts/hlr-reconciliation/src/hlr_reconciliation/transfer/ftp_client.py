from __future__ import annotations

import fnmatch
import ftplib
import logging
from pathlib import Path

from hlr_reconciliation.core.exceptions import TransferError
from hlr_reconciliation.models.config import TransferConfig


class FtpTransferClient:
    def __init__(self, config: TransferConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def download_latest(self) -> Path:
        self.config.local_download_directory.mkdir(parents=True, exist_ok=True)
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.config.host, self.config.port, timeout=self.config.timeout_seconds)
                ftp.login(self.config.username, self.config.password)
                ftp.cwd(self.config.remote_directory)
                candidates = [name for name in ftp.nlst() if fnmatch.fnmatch(name, self.config.file_pattern)]
                if not candidates:
                    raise TransferError("No HLR archive matched configured FTP pattern")
                latest = sorted(candidates)[-1]
                target = self.config.local_download_directory / latest
                with target.open("wb") as handle:
                    ftp.retrbinary(f"RETR {latest}", handle.write)
                self.logger.info("Downloaded FTP HLR archive %s", latest)
                return target
        except TransferError:
            raise
        except Exception as exc:
            raise TransferError("FTP HLR download failed") from exc
