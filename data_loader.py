"""Fetch daily adjusted OHLCV bars; never fill prices from future observations."""
from datetime import date, datetime, timedelta, timezone
import re

import numpy as np
import pandas as pd
import yfinance as yf


class DataError(ValueError):
    """An actionable market-data or input error."""


def normalize_ticker(ticker):
    """Accept a single provider symbol, never a list of stocks in one request."""
    if not isinstance(ticker, str):
        raise DataError("Enter a Yahoo Finance ticker as text.")
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.&^=\-]{0,29}", ticker):
        raise DataError("Enter one valid Yahoo Finance ticker, such as AAPL or RELIANCE.NS.")
    return ticker


def search_stocks(query):
    """Search current listings; these labels never enter historical trading signals."""
    query = query.strip() if isinstance(query, str) else ""
    if not query or len(query) > 100:
        raise DataError("Enter a company name or ticker between 1 and 100 characters.")
    try:
        quotes = yf.Search(query, max_results=15, news_count=0, lists_count=0,
                           include_cb=False, timeout=15, raise_errors=True).quotes
    except Exception as exc:
        raise DataError(
            "Company search is unavailable. Yahoo may be rate-limiting requests. "
            "Wait and try again, or choose Enter ticker if you know the symbol."
        ) from exc
    if not isinstance(quotes, list):
        raise DataError("Yahoo returned an unexpected search response. Try again later or enter a ticker.")
    matches, seen = [], set()
    for quote in quotes:
        if not isinstance(quote, dict) or quote.get("quoteType") not in {"EQUITY", "ETF", "INDEX"}:
            continue  # Exclude currencies/crypto: this engine assumes stock-market sessions.
        try:
            symbol = normalize_ticker(quote.get("symbol", ""))
        except DataError:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        matches.append({
            "symbol": symbol,
            "name": str(quote.get("longname") or quote.get("shortname") or symbol),
            "exchange": str(quote.get("exchDisp") or quote.get("exchange") or "Exchange unavailable"),
            "type": quote["quoteType"],
        })
    return matches


def validate_request(ticker, start, end):
    ticker = normalize_ticker(ticker)
    try:
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        if pd.isna(start) or pd.isna(end):
            raise ValueError
        start, end = start.date(), end.date()
    except (ValueError, TypeError):
        raise DataError("Enter valid start and end dates.") from None
    if start > end:
        raise DataError("Start date must be on or before end date.")
    if end >= date.today():
        raise DataError("Choose an end date before today to exclude an unfinished daily bar.")
    return ticker, start, end


def clean_market_data(raw):
    """Drop invalid bars and disclose removals; do not fabricate market prices."""
    if raw is None or raw.empty:
        raise DataError("No data returned. Check the ticker, dates, connection, or provider limits.")
    data = raw.copy()
    if isinstance(data.columns, pd.MultiIndex):
        # yfinance can return (Price, Ticker) even for a single symbol.
        levels = [i for i in range(data.columns.nlevels)
                  if {"Open", "High", "Low", "Close"}.issubset(data.columns.get_level_values(i))]
        if not levels:
            raise DataError("The provider returned unrecognized price columns.")
        data.columns = data.columns.get_level_values(levels[0])
    if data.columns.duplicated().any():
        raise DataError("Expected data for exactly one ticker.")
    required = ["Open", "High", "Low", "Close"]
    if not set(required).issubset(data.columns):
        raise DataError("Market data is missing required OHLC price columns.")
    original_count = len(data)
    data.index = pd.to_datetime(data.index, errors="coerce")
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    data.index = data.index.normalize()
    data = data.loc[~data.index.isna()]
    data = data.loc[~data.index.duplicated(keep="last")].sort_index()
    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data[required] = data[required].replace([np.inf, -np.inf], np.nan)
    valid = data[required].notna().all(axis=1) & (data[required] > 0).all(axis=1)
    valid &= data.High >= data[["Open", "Close", "Low"]].max(axis=1)
    valid &= data.Low <= data[["Open", "Close", "High"]].min(axis=1)
    data = data.loc[valid].copy()
    if data.empty:
        raise DataError("No usable price bars remain after removing missing or invalid values.")
    if "Volume" not in data:
        data["Volume"] = np.nan
    data["Volume"] = pd.to_numeric(data.Volume, errors="coerce")
    data.index.name = "Date"
    data = data[required + ["Volume"]]
    data.attrs["removed_rows"] = original_count - len(data)
    return data


def load_market_data(ticker, start, end):
    ticker, start, end = validate_request(ticker, start, end)
    try:
        raw = yf.download(
            ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
            interval="1d", auto_adjust=True, progress=False, threads=False,
            timeout=20, multi_level_index=False,
        )
    except Exception as exc:
        raise DataError("Market download failed. Check your connection, or wait and retry if Yahoo is rate-limiting requests.") from exc
    data = clean_market_data(raw)
    removed = data.attrs.get("removed_rows", 0)
    data = data.loc[str(start):str(end)].copy()
    if data.empty:
        raise DataError("There are no trading sessions in the selected dates.")
    data.attrs.update(ticker=ticker, removed_rows=removed, source="Yahoo Finance (adjusted)",
                      fetched_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return data


def generate_demo_data(start, end):
    """Deterministic synthetic bars for offline demos, never presented as real quotes."""
    _, start, end = validate_request("DEMO", start, end)
    dates = pd.bdate_range(start, end)
    if len(dates) == 0:
        raise DataError("Choose a range containing at least one weekday.")
    rng = np.random.default_rng(42)
    t = np.arange(len(dates))
    returns = 0.0003 + 0.007 * np.sin(t / 17) + rng.normal(0, 0.01, len(t))
    close = 100 * np.exp(np.cumsum(returns))
    previous = np.r_[100, close[:-1]]
    opens = previous * np.exp(rng.normal(0, 0.003, len(t)))
    spread = rng.uniform(0.002, 0.012, len(t))
    data = pd.DataFrame({"Open": opens, "High": np.maximum(opens, close) * (1 + spread),
                         "Low": np.minimum(opens, close) * (1 - spread), "Close": close,
                         "Volume": rng.integers(100000, 2000000, len(t))}, index=dates)
    data.index.name = "Date"
    data.attrs.update(ticker="DEMO", source="Synthetic demonstration", removed_rows=0)
    return data
