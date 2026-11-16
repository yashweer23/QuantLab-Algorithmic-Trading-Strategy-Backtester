"""Deterministic financial invariants and strategy tests; no market network required."""
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from backtester import run_backtest
from data_loader import DataError, clean_market_data, generate_demo_data, load_market_data, validate_request
from metrics import calculate_metrics
from strategies import STRATEGIES, momentum_strategy, moving_average_strategy, rsi_strategy
from strategies.rsi import calculate_rsi


def bars(prices, signals=None, opens=None):
    closes = np.array(prices, dtype=float)
    opens = closes if opens is None else np.array(opens, dtype=float)
    return pd.DataFrame({"Open": opens, "High": np.maximum(opens, closes) + 1,
                         "Low": np.minimum(opens, closes) - 1, "Close": closes,
                         "Volume": 100, "Signal": signals if signals is not None else 0},
                        index=pd.bdate_range("2024-01-01", periods=len(closes)))


def test_next_open_execution_fees_and_accounting():
    data = bars([100, 115, 125, 140], [1, 0, -1, 0], [100, 110, 120, 130])
    result = run_backtest(data, 1000, 1)
    quantity = 1000 / (110 * 1.01)
    final = quantity * 130 * 0.99
    assert list(result.orders.Date) == [data.index[1], data.index[3]]
    assert list(result.orders["Signal Date"]) == [data.index[0], data.index[2]]
    assert list(result.orders.Price) == [110, 130]
    assert result.equity.Equity.iloc[-1] == pytest.approx(final)
    assert result.trades["Net P&L"].iloc[0] == pytest.approx(final - 1000)
    np.testing.assert_allclose(result.equity.Equity - 1000,
                               result.equity["Realized P&L"] + result.equity["Unrealized P&L"], atol=1e-10)
    np.testing.assert_allclose(result.equity.Equity,
                               result.equity.Cash + result.equity.Holdings * data.Close)
    assert result.orders.Fee.sum() == pytest.approx(result.equity["Cumulative Fees"].iloc[-1])


def test_ignores_repeated_orders_and_final_signal():
    result = run_backtest(bars([100] * 7, [-1, 1, 1, -1, -1, 0, 1]), 1000, 0)
    assert result.orders.Side.tolist() == ["BUY", "SELL"]
    assert len(result.trades) == 1
    assert result.equity.Equity.iloc[-1] == 1000


def test_open_position_mark_to_market():
    result = run_backtest(bars([100, 100, 120], [1, 0, 0]), 1000, 1)
    assert result.trades.empty
    assert result.equity.Holdings.iloc[-1] == pytest.approx(1000 / 101)
    assert result.equity["Unrealized P&L"].iloc[-1] == pytest.approx(1000 / 101 * 120 - 1000)
    assert result.equity["Realized P&L"].iloc[-1] == 0
    assert np.isnan(calculate_metrics(result)["Win rate %"])


def test_no_trades_has_defined_cash_metrics():
    result = run_backtest(bars([100, 90, 110]), 1000, 0.1)
    stats = calculate_metrics(result)
    assert stats["Total return %"] == 0
    assert stats["Maximum drawdown %"] == 0
    assert stats["Annualized volatility %"] == 0
    assert np.isnan(stats["Sharpe ratio"])
    assert np.isnan(stats["Profit factor"])
    assert stats["Completed trades"] == 0
    assert list(result.orders.columns)


def test_drawdown_includes_entry_fee_and_initial_capital():
    result = run_backtest(bars([100, 100, 80], [1, 0, 0]), 1000, 1)
    assert result.equity.Drawdown.iloc[-1] == pytest.approx((1000 / 101 * 80) / 1000 - 1)


def test_benchmark_includes_cost_and_first_open():
    result = run_backtest(bars([105, 110, 120], opens=[100, 106, 111]), 1000, 1)
    assert result.equity["Buy & Hold"].iloc[-1] == pytest.approx(1000 / 101 * 120)


def test_trade_statistics_and_risk_formula():
    # Win +20, loss -30, breakeven 0; full-capital reinvestment each time.
    result = run_backtest(bars([100, 100, 120, 120, 90, 90, 90], [1, -1, 1, -1, 1, -1, 0]), 100, 0)
    stats = calculate_metrics(result, risk_free_rate_pct=5)
    assert stats["Completed trades"] == 3
    assert stats["Winning trades"] == 1
    assert stats["Losing trades"] == 1
    assert stats["Breakeven trades"] == 1
    assert stats["Win rate %"] == pytest.approx(100 / 3)
    assert stats["Average P&L per trade"] == pytest.approx(-10 / 3)
    assert stats["Profit factor"] == pytest.approx(20 / 30)
    returns = result.equity["Daily Return"].to_numpy()
    expected_sharpe = (returns.mean() - (1.05 ** (1 / 252) - 1)) / returns.std(ddof=1) * np.sqrt(252)
    assert stats["Sharpe ratio"] == pytest.approx(expected_sharpe)
    assert stats["Annualized volatility %"] == pytest.approx(returns.std(ddof=1) * np.sqrt(252) * 100)


@pytest.mark.parametrize("prices,expected", [([100, 100, 120], np.inf), ([100, 100, 80], 0)])
def test_profit_factor_one_sided_outcomes(prices, expected):
    stats = calculate_metrics(run_backtest(bars(prices, [1, -1, 0]), 1000, 0))
    assert stats["Profit factor"] == expected


