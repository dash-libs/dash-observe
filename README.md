# DashObserve — Databricks Library

[![CI](https://github.com/dash-libs/dash-observe/actions/workflows/ci.yml/badge.svg)](https://github.com/dash-libs/dash-observe/actions)
[![PyPI](https://img.shields.io/pypi/v/dash-observe)](https://pypi.org/project/dash-observe/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

Part of the **[Dashlibs](https://github.com/dash-libs)** suite — Databricks libraries built for business users.

Monte Carlo-style data observability that runs natively in a Databricks notebook —
no external service, no agent to deploy. v1 covers:

- **Freshness monitoring** — alert when a table's most recent timestamp value is older than expected
- **Volume monitoring** — alert on row-count bounds, or on deviation from a rolling historical baseline
- **Schema-change detection** — alert when columns are added, removed, or change type since the last run

All monitor results are appended to a Delta history table, which also feeds the volume
baseline and schema-diff comparisons for future runs.

## Installation

```bash
%pip install dash-observe
```

## Quick Start

```python
import dashobserve
dashobserve.launch()   # Opens interactive UI in your Databricks notebook
```

## What it looks like

![DashObserve UI](https://raw.githubusercontent.com/dash-libs/dash-observe/main/docs/screenshots/launch.png)

## Python API

```python
from dashobserve import MonitorConfig, run_monitors

cfg = MonitorConfig(
    table="catalog.schema.orders",
    freshness_column="updated_at", max_staleness_minutes=60,
    min_rows=1000, volume_tolerance_pct=20,
    track_schema=True,
)
report = run_monitors(cfg, history_table="catalog.schema.observe_history")
report.display()
print(report.summary())
```

## Part of Dashlibs

| Library | Purpose |
|---|---|
| dash-dq | Data Quality |
| dash-synthetic | Synthetic Data Generation |
| dash-observe | Data Observability (freshness, volume, schema) |
| dash-ml | ML Model Monitoring |
| dash-ingest | Data Ingestion |
| dash-gov | Data Governance |
| dash-relate | Ontology & Lineage for AI |
| dash-ui | Shared UI components (PyPI: `dash-uis`) |

## Quality & Contributing

- 25 unit tests, zero Spark dependency to run them — `pytest tests/ -v`
  (freshness/volume/schema-diff checks are pure Python and fully covered;
  only the Spark/Delta glue in `runner.py` needs a live cluster)
- Lint-clean (`ruff check dashobserve/`), PEP 561 typed (`py.typed`)
- Every change ships through a reviewed pull request; CI (lint → test on
  Python 3.9–3.12 → build) gates every PR and every release
- See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup,
  [CHANGELOG.md](CHANGELOG.md) for release history,
  [SECURITY.md](SECURITY.md) to report a vulnerability, and
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

Apache 2.0
