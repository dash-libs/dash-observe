"""
DashObserve — Data observability for Databricks: freshness, volume, and
schema-change monitoring. Launch the UI with dashobserve.launch() inside
a Databricks notebook.
"""
from dashobserve.monitors import MonitorResult, check_freshness, check_schema, check_volume, diff_schema
from dashobserve.runner import MonitorConfig, MonitorReport, run_monitors
from dashobserve.ui import launch

__version__ = "0.1.0"
__all__ = [
    "MonitorConfig",
    "MonitorReport",
    "MonitorResult",
    "run_monitors",
    "check_freshness",
    "check_volume",
    "check_schema",
    "diff_schema",
    "launch",
]
