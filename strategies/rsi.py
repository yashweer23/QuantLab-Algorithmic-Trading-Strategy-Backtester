"""Wilder RSI: SMA seed followed by recursive smoothing of gains and losses."""
import numpy as np
import pandas as pd
from . import prepare_data, validate_period


def calculate_rsi(close, period=14):
    validate_period(period, "RSI period")
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    values = np.full(len(close), np.nan)
    if len(close) <= period:
        return pd.Series(values, index=close.index, name="RSI")
    avg_gain = float(gain.iloc[1:period + 1].mean())
    avg_loss = float(loss.iloc[1:period + 1].mean())
    for i in range(period, len(close)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gain.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss.iloc[i]) / period
        if avg_gain == 0 and avg_loss == 0:
            values[i] = 50.0  # A flat market is neutral, not overbought.
        elif avg_loss == 0:
            values[i] = 100.0
        else:
            values[i] = 100 - 100 / (1 + avg_gain / avg_loss)
    return pd.Series(values, index=close.index, name="RSI")


def rsi_strategy(data, period=14, lower=30.0, upper=70.0):
    validate_period(period, "RSI period")
    if not (np.isfinite(lower) and np.isfinite(upper) and 0 <= lower < upper <= 100):
        raise ValueError("RSI thresholds must satisfy 0 ≤ buy < sell ≤ 100.")
    result = prepare_data(data, period + 2)
    result["RSI"] = calculate_rsi(result.Close, period)
    # Repeated intents are harmless: the engine ignores buys while already long.
    result.loc[result.RSI < lower, "Signal"] = 1
    result.loc[result.RSI > upper, "Signal"] = -1
    return result
