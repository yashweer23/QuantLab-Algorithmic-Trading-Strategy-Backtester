"""Explain actual fills with decision-time values and sampled causality checks."""
import json
from numbers import Integral

import numpy as np
import pandas as pd

from backtester import run_backtest
from failure_analysis import PRICE_COLUMNS, market_snapshot
from strategies import STRATEGIES


def evidence_for_order(signals, result, strategy, params, order_id):
    found = result.orders.loc[result.orders["Order ID"] == order_id]
    if len(found) != 1:
        raise ValueError("Choose an order from this scenario's ledger.")
    order = found.iloc[0]
    pos = signals.index.get_loc(order["Signal Date"])
    row = signals.iloc[pos]
    previous = signals.iloc[pos - 1] if pos else None
    buy = order.Side == "BUY"
    checks = []

    def check(label, left, operator, right):
        operations = {"<": np.less, ">": np.greater, "<=": np.less_equal, ">=": np.greater_equal}
        satisfied = bool(np.isfinite(left) and np.isfinite(right) and operations[operator](left, right))
        checks.append({"Condition": label, "Left value": float(left), "Operator": operator,
                       "Right value": float(right), "Satisfied": satisfied})

    if strategy == "Moving Average Crossover":
        check("Previous short vs long MA", previous.Short_MA if previous is not None else np.nan,
              "<=" if buy else ">=", previous.Long_MA if previous is not None else np.nan)
        check("Signal-day short vs long MA", row.Short_MA, ">" if buy else "<", row.Long_MA)
        explanation = "The short moving average crossed above the long average." if buy else "The short moving average crossed below the long average."
    elif strategy == "RSI Strategy":
        check("Signal-day RSI vs threshold", row.RSI, "<" if buy else ">", params["lower"] if buy else params["upper"])
        explanation = "RSI was below the buy threshold." if buy else "RSI was above the sell threshold."
    elif strategy == "Momentum Strategy":
        check("Signal-day momentum (%) vs threshold", row.Momentum, ">" if buy else "<",
              params["entry_threshold"] if buy else params["exit_threshold"])
        explanation = "Lookback momentum exceeded the entry threshold." if buy else "Lookback momentum fell below the exit threshold."
    else:
        raise ValueError("This strategy has no evidence formatter registered.")

    cash_expected = order["Cash Before"] + (-order.Notional - order.Fee if buy else order.Notional - order.Fee)
    holdings_expected = order["Holdings Before"] + (order.Quantity if buy else -order.Quantity)
    cash_residual = float(order["Cash After"] - cash_expected)
    holdings_residual = float(order["Holdings After"] - holdings_expected)
    context = signals.iloc[max(0, pos - 5):pos + 1].copy()
    context.index.name = "Available at signal close"
    return {
        "order": order.to_dict(), "strategy": strategy, "parameters": dict(params),
        "explanation": explanation, "checks": checks,
        "signal_matches_side": int(row.Signal) == (1 if buy else -1),
        "position_eligible": bool(order["Holdings Before"] == 0 if buy else order["Holdings Before"] > 0),
        "signal_close": float(row.Close), "decision_context": context,
        "fill_delay_bars": int(signals.index.get_loc(order.Date) - pos),
        "cost_pct": result.transaction_cost_pct, "slippage_pct": result.slippage_pct,
        "cash_residual": cash_residual, "holdings_residual": holdings_residual,
        "accounting_matches": bool(np.isclose(cash_residual, 0, atol=max(1e-8, result.initial_capital * 1e-12))
                                   and np.isclose(holdings_residual, 0, atol=1e-8)),
    }


