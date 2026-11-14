"""Strategy contract: unshifted close-time Signal (+1 buy, -1 sell, 0 wait)."""
from numbers import Integral
import numpy as np
import pandas as pd


def validate_period(value, name="Period"):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def prepare_data(data, min_rows):
    if "Close" not in data or len(data) < min_rows:
        raise ValueError(f"This strategy needs at least {min_rows} usable daily bars. Extend the dates.")
    close = pd.to_numeric(data.Close, errors="coerce")
    if not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError("Strategies require finite, positive closing prices.")
    if not data.index.is_monotonic_increasing or data.index.has_duplicates:
        raise ValueError("Strategy data must have a sorted, unique date index.")
    result = data.copy()
    result["Signal"] = 0
    return result


from .moving_average import moving_average_strategy
from .rsi import rsi_strategy
from .momentum import momentum_strategy

STRATEGIES = {
    "Moving Average Crossover": moving_average_strategy,
    "RSI Strategy": rsi_strategy,
    "Momentum Strategy": momentum_strategy,
}

__all__ = ["STRATEGIES", "moving_average_strategy", "rsi_strategy", "momentum_strategy"]
