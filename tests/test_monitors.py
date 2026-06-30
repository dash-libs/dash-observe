"""Unit tests for the pure-logic monitor checks (no Spark required)."""
from datetime import datetime, timedelta

from dashobserve.monitors import check_freshness, check_schema, check_volume, diff_schema


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
