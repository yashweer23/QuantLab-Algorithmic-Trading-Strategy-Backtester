"""Trade actual SMA crossovers, not merely an already-existing trend."""
from . import prepare_data, validate_period


def moving_average_strategy(data, short_window=20, long_window=50):
    validate_period(short_window, "Short MA")
    validate_period(long_window, "Long MA")
    if short_window >= long_window:
        raise ValueError("Short MA must be strictly smaller than long MA.")
    # Two valid long-MA values detect a crossover; one further bar permits execution.
    result = prepare_data(data, long_window + 2)
    result["Short_MA"] = result.Close.rolling(short_window, min_periods=short_window).mean()
    result["Long_MA"] = result.Close.rolling(long_window, min_periods=long_window).mean()
    spread = result.Short_MA - result.Long_MA
    result.loc[(spread > 0) & (spread.shift(1) <= 0), "Signal"] = 1
    result.loc[(spread < 0) & (spread.shift(1) >= 0), "Signal"] = -1
    return result
