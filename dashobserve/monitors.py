"""
Pure-logic monitor checks — freshness, volume, and schema-change detection.
No Spark/datetime-now dependency baked in, so every function here is testable
with plain Python values; the Spark-touching glue lives in runner.py.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class MonitorResult:
    table_name: str
    monitor_type: str      # freshness | volume | schema
    monitor_name: str
    status: str             # PASS | FAIL | ERROR
    message: str
    run_timestamp: str = ""
    details: str = "{}"     # json-encoded dict of monitor-specific details

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def check_freshness(latest_timestamp, max_staleness_minutes: float, now: datetime = None) -> tuple[bool, str]:
    """Most recent value in the freshness column must be within max_staleness_minutes of now."""
    if latest_timestamp is None:
        return False, "No timestamp values found — table may be empty"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if getattr(latest_timestamp, "tzinfo", None) is not None:
        latest_timestamp = latest_timestamp.replace(tzinfo=None)
    staleness_minutes = (now - latest_timestamp).total_seconds() / 60
    ok = staleness_minutes <= max_staleness_minutes
    msg = f"Data is {staleness_minutes:.1f} min old (threshold {max_staleness_minutes} min)"
    return ok, msg


def check_volume(row_count: int, min_rows: int = None, max_rows: int = None,
                  baseline_avg: float = None, tolerance_pct: float = None) -> tuple[bool, str]:
    """Row count must satisfy absolute bounds and/or stay within tolerance_pct of a historical baseline."""
    if min_rows is not None and row_count < min_rows:
        return False, f"Row count {row_count} below min_rows {min_rows}"
    if max_rows is not None and row_count > max_rows:
        return False, f"Row count {row_count} above max_rows {max_rows}"
    if baseline_avg is not None and tolerance_pct is not None and baseline_avg > 0:
        deviation_pct = abs(row_count - baseline_avg) / baseline_avg * 100
        if deviation_pct > tolerance_pct:
            return False, (
                f"Row count {row_count} deviates {deviation_pct:.1f}% from baseline "
                f"{baseline_avg:.0f} (tolerance {tolerance_pct}%)"
            )
    return True, f"Row count {row_count} within expected bounds"


def diff_schema(old_schema: dict, new_schema: dict) -> dict:
    """Compare two {column_name: dtype_string} schemas. Pure set/dict logic, no I/O."""
    old_cols, new_cols = set(old_schema), set(new_schema)
    added = sorted(new_cols - old_cols)
    removed = sorted(old_cols - new_cols)
    type_changed = sorted(c for c in (old_cols & new_cols) if old_schema[c] != new_schema[c])
    return {"added": added, "removed": removed, "type_changed": type_changed}


def check_schema(old_schema: dict, new_schema: dict) -> tuple[bool, str, dict]:
    """old_schema=None means no prior snapshot exists yet — treated as a baseline, not a failure."""
    if old_schema is None:
        return True, "Initial schema snapshot recorded", {"added": [], "removed": [], "type_changed": []}

    diff = diff_schema(old_schema, new_schema)
    changed = diff["added"] or diff["removed"] or diff["type_changed"]
    if not changed:
        return True, "No schema changes detected", diff

    parts = []
    if diff["added"]:
        parts.append(f"added: {', '.join(diff['added'])}")
    if diff["removed"]:
        parts.append(f"removed: {', '.join(diff['removed'])}")
    if diff["type_changed"]:
        parts.append(f"type changed: {', '.join(diff['type_changed'])}")
    return False, "Schema changed — " + "; ".join(parts), diff
