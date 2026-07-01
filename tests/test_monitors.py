"""Unit tests for the pure-logic monitor checks and forecasting (no Spark required)."""
from datetime import datetime, timedelta

from dashobserve.monitors import (
    check_freshness, check_schema, check_volume, diff_schema,
    predict_next_update, predict_volume,
)


# ── freshness ────────────────────────────────────────────────────────────

def test_freshness_passes_when_recent():
    now = datetime(2026, 1, 1, 12, 0, 0)
    latest = now - timedelta(minutes=30)
    ok, msg = check_freshness(latest, max_staleness_minutes=60, now=now)
    assert ok is True
    assert "30.0 min old" in msg


def test_freshness_fails_when_stale():
    now = datetime(2026, 1, 1, 12, 0, 0)
    latest = now - timedelta(hours=5)
    ok, msg = check_freshness(latest, max_staleness_minutes=60, now=now)
    assert ok is False
    assert "300.0 min old" in msg


def test_freshness_fails_when_no_data():
    ok, msg = check_freshness(None, max_staleness_minutes=60)
    assert ok is False
    assert "No timestamp values" in msg


def test_freshness_handles_tz_aware_timestamp():
    from datetime import timezone
    now = datetime(2026, 1, 1, 12, 0, 0)
    latest = (now - timedelta(minutes=10)).replace(tzinfo=timezone.utc)
    ok, msg = check_freshness(latest, max_staleness_minutes=60, now=now)
    assert ok is True


# ── volume ───────────────────────────────────────────────────────────────

def test_volume_passes_within_bounds():
    ok, msg = check_volume(500, min_rows=100, max_rows=1000)
    assert ok is True


def test_volume_fails_below_min():
    ok, msg = check_volume(50, min_rows=100)
    assert ok is False
    assert "below min_rows" in msg


def test_volume_fails_above_max():
    ok, msg = check_volume(5000, max_rows=1000)
    assert ok is False
    assert "above max_rows" in msg


def test_volume_passes_within_baseline_tolerance():
    ok, msg = check_volume(105, baseline_avg=100, tolerance_pct=20)
    assert ok is True


def test_volume_fails_outside_baseline_tolerance():
    ok, msg = check_volume(50, baseline_avg=100, tolerance_pct=20)
    assert ok is False
    assert "deviates" in msg


def test_volume_no_bounds_configured_always_passes():
    ok, msg = check_volume(123456)
    assert ok is True


# ── schema diff ──────────────────────────────────────────────────────────

def test_diff_schema_detects_added_column():
    diff = diff_schema({"a": "string"}, {"a": "string", "b": "int"})
    assert diff == {"added": ["b"], "removed": [], "type_changed": []}


def test_diff_schema_detects_removed_column():
    diff = diff_schema({"a": "string", "b": "int"}, {"a": "string"})
    assert diff == {"added": [], "removed": ["b"], "type_changed": []}


def test_diff_schema_detects_type_change():
    diff = diff_schema({"a": "string"}, {"a": "int"})
    assert diff == {"added": [], "removed": [], "type_changed": ["a"]}


def test_diff_schema_no_changes():
    diff = diff_schema({"a": "string"}, {"a": "string"})
    assert diff == {"added": [], "removed": [], "type_changed": []}


def test_check_schema_initial_snapshot_passes():
    ok, msg, diff = check_schema(None, {"a": "string"})
    assert ok is True
    assert "Initial schema snapshot" in msg


def test_check_schema_no_changes_passes():
    ok, msg, diff = check_schema({"a": "string"}, {"a": "string"})
    assert ok is True
    assert "No schema changes" in msg


def test_check_schema_changes_fail_with_details():
    ok, msg, diff = check_schema({"a": "string"}, {"a": "string", "b": "int"})
    assert ok is False
    assert "added: b" in msg
    assert diff["added"] == ["b"]


def test_monitor_result_to_dict():
    from dashobserve.monitors import MonitorResult
    r = MonitorResult("cat.sch.t", "freshness", "data_freshness", "PASS", "ok")
    d = r.to_dict()
    assert d["table_name"] == "cat.sch.t"
    assert d["status"] == "PASS"


# ── predict_next_update ──────────────────────────────────────────────────

def test_predict_next_update_daily_pattern():
    base = datetime(2026, 1, 1)
    timestamps = [base + timedelta(days=i) for i in range(7)]
    result = predict_next_update(timestamps)
    assert result["predicted_next_update"] is not None
    assert result["pattern"] == "daily"
    assert abs(result["avg_interval_hours"] - 24.0) < 0.1


def test_predict_next_update_weekly_pattern():
    base = datetime(2026, 1, 1)
    timestamps = [base + timedelta(weeks=i) for i in range(5)]
    result = predict_next_update(timestamps)
    assert result["pattern"] == "weekly"
    assert abs(result["avg_interval_hours"] - 168.0) < 0.1


def test_predict_next_update_predicts_correct_time():
    base = datetime(2026, 1, 1, 0, 0, 0)
    # 4 timestamps: 0h, 6h, 12h, 18h — avg interval = 6h, last = 18h, next = 24h
    timestamps = [base + timedelta(hours=6 * i) for i in range(4)]
    result = predict_next_update(timestamps)
    assert result["predicted_next_update"] == "2026-01-02T00:00:00"


def test_predict_next_update_insufficient_data():
    result = predict_next_update([datetime(2026, 1, 1)])
    assert result["predicted_next_update"] is None
    assert result["pattern"] == "insufficient_data"
    assert result["history_points"] == 1


def test_predict_next_update_empty():
    result = predict_next_update([])
    assert result["predicted_next_update"] is None
    assert result["history_points"] == 0


# ── predict_volume ───────────────────────────────────────────────────────

def test_predict_volume_linear_growth():
    base = datetime(2026, 1, 1)
    history = [(base + timedelta(weeks=i), 1000 + i * 100) for i in range(5)]
    projections = predict_volume(history, n_periods=3, period="weeks")
    assert len(projections) == 3
    assert projections[0]["period_label"] == "+1 weeks"
    assert projections[0]["predicted_row_count"] > 1400


def test_predict_volume_flat():
    base = datetime(2026, 1, 1)
    history = [(base + timedelta(days=i), 5000) for i in range(6)]
    projections = predict_volume(history, n_periods=2, period="days")
    assert projections[0]["predicted_row_count"] == 5000
    assert projections[0]["lower_bound"] <= 5000 <= projections[0]["upper_bound"]


def test_predict_volume_months_period():
    base = datetime(2026, 1, 1)
    history = [(base + timedelta(days=30 * i), 10000 + i * 500) for i in range(4)]
    projections = predict_volume(history, n_periods=2, period="months")
    assert projections[1]["period_label"] == "+2 months"
    assert all(p["lower_bound"] <= p["predicted_row_count"] <= p["upper_bound"] for p in projections)


def test_predict_volume_insufficient_history():
    history = [(datetime(2026, 1, 1), 1000)]
    assert predict_volume(history, n_periods=4, period="weeks") == []


def test_predict_volume_invalid_period():
    import pytest
    history = [(datetime(2026, 1, 1), 1000), (datetime(2026, 1, 8), 1100)]
    with pytest.raises(ValueError, match="period must be one of"):
        predict_volume(history, period="quarters")
