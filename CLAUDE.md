# CLAUDE.md — dash-observe

Part of the **Dashlibs** suite. See ~/dashlibs for the full context.

## Purpose
Data observability for Databricks — Monte Carlo-style monitoring without leaving the
notebook. v1 covers freshness, volume, and schema-change monitoring. monitors.py=pure-logic
check functions (no Spark, fully unit-testable), runner.py=MonitorConfig/run_monitors()/Delta
history persistence (the Spark-touching glue).

## Structure
- `/ui.py`        — ipywidgets UI (built on `dashui`), `launch()` entrypoint
- `/monitors.py`  — `check_freshness`, `check_volume`, `check_schema`/`diff_schema`, `MonitorResult`
- `/runner.py`    — `MonitorConfig`, `MonitorReport`, `run_monitors()`
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

## Out of scope for v1
Distribution/anomaly monitoring (statistical drift) and lineage/alerting integration were
deliberately deferred — freshness, volume, and schema-change cover the most common pipeline
failure modes and are the fastest to ship correctly.

## CI
- `ci.yml`    — PR gate: lint → test → build
- `daily.yml` — 06:00 UTC: tests + .health/log.txt commit
- `release.yml`— Monday 09:00 UTC: patch bump on a release branch → PR → auto-merge → GitHub release → PyPI
