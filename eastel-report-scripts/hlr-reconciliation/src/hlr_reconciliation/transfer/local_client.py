from __future__ import annotations

import logging
import shutil
from pathlib import Path

from hlr_reconciliation.core.exceptions import TransferError
from hlr_reconciliation.models.config import TransferConfig


class LocalTransferClient:
    def __init__(self, config: TransferConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def download_latest(self) -> Path:
        if self.config.local_source_file is None:
            raise TransferError("transfer.local_source_file is required for local transfer")
        if not self.config.local_source_file.exists():
            raise TransferError(f"Local HLR source file not found: {self.config.local_source_file}")
        self.config.local_download_directory.mkdir(parents=True, exist_ok=True)
        target = self.config.local_download_directory / self.config.local_source_file.name
        shutil.copy2(self.config.local_source_file, target)
        self.logger.info("Copied local HLR archive to %s", target)
        return target
