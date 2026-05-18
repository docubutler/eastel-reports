# PostgreSQL To Mongo Syncs

This folder groups the PostgreSQL-to-Mongo sync flows by domain.

## Subprojects

- `postgres-to-mongo-usage-sync`
  Usage-log sync flow, collection setup, and local config.
- `postgres-to-mongo-request-sync`
  Request-log sync flow, collection setup, and local config.

Each subfolder is intended to be runnable on its own and keeps its own:

- `README.md`
- `requirements.txt`
- `config-sample.yml`
- local `config.yml`

Keep shared helpers out of this parent folder unless they are truly used by both flows.
