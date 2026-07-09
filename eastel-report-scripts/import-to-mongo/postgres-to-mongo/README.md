# PostgreSQL To Mongo Syncs

This folder groups the PostgreSQL-to-Mongo sync flows by domain.

## Subprojects

- `postgres-to-mongo-usage-sync`
  Usage-log sync flow, collection setup, and local config.
- `postgres-to-mongo-request-sync`
  Request-log sync flow, collection setup, and local config.
- `usage-log-backfill`
  One-off repair/backfill tool for `usage_logs`.
- `request-log-backfill`
  One-off repair/backfill tool for `request_logs`.

Each subfolder is intended to be runnable on its own and keeps its own:

- `README.md`
- `config-sample.yml`
- local `config.yml`

Notes:

- The live sync folders are for continuous incremental sync.
- The backfill folders are for one-off correction jobs against existing Mongo documents.
- The live sync folders now support `sync.min_record_age_seconds` to delay syncing very new rows until they are older and more likely to be final.

Keep shared helpers out of this parent folder unless they are truly used by both flows.
