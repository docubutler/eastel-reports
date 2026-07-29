from __future__ import annotations


class HlrReconciliationError(Exception):
    exit_code = 1


class IdempotencyError(HlrReconciliationError):
    exit_code = 10


class ConfigError(HlrReconciliationError):
    exit_code = 11


class TransferError(HlrReconciliationError):
    exit_code = 12


class HlrFileError(HlrReconciliationError):
    exit_code = 13


class SourceDatabaseError(HlrReconciliationError):
    exit_code = 14


class MongoPersistenceError(HlrReconciliationError):
    exit_code = 15


class ReportError(HlrReconciliationError):
    exit_code = 16


class EmailError(HlrReconciliationError):
    exit_code = 17