@pytest.mark.parametrize("capital,cost", [(0, 0), (-1, 0), (np.nan, 0), (100, -1), (100, 100), (100, np.inf)])
def test_invalid_engine_inputs(capital, cost):
    with pytest.raises(ValueError):
        run_backtest(bars([100, 110]), capital, cost)


def test_engine_rejects_bad_prices_and_signals():
    for column, bad in [("Open", np.nan), ("Close", -1), ("Signal", 2)]:
        data = bars([100, 101])
        data.loc[data.index[0], column] = bad
        with pytest.raises(ValueError):
            run_backtest(data)


def test_sma_crossovers_and_warmup():
    result = moving_average_strategy(bars([5, 4, 3, 4, 5, 4, 3, 2]), 2, 3)
    assert result.Signal.tolist() == [0, 0, 0, 0, 1, 0, -1, 0]
    rising = moving_average_strategy(bars(list(range(10, 20))), 2, 3)
    assert not rising.Signal.any()  # Existing trend is not a new crossover.


def test_wilder_rsi_seed_and_recursion():
    result = calculate_rsi(pd.Series([10, 11, 10, 12, 11], dtype=float), 3)
    assert result.iloc[:3].isna().all()
    assert result.iloc[3] == pytest.approx(75)
    assert result.iloc[4] == pytest.approx(100 - 100 / (1 + (2 / 3) / (5 / 9)))


@pytest.mark.parametrize("prices,expected", [([100] * 20, 50), (list(range(100, 120)), 100), (list(range(120, 100, -1)), 0)])
def test_rsi_flat_and_one_direction(prices, expected):
    assert calculate_rsi(pd.Series(prices, dtype=float)).iloc[-1] == expected


def test_momentum_units_and_thresholds():
    result = momentum_strategy(bars([100, 110, 120, 90, 80]), 2, 5, 0)
    assert result.Momentum.iloc[2] == pytest.approx(20)
    assert result.Signal.tolist() == [0, 0, 1, -1, -1]


@pytest.mark.parametrize("strategy", list(STRATEGIES.values()))
def test_strategy_and_engine_are_prefix_invariant(strategy):
    data = generate_demo_data("2022-01-01", "2024-01-01")
    prefix = strategy(data.iloc[:200])
    full = strategy(data)
    pd.testing.assert_frame_equal(prefix, full.iloc[:200])
    # Even adversarial later prices cannot alter earlier indicators or executions.
    changed = data.copy()
    changed.loc[changed.index[200]:, ["Open", "High", "Low", "Close"]] *= 10
    altered = strategy(changed)
    pd.testing.assert_frame_equal(full.iloc[:200], altered.iloc[:200])
    pd.testing.assert_frame_equal(run_backtest(prefix).equity, run_backtest(full).equity.iloc[:200])


@pytest.mark.parametrize("fn,kwargs", [
    (moving_average_strategy, {"short_window": 50, "long_window": 20}),
    (moving_average_strategy, {"short_window": 20, "long_window": 20}),
    (moving_average_strategy, {"short_window": 0}),
    (rsi_strategy, {"lower": 70, "upper": 30}),
    (rsi_strategy, {"period": 1.5}),
    (momentum_strategy, {"entry_threshold": 0, "exit_threshold": 5}),
])
def test_invalid_strategy_parameters(fn, kwargs):
    with pytest.raises(ValueError):
        fn(bars([100] * 100), **kwargs)


@pytest.mark.parametrize("strategy", list(STRATEGIES.values()))
def test_insufficient_indicator_history(strategy):
    with pytest.raises(ValueError, match="at least"):
        strategy(bars([100, 101]))


def test_cleaning_drops_invalid_rows_without_filling():
    data = bars([100, 101, 102, 103])
    data.loc[data.index[1], "Close"] = np.nan
    data.loc[data.index[2], "Open"] = np.inf
    cleaned = clean_market_data(data)
    assert cleaned.index.tolist() == [data.index[0], data.index[3]]
    assert cleaned.attrs["removed_rows"] == 2
    multi = bars([100, 101])
    multi.columns = pd.MultiIndex.from_product([multi.columns, ["AAPL"]])
    assert clean_market_data(multi).Close.tolist() == [100, 101]


@pytest.mark.parametrize("raw", [None, pd.DataFrame(), pd.DataFrame({"Close": [100]})])
def test_missing_data_errors(raw):
    with pytest.raises(DataError):
        clean_market_data(raw)


def test_request_validation_and_inclusive_end():
    with pytest.raises(DataError):
        validate_request("AAPL", "2024-02-01", "2024-01-01")
    with pytest.raises(DataError):
        validate_request("AAPL MSFT", "2024-01-01", "2024-02-01")
    with patch("data_loader.yf.download", return_value=bars([100, 101])) as download:
        data = load_market_data("aapl", "2024-01-01", "2024-01-02")
        assert download.call_args.kwargs["end"] == "2024-01-03"
        assert download.call_args.kwargs["auto_adjust"] is True
        assert len(data) == 2
    with patch("data_loader.yf.download", return_value=pd.DataFrame()):
        with pytest.raises(DataError, match="No data"):
            load_market_data("UNKNOWN", "2024-01-01", "2024-02-01")
