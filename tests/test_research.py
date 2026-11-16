"""Financial invariants, controlled stress experiments and falsifiable evidence."""
from copy import deepcopy
from io import BytesIO
import json
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd
import pytest

from backtester import run_backtest
from data_loader import generate_demo_data
from failure_analysis import (build_scenarios, evaluate_scenario, export_failure_report,
                              run_failure_analysis, snapshot_id)
from strategies import STRATEGIES, moving_average_strategy
from trade_evidence import audit_future_data, evidence_for_order, evidence_json, selected_order_id


def prices(close, signal=None):
    close = np.array(close, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                          "Close": close, "Volume": 100}, index=pd.bdate_range("2023-01-02", periods=len(close)))
    if signal is not None:
        frame["Signal"] = signal
    return frame


def config(strategy="Moving Average Crossover"):
    params = {"Moving Average Crossover": dict(short_window=10, long_window=30),
              "RSI Strategy": dict(period=14, lower=30.0, upper=70.0),
              "Momentum Strategy": dict(lookback=20, entry_threshold=5.0, exit_threshold=0.0)}
    return dict(source="Yahoo Finance", ticker="TEST", start="2023-01-01", end="2024-01-01",
                capital=1000.0, cost=0.1, risk_free=0.0, strategy=strategy, params=params[strategy])


@pytest.fixture
def snapshot():
    return generate_demo_data("2023-01-01", "2024-01-01")


def test_delayed_slipped_fills_preserve_cash_cost_basis_and_original_signal():
    data = prices([100, 101, 110, 111, 130, 120], [1, 0, -1, 0, 0, 0])
    result = run_backtest(data, 1000, 1, slippage_pct=2, execution_delay=2)
    qty = 1000 / (110 * 1.02 * 1.01)
    final = qty * (130 * 0.98) * 0.99
    assert result.equity.Equity.iloc[-1] == pytest.approx(final)
    assert result.orders.Date.tolist() == [data.index[2], data.index[4]]
    assert result.orders["Signal Date"].tolist() == [data.index[0], data.index[2]]
    assert result.orders.Price.tolist() == pytest.approx([112.2, 127.4])
    assert result.orders["Market Open"].tolist() == [110, 130]
    assert result.orders["Slippage Cost"].sum() == pytest.approx(qty * (2.2 + 2.6))
    assert result.orders["Cost Basis Before"].tolist() == pytest.approx([0, 1000])
    assert result.orders["Cost Basis After"].tolist() == pytest.approx([1000, 0])
    np.testing.assert_allclose(result.equity.Equity - 1000,
                               result.equity["Realized P&L"] + result.equity["Unrealized P&L"], atol=1e-8)
    assert result.equity["Buy & Hold"].iloc[-1] == pytest.approx(1000 / (100 * 1.02 * 1.01) * 120)


@pytest.mark.parametrize("kwargs", [{"execution_delay": 0}, {"execution_delay": -1},
    {"execution_delay": 1.5}, {"execution_delay": True}, {"slippage_pct": -1},
    {"slippage_pct": np.nan}, {"slippage_pct": 100}])
def test_invalid_execution_models_are_rejected(kwargs):
    with pytest.raises(ValueError):
        run_backtest(prices([100, 101], [1, 0]), **kwargs)


def test_delay_beyond_history_never_fills_and_more_slippage_reduces_equity():
    data = prices([100, 110, 120, 130, 140, 150], [1, 0, -1, 1, 0, 0])
    assert run_backtest(data, execution_delay=20).orders.empty
    results = [run_backtest(data, slippage_pct=s).equity.Equity.iloc[-1] for s in [0, 0.1, 0.5, 2]]
    assert all(a > b for a, b in zip(results, results[1:]))


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_each_scenario_changes_exactly_one_assumption_and_does_not_mutate_config(strategy):
    original = config(strategy)
    before = deepcopy(original)
    cases, _ = build_scenarios(original)
    for case in cases[1:]:
        changes = sum([case.cost != original["cost"], case.slippage != 0,
                       case.delay != 1, case.start_offset != 0])
        changes += sum(case.params[k] != original["params"][k] for k in original["params"])
        assert changes == 1
    assert original == before


def test_report_matches_baseline_rewarms_start_and_exports_every_evaluated_path(snapshot):
    cfg = config()
    untouched = snapshot.copy(deep=True)
    expected_signals = STRATEGIES[cfg["strategy"]](snapshot, **cfg["params"])
    expected = run_backtest(expected_signals, cfg["capital"], cfg["cost"])
    report = run_failure_analysis(expected_signals, cfg)
    pd.testing.assert_frame_equal(report.runs["baseline"].result.equity, expected.equity)
    pd.testing.assert_frame_equal(snapshot, untouched)
    shifted = next(r for r in report.runs.values() if r.scenario.start_offset == 10)
    assert shifted.signals.index[0] == snapshot.index[10]
    assert shifted.signals.Long_MA.iloc[:29].isna().all()
    assert not shifted.signals.Signal.iloc[:29].any()
    with zipfile.ZipFile(BytesIO(export_failure_report(report))) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["snapshot_sha256"] == snapshot_id(snapshot, cfg)
        assert len(manifest["scenarios"]) == len(report.runs)
        for id_, run in report.runs.items():
            if run.result is not None:
                assert f"{id_}/orders.csv" in archive.namelist()
        assert "adjusted_prices.csv" in archive.namelist()


