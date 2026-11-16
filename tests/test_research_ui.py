"""Drive the real dashboard and its native selection callbacks using fixed bars."""
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from data_loader import generate_demo_data

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def dashboard():
    st.cache_data.clear()
    bars = generate_demo_data("2023-01-01", "2024-12-31")
    with patch("data_loader.yf.download", return_value=bars) as download:
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        app.radio(key="lookup_mode").set_value("Enter ticker").run()
        app.text_input(key="custom_ticker").set_value("AAPL")
        app.date_input(key="start").set_value(date(2023, 1, 1))
        app.date_input(key="end").set_value(date(2024, 12, 31)).run()
        app.button(key="run").click().run()
        assert not app.exception
        yield app, download
    st.cache_data.clear()


def send_selection(app, element, selection):
    # AppTest has no Plotly click method. Inject the serialized frontend payload
    # through its runner, exercising the actual Streamlit widget callback.
    states = app._tree.get_widget_states()
    widget = next((w for w in states.widgets if w.id == element.proto.id), None)
    if widget is None:
        widget = states.widgets.add()
        widget.id = element.proto.id
    widget.string_value = json.dumps({"selection": selection})
    return app._run(states)


def test_click_scenario_then_trade_opens_matching_evidence(dashboard):
    app, download = dashboard
    app.button(key="run_failure").click().run()
    assert not app.exception
    report = app.session_state["failure_report"]
    picker = next(s for s in app.selectbox if s.label == "Scenario to inspect")
    scope = picker.key.removesuffix("_choice")
    selected_row = report.table.index[report.table.Category == "Slippage"][-1]
    selected_id = report.table.loc[selected_row, "Scenario"]
    table = next(t for t in app.dataframe if t.proto.id.endswith(f"{scope}_table"))
    send_selection(app, table, {"rows": [int(selected_row)], "columns": [], "cells": []})
    assert not app.exception
    assert app.selectbox(key=f"{scope}_choice").value == selected_id

    run = app.session_state["failure_report"].runs[selected_id]
    wanted = int(run.result.orders["Order ID"].iloc[1])
    chart_key = f"{scope}_{selected_id}_chart"
    chart = next(c for c in app.get("plotly_chart") if c.proto.id.endswith(chart_key))
    send_selection(app, chart, {"points": [{"point_index": 0, "customdata": [wanted]}],
                                "point_indices": [0], "box": [], "lasso": []})
    assert not app.exception
    assert app.selectbox(key=f"{scope}_{selected_id}_order").value == wanted
    expected = run.result.orders.set_index("Order ID").loc[wanted]
    accounts = [t.value for t in app.dataframe if "Field" in t.value.columns]
    assert accounts[0].set_index("Field").loc["Price", "Value"] == expected.Price
    assert accounts[0].set_index("Field").loc["Slippage Cost", "Value"] > 0
    assert not app.error
    assert download.call_count == 1  # Every variation reuses the saved price snapshot.


def test_research_controls_audit_and_stale_report_handling(dashboard):
    app, download = dashboard
    audit = next(b for b in app.button if b.key.endswith("_audit_button"))
    audit.click().run()
    assert (app.session_state[audit.key.replace("_button", "_result")].Status == "Pass").all()
    app.button(key="run_failure").click().run()
    fingerprint = app.session_state["failure_report"].fingerprint
    app.number_input(key="stress_slippage").set_value(0.5).run()
    assert any("Stress ranges changed" in w.value for w in app.warning)
    assert app.session_state["failure_report"].limits["slippage"] == 0.25
    app.button(key="run_failure").click().run()
    assert app.session_state["failure_report"].limits["slippage"] == 0.5
    app.number_input(key="capital").set_value(200000).run()
    assert any("Inputs changed" in w.value for w in app.warning)
    assert app.session_state["failure_report"].fingerprint == fingerprint
    app.button(key="run").click().run()
    assert not app.exception
    assert not app.error
    assert "failure_report" not in app.session_state
    assert download.call_count == 1
