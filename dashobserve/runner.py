"""
MonitorConfig + run_monitors() — the Spark-touching glue around the pure
checks in monitors.py. Reads/writes a Delta "history" table so volume
baselines and schema snapshots can be compared run over run.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime

from dashobserve.monitors import MonitorResult, check_freshness, check_schema, check_volume


@dataclass
class MonitorConfig:
    table: str
    freshness_column: str = None
    max_staleness_minutes: float = None
    min_rows: int = None
    max_rows: int = None
    volume_tolerance_pct: float = None
    track_schema: bool = False


class MonitorReport:
    def __init__(self, results: list):
        self.results = results

    def to_dict(self) -> list:
        return [r.to_dict() for r in self.results]

    def to_pandas(self):
        import pandas as pd
        return pd.DataFrame(self.to_dict())

    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        return {
            "total_monitors": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        }

    def display(self):
        for r in self.results:
            icon = "✅" if r.status == "PASS" else "❌"
            print(f"{icon} [{r.monitor_type}] {r.table_name} — {r.message}")


def run_monitors(config: MonitorConfig, history_table: str = None, spark=None) -> MonitorReport:
    """Run every monitor configured on config.table and return a MonitorReport."""
    if spark is None:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
    from pyspark.sql import functions as F

    df = spark.table(config.table)
    run_ts = datetime.now().isoformat(timespec="seconds")
    results = []

    if config.freshness_column and config.max_staleness_minutes is not None:
        latest = df.agg(F.max(config.freshness_column)).collect()[0][0]
        ok, msg = check_freshness(latest, config.max_staleness_minutes)
        results.append(MonitorResult(
            config.table, "freshness", "data_freshness",
            "PASS" if ok else "FAIL", msg, run_ts,
        ))

    if config.min_rows is not None or config.max_rows is not None or config.volume_tolerance_pct is not None:
        row_count = df.count()
        baseline_avg = None
        if config.volume_tolerance_pct is not None and history_table:
            baseline_avg = _read_volume_baseline(spark, history_table, config.table)
        ok, msg = check_volume(row_count, config.min_rows, config.max_rows, baseline_avg, config.volume_tolerance_pct)
        results.append(MonitorResult(
            config.table, "volume", "row_count",
            "PASS" if ok else "FAIL", msg, run_ts,
            details=json.dumps({"row_count": row_count}),
        ))

    if config.track_schema:
        new_schema = {f.name: str(f.dataType) for f in df.schema.fields}
        old_schema = _read_last_schema(spark, history_table, config.table) if history_table else None
        ok, msg, diff = check_schema(old_schema, new_schema)
        results.append(MonitorResult(
            config.table, "schema", "schema_change",
            "PASS" if ok else "FAIL", msg, run_ts,
            details=json.dumps({"schema": new_schema, "diff": diff}),
        ))

    if history_table and results:
        _save_results(spark, history_table, results)

    return MonitorReport(results)


def _read_volume_baseline(spark, history_table: str, table: str, window: int = 7):
    """Average row_count from the last `window` volume monitor runs for this table."""
    from pyspark.sql import functions as F
    try:
        rows = (
            spark.table(history_table)
                 .filter((F.col("table_name") == table) & (F.col("monitor_type") == "volume"))
                 .orderBy(F.col("run_timestamp").desc())
                 .limit(window)
                 .select("details")
                 .collect()
        )
    except Exception:
        return None
    counts = []
    for r in rows:
        try:
            counts.append(json.loads(r["details"])["row_count"])
        except Exception:
            continue
    return sum(counts) / len(counts) if counts else None


def _read_last_schema(spark, history_table: str, table: str):
    """The most recently saved schema snapshot for this table, or None if there isn't one."""
    from pyspark.sql import functions as F
    try:
        row = (
            spark.table(history_table)
                 .filter((F.col("table_name") == table) & (F.col("monitor_type") == "schema"))
                 .orderBy(F.col("run_timestamp").desc())
                 .limit(1)
                 .select("details")
                 .collect()
        )
    except Exception:
        return None
    if not row:
        return None
    try:
        return json.loads(row[0]["details"])["schema"]
    except Exception:
        return None


def _save_results(spark, history_table: str, results: list):
    rows = [r.to_dict() for r in results]
    (spark.createDataFrame(rows)
          .write.format("delta")
          .mode("append")
          .option("mergeSchema", "true")
          .saveAsTable(history_table))