def test_skipped_parameters_and_no_trade_baseline_are_never_robustness_passes():
    data = prices([100] * 20)
    cfg = config()
    cfg["params"] = dict(short_window=1, long_window=2)
    report = run_failure_analysis(data, cfg)
    assert report.table.iloc[0].Outcome == "No trades"
    assert (report.table.Status == "Skipped").any()  # Zero period or reversed MA windows.
    assert (report.findings.Scenario == "").all()
    assert all("Baseline is no trades" in message for message in report.findings.Finding)


def test_smallest_tested_loss_is_identified_only_for_profitable_baseline():
    # An isolated buy rule makes the fee threshold check analytically transparent.
    def buy_once(data, **params):
        out = data.copy()
        out["Signal"] = 0
        out.iloc[0, out.columns.get_loc("Signal")] = 1
        return out
    cfg = config()
    data = prices([100, 100, 100.3, 100.3])
    with patch.dict(STRATEGIES, {cfg["strategy"]: buy_once}):
        report = run_failure_analysis(data, cfg, dict(extra_cost=1.0, start_shift=1))
        costs = report.table[report.table.Category == "Transaction costs"]
        expected = costs[costs.Outcome == "Loss"].sort_values("Magnitude").iloc[0]
        finding = report.findings[report.findings.Category == "Transaction costs"].iloc[0]
        assert report.table.iloc[0].Outcome == "Profit"
        assert finding.Scenario == expected.Scenario
        assert finding.Change == expected.Change
        losing = run_failure_analysis(prices([100, 100, 90, 90]), cfg, dict(start_shift=1))
        assert losing.table.iloc[0].Outcome == "Loss"
        assert (losing.findings.Scenario == "").all()


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_every_executed_order_has_valid_decision_and_accounting_evidence(snapshot, strategy):
    cfg = config(strategy)
    signals = STRATEGIES[strategy](snapshot, **cfg["params"])
    result = run_backtest(signals, 1000, 0.3, slippage_pct=0.2, execution_delay=3)
    assert len(result.orders)
    for id_ in result.orders["Order ID"]:
        evidence = evidence_for_order(signals, result, strategy, cfg["params"], id_)
        assert all(row["Satisfied"] for row in evidence["checks"])
        assert evidence["accounting_matches"]
        assert evidence["position_eligible"]
        assert evidence["signal_matches_side"]
        assert evidence["fill_delay_bars"] == 3
        assert evidence["decision_context"].index[-1] == evidence["order"]["Signal Date"]
        parsed = json.loads(evidence_json(evidence))
        assert parsed["order"]["Order ID"] == id_
        assert "NaN" not in evidence_json(evidence)


def test_chart_uses_order_ids_not_trace_indices():
    event = {"selection": {"points": [{"point_index": 0, "customdata": [8]}]}}
    assert selected_order_id(event, [2, 4, 8]) == 8
    assert selected_order_id(event, [2, 4]) is None
    assert selected_order_id({"selection": {"points": [{"point_index": 0}]}}, [1]) is None


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_causal_strategies_pass_sampled_audit_even_with_delayed_slipped_fills(snapshot, strategy):
    cfg = config(strategy)
    audit = audit_future_data(snapshot, strategy, cfg["params"], slippage=0.5, delay=3)
    assert len(audit) == 6
    assert (audit.Status == "Pass").all()


def test_audit_detects_a_deliberately_leaky_indicator_and_insufficient_history(snapshot):
    cfg = config()
    def leaky(data, **params):
        result = moving_average_strategy(data, **params)
        result["Tomorrow"] = result.Close.shift(-1)
        return result
    with patch.dict(STRATEGIES, {cfg["strategy"]: leaky}):
        audit = audit_future_data(snapshot, cfg["strategy"], cfg["params"])
    assert (audit.Status == "Fail").all()
    assert audit.Details.str.contains("Tomorrow").all()
    short = audit_future_data(snapshot.iloc[:32], cfg["strategy"], cfg["params"])
    assert short.Status.iloc[0] == "Insufficient history"


def test_audit_fingerprint_changes_with_prices_or_parameters(snapshot):
    cfg = config()
    original = snapshot_id(snapshot, cfg)
    changed = snapshot.copy()
    changed.iloc[-1, changed.columns.get_loc("Close")] += 1
    assert snapshot_id(changed, cfg) != original
    cfg["params"]["short_window"] += 1
    assert snapshot_id(snapshot, cfg) != original
