# CLAUDE.md — dash-observe

Part of the **Dashlibs** suite. Full suite-wide context (release process
gotchas, PR/review norms, repo list, rationale for past decisions):
see `~/dashlibs/CLAUDE.md`.

## Purpose
Notebook-native data observability for Databricks. Covers freshness, volume, schema-change
monitoring, next-update prediction, and volume forecasting. monitors.py=pure-logic check and
forecast functions (no Spark, fully unit-testable), runner.py=MonitorConfig/run_monitors()/
ForecastReport/run_forecast()/Delta history persistence (the Spark-touching glue).

## Structure
- `/ui.py`        — ipywidgets UI (built on `dashui`), `launch()` entrypoint
- `/monitors.py`  — `check_freshness`, `check_volume`, `check_schema`/`diff_schema`, `predict_next_update`, `predict_volume`, `MonitorResult`
- `/runner.py`    — `MonitorConfig`, `MonitorReport`, `run_monitors()`, `ForecastReport`, `run_forecast()`
- `tests/`        — pytest, no Spark dependency for unit tests

## Key Design Rules
- Never import Spark at module level — always inside functions
- Keep check logic in `monitors.py` pure (plain Python in, plain Python out) so it's testable
  without Spark; `runner.py` is the only place that touches `SparkSession`/Delta
- Volume baselines and schema snapshots are read from the *same* history Delta table that
  `run_monitors()` writes to (`mode("append")`) — there's no separate baseline store
- UI widgets come from the shared `dashui` package (PyPI: `dash-uis`) — don't reimplement
  headers/source pickers/output panels locally
- `launch()` is always the public entrypoint for business users

## Scope
Covers freshness, volume, schema-change monitoring, plus next-update prediction and volume
forecasting (both pure-Python, no Spark, fully unit-tested).

**Explicitly requested next direction (not yet built):** go deep on Unity Catalog / Databricks
SDK integration rather than staying with basic `spark.table()` calls — system tables,
`information_schema`, table properties/tags, audit logs, and especially **lineage** (UC's
native lineage APIs, possibly cross-referencing dash-relate's ontology). Be comprehensive here,
not conservative — this was explicit user direction, not a "nice to have."

## CI
- `ci.yml`    — PR gate: lint → test → build
- `daily.yml` — 06:00 UTC: tests + .health/log.txt commit
- `release.yml`— Monday 09:00 UTC: patch bump on a release branch → PR → GitHub release → PyPI

This repo has no branch protection configured yet, but the same norm applies regardless:
**every change goes through a PR with real human review before merging — no exceptions.**
Don't self-merge, don't push directly to `main`. Prefer small, targeted commits/PRs.
