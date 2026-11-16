"""Exercise actual Streamlit widgets without relying on Yahoo availability."""
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from io import BytesIO
import json
import zipfile
import streamlit as st
from streamlit.testing.v1 import AppTest
import pytest

from data_loader import generate_demo_data

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def clear_caches():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


LISTINGS = [
    {"symbol": "RELIANCE.NS", "longname": "Reliance Industries", "exchDisp": "NSE", "quoteType": "EQUITY"},
    {"symbol": "RELIANCE.BO", "longname": "Reliance Industries", "exchDisp": "BSE", "quoteType": "EQUITY"},
]


def search_and_select(app, symbol="RELIANCE.NS"):
    app.text_input(key="stock_query").set_value("Reliance")
    app.button(key="search_stocks").click().run()
    app.selectbox(key="selected_stock").select(symbol).run()


def test_real_data_is_default_and_initial_visit_makes_no_network_requests():
    with patch("data_loader.yf.Search") as search, patch("data_loader.yf.download") as download:
        app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert all(widget.label != "Data source" for widget in app.selectbox)
    assert app.button(key="run").disabled
    assert "report" not in app.session_state
    search.assert_not_called()
    download.assert_not_called()


def test_search_requires_explicit_listing_and_only_downloads_selected_exchange():
    # Known fixture bars isolate app/accounting behavior from provider availability.
    fixture = generate_demo_data("2020-01-01", "2025-01-01")
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=LISTINGS)) as search, \
         patch("data_loader.yf.download", return_value=fixture) as download:
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        app.text_input(key="stock_query").set_value("Reliance")
        app.button(key="search_stocks").click().run()
        assert not app.exception
        assert app.selectbox(key="selected_stock").value is None
        assert app.button(key="run").disabled
        assert all("Reliance Industries" in label for label in app.selectbox(key="selected_stock").options)
        app.selectbox(key="selected_stock").select("RELIANCE.BO").run()
        app.date_input(key="start").set_value(date(2023, 1, 1))
        app.date_input(key="end").set_value(date(2024, 12, 31))
        download.assert_not_called()
        app.button(key="run").click().run()
        assert not app.exception
        assert not app.error
        assert download.call_args.args[0] == "RELIANCE.BO"
        saved, signals, result, stats = app.session_state["report"]
        assert saved["exchange"] == "BSE"
        assert saved["company"] == "Reliance Industries"
        assert signals.attrs["source"] == "Yahoo Finance (adjusted)"
        assert signals.attrs["fetched_at_utc"]
        app.number_input(key="capital").set_value(200000).run()
        assert any("Inputs changed" in w.value for w in app.warning)
        app.button(key="run").click().run()
        assert app.session_state["report"][3]["Initial capital"] == 200000
        assert download.call_count == 1  # Reuse bars, recalculate the portfolio.
        assert search.call_count == 1
    from app import export_report
    with zipfile.ZipFile(BytesIO(export_report(saved, result, stats, signals))) as archive:
        params = json.loads(archive.read("parameters.json"))
        metadata = json.loads(archive.read("data_metadata.json"))
        assert params["ticker"] == "RELIANCE.BO"
        assert metadata["synthetic"] is False
        assert metadata["last_bar"] == str(signals.index[-1].date())


@pytest.mark.parametrize("failure", [False, True])
def test_new_empty_or_failed_search_clears_previous_selection(failure):
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=LISTINGS)) as search:
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        search_and_select(app)
        assert not app.button(key="run").disabled
        if failure:
            search.side_effect = RuntimeError("service unavailable")
        else:
            search.return_value = SimpleNamespace(quotes=[])
        app.text_input(key="stock_query").set_value("Another company")
        app.button(key="search_stocks").click().run()
        assert not app.exception
        assert app.button(key="run").disabled
        assert "report" not in app.session_state
        if failure:
            assert any("Enter ticker" in error.value for error in app.error)
        else:
            assert any("No matching" in info.value for info in app.info)


def test_direct_ticker_bypasses_search_and_failure_never_uses_demo():
    with patch("data_loader.yf.Search") as search, \
         patch("data_loader.yf.download", side_effect=RuntimeError("timeout")), \
         patch("data_loader.generate_demo_data") as demo:
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        app.radio(key="lookup_mode").set_value("Enter ticker").run()
        app.text_input(key="custom_ticker").set_value(" tcs.ns ").run()
        app.button(key="run").click().run()
        assert not app.exception
        assert any("Market download failed" in error.value for error in app.error)
        assert "report" not in app.session_state
        search.assert_not_called()
        demo.assert_not_called()


def test_blank_direct_ticker_disables_run_and_bad_ticker_never_downloads():
    with patch("data_loader.yf.download") as download:
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        app.radio(key="lookup_mode").set_value("Enter ticker").run()
        assert app.button(key="run").disabled
        app.text_input(key="custom_ticker").set_value("AAPL MSFT").run()
        app.button(key="run").click().run()
        assert not app.exception
        assert any("one valid" in error.value for error in app.error)
        download.assert_not_called()


@pytest.mark.parametrize("strategy", ["Moving Average Crossover", "RSI Strategy", "Momentum Strategy"])
def test_dashboard_runs_all_strategies(strategy):
    fixture = generate_demo_data("2023-01-01", "2024-12-31")
    with patch("data_loader.yf.download", return_value=fixture):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        assert not app.exception
        app.radio(key="lookup_mode").set_value("Enter ticker").run()
        app.text_input(key="custom_ticker").set_value("AAPL")
        app.date_input(key="start").set_value(date(2023, 1, 1))
        app.date_input(key="end").set_value(date(2024, 12, 31))
        app.selectbox(key="strategy").select(strategy).run()
        app.button(key="run").click().run()
    assert not app.exception
    assert not app.error
    assert len(app.metric) >= 8
    assert len(app.dataframe) >= 3
    assert app.session_state["report"][3]["Initial capital"] == 100000
    assert app.session_state["report"][0]["source"] == "Yahoo Finance"


def test_dashboard_invalid_ma_and_changed_inputs():
    fixture = generate_demo_data("2023-01-01", "2024-12-31")
    with patch("data_loader.yf.download", return_value=fixture):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        app.radio(key="lookup_mode").set_value("Enter ticker").run()
        app.text_input(key="custom_ticker").set_value("AAPL")
        app.date_input(key="start").set_value(date(2023, 1, 1))
        app.date_input(key="end").set_value(date(2024, 12, 31)).run()
        app.button(key="run").click().run()
        app.number_input(key="capital").set_value(200000).run()
        assert any("Inputs changed" in warning.value for warning in app.warning)
        app.number_input(key="short").set_value(80)
        app.button(key="run").click().run()
    assert any("strictly smaller" in error.value for error in app.error)
    assert not app.exception
