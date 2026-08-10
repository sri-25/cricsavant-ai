# Runbook — Lakebase → Delta CDF Sync

**Job:** `cricsavant-cdf-sync` (definition: `cdf_sync_job.json`)
**What it does:** runs `notebooks/001_sync_change_log_to_delta.py` hourly,
copying new `change_log` rows (watermark-based, idempotent) from Lakebase
into `cricsavant.ops.lb_change_log_history` (Delta). This table powers the
League Analytics audit strip and tool-call analytics.

## Setting it up (Free Edition UI)

1. Workflows → Jobs → **Create Job**.
2. Task: Notebook → point at `notebooks/001_sync_change_log_to_delta.py`
   in the Git folder; serverless compute.
3. Schedule: hourly (`0 0 * * * ?`, UTC) — or paste `cdf_sync_job.json`
   via the Jobs API / "Edit as JSON".
4. Retries: 2, 2-minute interval, retry-on-timeout on, 15-minute task
   timeout, max 1 concurrent run (the watermark makes overlap harmless,
   but there's no reason to allow it).
5. Notifications: on-failure email to the workspace owner.

## Health checks

- **In-app:** League Analytics → "Lakehouse Audit (CDF)" — the
  "Synced to Delta N / M" card shows live-vs-synced counts; lag 0 = healthy.
- **In-workspace:** the Job's run history should show hourly successes;
  `SELECT max(event_id) FROM cricsavant.ops.lb_change_log_history` should
  track Lakebase's `SELECT max(event_id) FROM change_log`.

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Job fails with Postgres auth error | Lakebase OAuth token expiry pattern (the notebook uses the owner identity path) | Re-run once; if persistent, re-issue credentials per SETUP.md §4 |
| Lag grows but job "succeeds" | Watermark table (`ops.sync_watermark`) stuck | Inspect/reset the watermark row, re-run |
| App audit strip errors | App SP lost `ops` schema grant | Re-apply grants per SETUP.md §6 |

Manual catch-up at any time: open the notebook, Run all — idempotency
makes double-runs safe.
