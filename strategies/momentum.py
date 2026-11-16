"""Momentum is the percentage price change over the previous lookback bars."""
import numpy as np
from . import prepare_data, validate_period


def momentum_strategy(data, lookback=20, entry_threshold=5.0, exit_threshold=0.0):
    validate_period(lookback, "Momentum lookback")
    if not (np.isfinite(entry_threshold) and np.isfinite(exit_threshold)):
        raise ValueError("Momentum thresholds must be finite numbers.")
    if exit_threshold >= entry_threshold:
        raise ValueError("Momentum exit threshold must be below the entry threshold.")
    result = prepare_data(data, lookback + 2)
    result["Momentum"] = (result.Close / result.Close.shift(lookback) - 1) * 100
    result.loc[result.Momentum > entry_threshold, "Signal"] = 1
    result.loc[result.Momentum < exit_threshold, "Signal"] = -1
    return result
