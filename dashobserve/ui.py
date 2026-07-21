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

    m_track_freshness = w.Checkbox(value=False, description="Track freshness")
    m_freshness_col = w.Text(
        description="Freshness col:",
        placeholder="updated_at — leave blank to use Delta table metadata instead",
    )
    m_max_staleness = w.IntText(description="Max staleness (min):", value=1440)

    m_min_rows = w.Text(description="Min rows:", placeholder="optional")
    m_max_rows = w.Text(description="Max rows:", placeholder="optional")
    m_tolerance = w.Text(description="Baseline tolerance %:", placeholder="optional, e.g. 20")

    m_track_schema = w.Checkbox(value=True, description="Track schema changes")

    add_btn = dashui.action_button("Add Monitor", style="info")

    def _monitor_label(i, m):
        freshness = "off"
        if m["max_staleness_minutes"] is not None:
            freshness = f"on ({m['freshness_column'] or 'metadata'})"
        volume = "on" if (m["min_rows"] or m["max_rows"] or m["volume_tolerance_pct"]) else "off"
        return f"{i}. {m['table']} — freshness:{freshness}, volume:{volume}, schema:{'on' if m['track_schema'] else 'off'}"

    monitors_list = dashui.item_list(_monitor_label, empty_text="No monitors configured yet.")

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

    def _render_monitors():
        monitors_list.render(monitors, on_change=lambda _items: _save_state())

    def _add_monitor(table: str):
        monitors.append({
            "table": table,
            "freshness_column": m_freshness_col.value.strip() or None,
            "max_staleness_minutes": m_max_staleness.value if m_track_freshness.value else None,
            "min_rows": _parse_int(m_min_rows.value),
            "max_rows": _parse_int(m_max_rows.value),
            "volume_tolerance_pct": _parse_float(m_tolerance.value),
            "track_schema": m_track_schema.value,
        })

    def on_add(b):
        table = m_table.value.strip()
        if not table:
            return
        _add_monitor(table)
        _render_monitors()
        m_table.value = m_freshness_col.value = m_min_rows.value = m_max_rows.value = m_tolerance.value = ""
        _save_state()

    add_btn.on_click(on_add)
    _render_monitors()  # show any monitors restored from a previous session

    # ── Bulk-add from schema discovery ──────────────────────────────────────
    discover_schema = w.Text(description="Schema:", placeholder="catalog.schema")
    discover_btn = dashui.action_button("Discover Tables", style="info")
    discovered_select = w.SelectMultiple(options=[], description="Found:", layout=w.Layout(width="100%", height="120px"))
    add_selected_btn = dashui.action_button("Add Selected", style="success")
    discover_output = dashui.output_panel()

    def on_discover(b):
        with discover_output:
            discover_output.clear_output()
            scope = discover_schema.value.strip()
            if not scope:
                print("Enter a catalog.schema first")
                return
            discover_btn.set_label("Discovering…")
            discover_btn.set_disabled(True)
            try:
                from dashobserve.runner import discover_tables
                found = discover_tables(scope)
                discovered_select.options = found
                print(f"Found {len(found)} table(s) — select the ones to monitor, using the settings above")
            except Exception as e:
                print(f"Error: {e}")
            finally:
                discover_btn.set_label("Discover Tables")
                discover_btn.set_disabled(False)

    def on_add_selected(b):
        with discover_output:
            for table in discovered_select.value:
                _add_monitor(table)
            _render_monitors()
            _save_state()
            print(f"Added {len(discovered_select.value)} monitor(s)")

    discover_btn.on_click(on_discover)
    add_selected_btn.on_click(on_add_selected)

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
            run_btn.set_label("Running…")
            run_btn.set_disabled(True)
            try:
                from dashobserve.runner import MonitorConfig, run_monitors
                hist = history_table.value.strip() or None
                for m in monitors:
                    cfg = MonitorConfig(
                        table=m["table"],
                        freshness_column=m["freshness_column"],
                        max_staleness_minutes=m["max_staleness_minutes"],
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
            finally:
                run_btn.set_label("Run All Monitors")
                run_btn.set_disabled(False)

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
        w.HBox([m_track_freshness, m_max_staleness]),
        m_freshness_col,
        w.HBox([m_min_rows, m_max_rows, m_tolerance]),
        m_track_schema,
        add_btn,
        dashui.html(
            "<div style='font-size:12px;color:#666;margin:6px 0 2px'>Or add every table in "
            "a schema at once, using the settings above:</div>"
        ),
        w.HBox([discover_schema, discover_btn]),
        discovered_select, add_selected_btn, discover_output,
        monitors_list.widget,
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