def evidence_json(evidence):
    def clean(value):
        if isinstance(value, pd.DataFrame):
            return clean(value.reset_index().to_dict("records"))
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, np.generic):
            return clean(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value
    return json.dumps(clean(evidence), indent=2, allow_nan=False)


def selected_order_id(event, valid_ids):
    """Resolve chart customdata, never a trace-local point index, to a ledger ID."""
    points = (event or {}).get("selection", {}).get("points", [])
    for point in reversed(points):
        custom = point.get("customdata")
        if isinstance(custom, (list, tuple)) and custom:
            candidate = custom[0]
            if candidate in valid_ids:
                return candidate
    return None


def _compare_frames(expected, actual):
    if not expected.index.equals(actual.index) or list(expected.columns) != list(actual.columns):
        return False, "Index or columns changed"
    equal = np.isclose(expected.to_numpy(dtype=float), actual.to_numpy(dtype=float),
                       rtol=1e-10, atol=1e-10, equal_nan=True)
    if equal.all():
        return True, ""
    r, c = np.argwhere(~equal)[0]
    return False, f"{expected.index[r].date()}: {expected.columns[c]} changed"


def audit_future_data(data, strategy, params, *, initial_capital=100000.0,
                      cost=0.1, slippage=0.0, delay=1, sample_count=6):
    """Compare full runs with truncated prefixes and deliberately changed future prices.

    Passing sampled checks is evidence of consistency, not proof against every bias.
    The input remains the downloaded adjusted snapshot, not historical data vintages.
    """
    if isinstance(sample_count, bool) or not isinstance(sample_count, Integral) or not 1 <= sample_count <= 20:
        raise ValueError("Audit sample count must be an integer from 1 to 20.")
    raw = market_snapshot(data)
    fn = STRATEGIES[strategy]
    full = fn(raw, **params)
    minimum = (params["long_window"] if "long_window" in params else
               params["period"] if "period" in params else params["lookback"]) + 2
    if len(raw) <= minimum:
        return pd.DataFrame([{"Cutoff": pd.NaT, "Prefix indicators": "Not tested",
                              "Changed future": "Not tested", "Portfolio prefix": "Not tested",
                              "Status": "Insufficient history", "Details": "Need at least one bar beyond indicator warm-up."}])
    options = dict(initial_capital=initial_capital, transaction_cost_pct=cost,
                   slippage_pct=slippage, execution_delay=delay)
    original = run_backtest(full, **options)
    columns = [c for c in full if c not in PRICE_COLUMNS]
    cutoffs = np.unique(np.linspace(minimum, len(raw) - 1, sample_count, dtype=int))
    rows = []
    for n in cutoffs:
        try:
            prefix = fn(raw.iloc[:n].copy(), **params)
            prefix_ok, a = _compare_frames(full[columns].iloc[:n], prefix[columns])
            changed = raw.copy()
            # Only observations strictly after the cutoff change; earlier OHLC is untouched.
            factors = np.linspace(0.5, 1.5, len(raw) - n)
            changed.loc[changed.index[n:], ["Open", "High", "Low", "Close"]] *= factors[:, None]
            altered = fn(changed, **params)
            future_ok, b = _compare_frames(full[columns].iloc[:n], altered[columns].iloc[:n])
            prefix_result = run_backtest(prefix, **options)
            portfolio_ok, c = _compare_frames(original.equity.iloc[:n], prefix_result.equity)
            rows.append({"Cutoff": raw.index[n - 1], "Prefix indicators": "Pass" if prefix_ok else "Fail",
                         "Changed future": "Pass" if future_ok else "Fail",
                         "Portfolio prefix": "Pass" if portfolio_ok else "Fail",
                         "Status": "Pass" if prefix_ok and future_ok and portfolio_ok else "Fail",
                         "Details": "; ".join(x for x in [a, b, c] if x)})
        except (ValueError, KeyError) as exc:
            rows.append({"Cutoff": raw.index[n - 1], "Prefix indicators": "Not tested",
                         "Changed future": "Not tested", "Portfolio prefix": "Not tested",
                         "Status": "Error", "Details": str(exc)})
    return pd.DataFrame(rows)
