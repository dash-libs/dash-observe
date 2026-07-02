"""DashObserve interactive UI for Databricks notebooks."""
from __future__ import annotations

_LIBRARY = "dashobserve"


def env_setup() -> None:
    """Open the environment setup panel — where should dashobserve read/write
    its configs? Defaults to the notebook's current working directory if
    never called."""
    try:
        import dashui
        from IPython.display import display
    except ImportError:
        raise RuntimeError("ipywidgets required. Run: %pip install ipywidgets") from None

    display(dashui.card([
        dashui.header("DashObserve — Environment Setup", library=_LIBRARY),
        dashui.env_setup_panel(_LIBRARY).widget,
    ]))


def launch():
    try:
        import ipywidgets as w
        from IPython.display import display
    except ImportError:
        raise RuntimeError("ipywidgets required. Run: %pip install ipywidgets")

    import dashui

    saved = dashui.load_config(_LIBRARY, defaults={"monitors": [], "history_table": ""})
    monitors: list[dict] = list(saved["monitors"])

    # ── Add monitor ───────────────────────────────────────────────────────
    m_table = w.Text(description="UC Table:", placeholder="catalog.schema.table")

    m_freshness_col = w.Text(description="Freshness col:", placeholder="updated_at (optional)")
    m_max_staleness = w.IntText(description="Max staleness (min):", value=1440)

    m_min_rows = w.Text(description="Min rows:", placeholder="optional")
    m_max_rows = w.Text(description="Max rows:", placeholder="optional")
    m_tolerance = w.Text(description="Baseline tolerance %:", placeholder="optional, e.g. 20")

    m_track_schema = w.Checkbox(value=True, description="Track schema changes")

    add_btn = dashui.action_button("Add Monitor", style="info")
    monitors_output, render_monitors = dashui.running_list(
        lambda i, m: (
            f"  {i}. {m['table']} — "
            f"freshness:{'on' if m['freshness_column'] else 'off'}, "
            f"volume:{'on' if (m['min_rows'] or m['max_rows'] or m['volume_tolerance_pct']) else 'off'}, "
            f"schema:{'on' if m['track_schema'] else 'off'}"
        )
    )

    def _parse_int(text):
        text = text.strip()
        return int(text) if text else None

    def _parse_float(text):
        text = text.strip()
        return float(text) if text else None

    def _save_state() -> None:
        try:
            dashui.save_config(_LIBRARY, {"monitors": monitors, "history_table": history_table.value.strip()})
        except Exception:
            pass  # persistence is a convenience, never block the actual operation on it

    def on_add(b):
        table = m_table.value.strip()
        if not table:
            return
        monitors.append({
            "table": table,
            "freshness_column": m_freshness_col.value.strip() or None,
            "max_staleness_minutes": m_max_staleness.value,
            "min_rows": _parse_int(m_min_rows.value),
            "max_rows": _parse_int(m_max_rows.value),
            "volume_tolerance_pct": _parse_float(m_tolerance.value),
            "track_schema": m_track_schema.value,
        })
        render_monitors(monitors)
        m_table.value = m_freshness_col.value = m_min_rows.value = m_max_rows.value = m_tolerance.value = ""
        _save_state()

    add_btn.on_click(on_add)
    render_monitors(monitors)  # show any monitors restored from a previous session

    # ── Run ──────────────────────────────────────────────────────────────
    history_table = w.Text(description="History table:", placeholder="catalog.schema.observe_history (optional)", value=saved["history_table"])
    run_btn = dashui.action_button("Run All Monitors", style="success")
    output = dashui.output_panel()

    def on_run(b):
        with output:
            output.clear_output()
            if not monitors:
                print("No monitors configured — add at least one above")
                return
            _save_state()
            try:
                from dashobserve.runner import MonitorConfig, run_monitors
                hist = history_table.value.strip() or None
                for m in monitors:
                    cfg = MonitorConfig(
                        table=m["table"],
                        freshness_column=m["freshness_column"],
                        max_staleness_minutes=m["max_staleness_minutes"] if m["freshness_column"] else None,
                        min_rows=m["min_rows"],
                        max_rows=m["max_rows"],
                        volume_tolerance_pct=m["volume_tolerance_pct"],
                        track_schema=m["track_schema"],
                    )
                    report = run_monitors(cfg, history_table=hist)
                    report.display()
                    s = report.summary()
                    print(f"   → {s['passed']}/{s['total_monitors']} passed\n")
            except Exception as e:
                print(f"Error: {e}")

    run_btn.on_click(on_run)

    # ── Forecast ─────────────────────────────────────────────────────────
    f_table = w.Text(description="UC Table:", placeholder="catalog.schema.table")
    f_history = w.Text(description="History table:", placeholder="catalog.schema.observe_history")
    f_n_periods = w.IntText(description="Periods ahead:", value=4, min=1, max=52)
    f_period = w.ToggleButtons(options=["days", "weeks", "months"], description="Period:")
    forecast_btn = dashui.action_button("Run Forecast", style="info")
    forecast_output = dashui.output_panel()

    def on_forecast(b):
        with forecast_output:
            forecast_output.clear_output()
            table = f_table.value.strip()
            hist = f_history.value.strip()
            if not table or not hist:
                print("Specify both a UC table and the history table")
                return
            try:
                from dashobserve.runner import run_forecast
                report = run_forecast(
                    table=table,
                    history_table=hist,
                    n_periods=f_n_periods.value,
                    period=f_period.value,
                )
                report.display()
            except Exception as e:
                print(f"Error: {e}")

    forecast_btn.on_click(on_forecast)

    env_accordion = w.Accordion(children=[dashui.env_setup_panel(_LIBRARY).widget])
    env_accordion.set_title(0, "Environment setup")
    env_accordion.selected_index = None

    ui = dashui.card([
        dashui.header("DashObserve — Data Observability", library="dashobserve"),
        env_accordion,
        dashui.section("Step 1: Configure a monitor"),
        m_table,
        w.HBox([m_freshness_col, m_max_staleness]),
        w.HBox([m_min_rows, m_max_rows, m_tolerance]),
        m_track_schema,
        add_btn, monitors_output,
        dashui.section("Step 2: Run monitors"),
        history_table,
        run_btn,
        output,
        dashui.section("Step 3: Forecast"),
        dashui.html(
            "<div style='font-size:12px;color:#666;margin-bottom:4px'>"
            "Predicts next table update and projects volume trend. "
            "Requires history built from prior monitor runs.</div>"
        ),
        w.HBox([f_table, f_history]),
        w.HBox([f_n_periods, f_period]),
        forecast_btn,
        forecast_output,
    ])
    display(ui)
