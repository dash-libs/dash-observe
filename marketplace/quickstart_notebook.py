# Databricks notebook source
# MAGIC %md
# MAGIC # dash-observe — Data Observability
# MAGIC
# MAGIC Freshness, volume, and schema-change monitoring for Databricks tables.
# MAGIC
# MAGIC **Install and launch:**

# COMMAND ----------

# MAGIC %pip install dash-observe

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import dashobserve
dashobserve.launch()

# COMMAND ----------
# MAGIC %md
# MAGIC ## Python API (optional — for automation)
# MAGIC
# MAGIC ```python
# MAGIC from dashobserve import MonitorConfig, run_monitors
# MAGIC
# MAGIC cfg = MonitorConfig(
# MAGIC     table="catalog.schema.orders",
# MAGIC     freshness_column="updated_at", max_staleness_minutes=60,
# MAGIC     min_rows=1000, volume_tolerance_pct=20,
# MAGIC     track_schema=True,
# MAGIC )
# MAGIC report = run_monitors(cfg, history_table="catalog.schema.observe_history")
# MAGIC report.display()
# MAGIC ```
