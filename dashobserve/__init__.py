"""
DashObserve — Notebook-native data observability for Databricks: freshness,
volume, and schema-change monitoring, plus next-update prediction and volume
forecasting. Launch the UI with dashobserve.launch() inside a Databricks notebook.
"""
from dashobserve.monitors import (
    MonitorResult, check_freshness, check_schema, check_volume, diff_schema,
    predict_next_update, predict_volume,
)
from dashobserve.runner import MonitorConfig, MonitorReport, run_monitors, ForecastReport, run_forecast
from dashobserve.ui import env_setup, launch

__version__ = "0.1.5"
__all__ = [
    "MonitorConfig",
    "MonitorReport",
    "MonitorResult",
    "ForecastReport",
    "run_monitors",
    "run_forecast",
    "check_freshness",
    "check_volume",
    "check_schema",
    "diff_schema",
    "predict_next_update",
    "predict_volume",
    "env_setup",
    "launch",
]
