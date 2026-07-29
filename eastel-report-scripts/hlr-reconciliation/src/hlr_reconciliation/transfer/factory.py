from __future__ import annotations

import logging

from hlr_reconciliation.models.config import TransferConfig
from hlr_reconciliation.transfer.ftp_client import FtpTransferClient
from hlr_reconciliation.transfer.local_client import LocalTransferClient
from hlr_reconciliation.transfer.sftp_client import SftpTransferClient


def build_transfer_client(config: TransferConfig, logger: logging.Logger):
    if config.protocol == "local":
        return LocalTransferClient(config, logger)
    if config.protocol == "ftp":
        return FtpTransferClient(config, logger)
    if config.protocol == "sftp":
        return SftpTransferClient(config, logger)
    raise ValueError(f"Unsupported transfer protocol: {config.protocol}")
