"""
Pure-logic monitor checks and forecasting — freshness, volume, schema-change
detection, next-update prediction, and volume trend forecasting.
No Spark/datetime-now dependency baked in; every function is testable with
plain Python values. The Spark-touching glue lives in runner.py.
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


def predict_next_update(update_timestamps: list) -> dict:
    """
    Predict when a table will next be updated based on historical update timestamps.

    update_timestamps: list of datetime objects (when the freshness column last changed).
    Returns dict: predicted_next_update (ISO str), avg_interval_hours, pattern, history_points.
    """
    from datetime import timedelta

    if len(update_timestamps) < 2:
        return {
            "predicted_next_update": None,
            "avg_interval_hours": None,
            "pattern": "insufficient_data",
            "last_known_update": update_timestamps[0].isoformat(timespec="seconds") if update_timestamps else None,
            "history_points": len(update_timestamps),
        }

    sorted_ts = sorted(update_timestamps)
    intervals_h = [
        (sorted_ts[i + 1] - sorted_ts[i]).total_seconds() / 3600
        for i in range(len(sorted_ts) - 1)
    ]
    avg_h = sum(intervals_h) / len(intervals_h)

    pattern = "irregular"
    for threshold_h, label in [
        (1.4,  "hourly"),
        (5.0,  "every few hours"),
        (18.0, "twice daily"),
        (30.0, "daily"),
        (55.0, "every few days"),
        (200.0, "weekly"),
        (400.0, "bi-weekly"),
        (800.0, "monthly"),
    ]:
        if avg_h <= threshold_h:
            pattern = label
            break

    predicted_next = sorted_ts[-1] + timedelta(hours=avg_h)
    return {
        "predicted_next_update": predicted_next.isoformat(timespec="seconds"),
        "avg_interval_hours": round(avg_h, 2),
        "pattern": pattern,
        "last_known_update": sorted_ts[-1].isoformat(timespec="seconds"),
        "history_points": len(sorted_ts),
    }


def predict_volume(history: list, n_periods: int = 4, period: str = "weeks") -> list[dict]:
    """
    Forecast future row counts using a linear trend fitted to historical observations.

    history: list of (datetime_or_isostr, row_count) pairs.
    period: 'days' | 'weeks' | 'months'
    Returns list of dicts: period_label, predicted_date, predicted_row_count,
    lower_bound, upper_bound (95% prediction interval).
    """
    from datetime import datetime, timedelta

    PERIOD_DAYS = {"days": 1, "weeks": 7, "months": 30}
    if period not in PERIOD_DAYS:
        raise ValueError(f"period must be one of {list(PERIOD_DAYS)}, got {period!r}")
    if len(history) < 2:
        return []

    parsed = []
    for ts, count in history:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        parsed.append((ts, int(count)))
    parsed.sort(key=lambda x: x[0])

    t0 = parsed[0][0]
    xs = [(p[0] - t0).total_seconds() / 86400 for p in parsed]
    ys = [p[1] for p in parsed]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom if denom else 0
    intercept = mean_y - slope * mean_x

    residuals = [ys[i] - (intercept + slope * xs[i]) for i in range(n)]
    std_err = (sum(r ** 2 for r in residuals) / max(n - 2, 1)) ** 0.5

    step_days = PERIOD_DAYS[period]
    last_x = xs[-1]
    last_ts = parsed[-1][0]

    projections = []
    for i in range(1, n_periods + 1):
        future_x = last_x + i * step_days
        future_ts = last_ts + timedelta(days=i * step_days)
        predicted = max(0, int(intercept + slope * future_x))
        ci = int(1.96 * std_err)
        projections.append({
            "period": i,
            "period_label": f"+{i} {period}",
            "predicted_date": future_ts.strftime("%Y-%m-%d"),
            "predicted_row_count": predicted,
            "lower_bound": max(0, predicted - ci),
            "upper_bound": predicted + ci,
        })
    return projections


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
