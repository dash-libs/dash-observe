"""Unit tests for MonitorConfig/MonitorReport (no Spark required)."""
from dashobserve.monitors import MonitorResult
from dashobserve.runner import MonitorConfig, MonitorReport


def test_monitor_config_defaults():
    cfg = MonitorConfig(table="cat.sch.t")
    assert cfg.freshness_column is None
    assert cfg.track_schema is False


def test_monitor_report_summary():
    results = [
        MonitorResult("cat.sch.t", "freshness", "data_freshness", "PASS", "ok"),
        MonitorResult("cat.sch.t", "volume", "row_count", "FAIL", "too low"),
    ]
    report = MonitorReport(results)
    summary = report.summary()
    assert summary["total_monitors"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["pass_rate_pct"] == 50.0


def test_monitor_report_empty_summary():
    report = MonitorReport([])
    summary = report.summary()
    assert summary["total_monitors"] == 0
    assert summary["pass_rate_pct"] == 0


def test_monitor_report_to_dict():
    results = [MonitorResult("cat.sch.t", "schema", "schema_change", "PASS", "ok")]
    report = MonitorReport(results)
    d = report.to_dict()
    assert len(d) == 1
    assert d[0]["monitor_type"] == "schema"
