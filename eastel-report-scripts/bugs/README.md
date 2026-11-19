# Bug Database

Defect register for the report scripts in this repository. One file per bug, plus
this index.

## How to use

- Every bug gets a file `BUG-NNN-short-slug.md`, numbered sequentially.
- Add a row to the table below when you create a file.
- Status values: `open`, `investigating`, `fix-proposed`, `fixed`, `wontfix`.
- Severity values: `critical` (silent data loss / wrong reports), `high`
  (blocking failures, recoverable), `medium`, `low`.
- Link to the code with `path:line` so the reference survives review.
- Record evidence, not assumptions. Mark anything unverified as an open question.

## Register

| ID | Title | Severity | Status | Components |
|---|---|---|---|---|
| [BUG-001](BUG-001-sync-skips-rows-inside-settle-window.md) | Sync permanently skips rows excluded by the settle window | critical | fix-proposed | usage sync, request sync |
| [BUG-002](BUG-002-settle-window-never-covers-late-updates.md) | Settle window delays the only copy, so late updates are never synced | high | open | usage sync, request sync |
| [BUG-003](BUG-003-settle-cutoff-timezone-mismatch.md) | Settle cutoff computed in UTC while `cr_time` is server-local | critical | fix-proposed | usage sync, request sync |

`fix-proposed` means the code change exists in the working tree or a commit but has
not been deployed and verified against the live database yet.
