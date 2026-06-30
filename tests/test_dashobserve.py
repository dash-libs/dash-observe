"""Smoke tests for the dashobserve package (no Spark required)."""


def test_import():
    import dashobserve
    assert hasattr(dashobserve, "__version__")


def test_launch_importable():
    from dashobserve import launch
    assert callable(launch)


def test_public_api_importable():
    from dashobserve import MonitorConfig, MonitorReport, run_monitors
    assert MonitorConfig is not None
    assert MonitorReport is not None
    assert callable(run_monitors)
