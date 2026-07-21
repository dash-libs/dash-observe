"""
MonitorConfig + run_monitors() — the Spark-touching glue around the pure
checks in monitors.py. Reads/writes a Delta "history" table so volume
baselines and schema snapshots can be compared run over run.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime

from dashobserve.monitors import (
    MonitorResult, check_freshness, check_schema, check_volume,
    predict_next_update, predict_volume,
)


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
            print(f"[{r.status}] [{r.monitor_type}] {r.table_name} — {r.message}")


def run_monitors(config: MonitorConfig, history_table: str = None, spark=None) -> MonitorReport:
    """Run every monitor configured on config.table and return a MonitorReport."""
    if spark is None:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
    from pyspark.sql import functions as F

    df = spark.table(config.table)
    run_ts = datetime.now().isoformat(timespec="seconds")
    results = []

    if config.max_staleness_minutes is not None:
        if config.freshness_column:
            latest = df.agg(F.max(config.freshness_column)).collect()[0][0]
            source = "column"
        else:
            # No timestamp column needed — Delta table metadata already
            # tracks when the table was last written.
            latest = _table_last_modified(spark, config.table)
            source = "metadata"
        ok, msg = check_freshness(latest, config.max_staleness_minutes)
        if source == "metadata":
            msg += " (via Delta table metadata)"
        results.append(MonitorResult(
            config.table, "freshness", "data_freshness",
            "PASS" if ok else "FAIL", msg, run_ts,
            details=json.dumps({
                "latest_timestamp": latest.isoformat() if latest else None,
                "source": source,
            }),
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


def _table_last_modified(spark, table: str):
    """The Delta table's lastModified timestamp — metadata only, no scan."""
    try:
        return spark.sql(f"DESCRIBE DETAIL {table}").collect()[0]["lastModified"]
    except Exception:
        return None


def discover_tables(schema_scope: str, spark=None) -> list[str]:
    """List every table in a 'catalog.schema' via information_schema — for
    bulk-adding monitors across a whole schema instead of one table at a time."""
    catalog, sep, schema_name = schema_scope.partition(".")
    if not sep:
        raise ValueError(f"schema_scope must be 'catalog.schema', got {schema_scope!r}")
    if spark is None:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
    rows = spark.sql(
        f"SELECT table_name FROM {catalog}.information_schema.tables "
        f"WHERE table_schema = '{schema_name}' ORDER BY table_name"
    ).collect()
    return [f"{catalog}.{schema_name}.{r['table_name']}" for r in rows]


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


class ForecastReport:
    def __init__(self, table: str, next_update: dict, volume_projections: list):
        self.table = table
        self.next_update = next_update
        self.volume_projections = volume_projections

    def summary(self) -> dict:
        return {
            "table": self.table,
            "next_update_pattern": self.next_update["pattern"],
            "predicted_next_update": self.next_update["predicted_next_update"],
            "volume_periods_forecast": len(self.volume_projections),
        }

    def display(self):
        print(f"Next update prediction for {self.table}:")
        if self.next_update["predicted_next_update"]:
            print(f"   Pattern:         {self.next_update['pattern']}")
            print(f"   Avg interval:    {self.next_update['avg_interval_hours']} hours")
            print(f"   Last update:     {self.next_update['last_known_update']}")
            print(f"   Predicted next:  {self.next_update['predicted_next_update']}")
            print(f"   Based on:        {self.next_update['history_points']} observations")
        else:
            print("   Insufficient history — run monitors a few more times first")

        if self.volume_projections:
            print("\nVolume forecast:")
            print(f"   {'Period':<14} {'Date':<14} {'Projected rows':>14}   Range")
            print(f"   {'-'*14} {'-'*14} {'-'*14}   {'-'*24}")
            for p in self.volume_projections:
                rng = f"{p['lower_bound']:,} – {p['upper_bound']:,}"
                print(f"   {p['period_label']:<14} {p['predicted_date']:<14} {p['predicted_row_count']:>14,}   {rng}")
        else:
            print("\nVolume forecast: insufficient history")


def run_forecast(
    table: str,
    history_table: str,
    n_periods: int = 4,
    period: str = "weeks",
    spark=None,
) -> ForecastReport:
    """
    Read historical monitor results and produce next-update and volume forecasts.

    Requires that run_monitors() has been called at least a few times with the
    same history_table so there is enough data to fit a trend.
    """
    if spark is None:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
    from pyspark.sql import functions as F
    from datetime import datetime

    update_timestamps = []
    try:
        rows = (
            spark.table(history_table)
                 .filter((F.col("table_name") == table) & (F.col("monitor_type") == "freshness"))
                 .orderBy("run_timestamp")
                 .select("details")
                 .collect()
        )
        for r in rows:
            try:
                ts_str = json.loads(r["details"]).get("latest_timestamp")
                if ts_str:
                    update_timestamps.append(datetime.fromisoformat(ts_str))
            except Exception:
                continue
    except Exception:
        pass

    volume_history = []
    try:
        rows = (
            spark.table(history_table)
                 .filter((F.col("table_name") == table) & (F.col("monitor_type") == "volume"))
                 .orderBy("run_timestamp")
                 .select("run_timestamp", "details")
                 .collect()
        )
        for r in rows:
            try:
                count = json.loads(r["details"]).get("row_count")
                if count is not None:
                    volume_history.append((r["run_timestamp"], count))
            except Exception:
                continue
    except Exception:
        pass

    return ForecastReport(
        table=table,
        next_update=predict_next_update(update_timestamps),
        volume_projections=predict_volume(volume_history, n_periods=n_periods, period=period),
    )
