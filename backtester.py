"""Event-driven, long-only accounting with close signals and next-open fills."""
from dataclasses import dataclass
from numbers import Integral
import numpy as np
import pandas as pd

ORDER_COLUMNS = ["Date", "Signal Date", "Side", "Price", "Quantity", "Notional", "Fee",
                 "Cash After", "Holdings After", "Realized P&L", "Order ID", "Market Open",
                 "Slippage Cost", "Cash Before", "Holdings Before", "Cost Basis Before", "Cost Basis After"]
TRADE_COLUMNS = ["Entry Date", "Exit Date", "Entry Price", "Exit Price", "Quantity",
                 "Entry Fee", "Exit Fee", "Net P&L", "Return %", "Holding Days"]


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    orders: pd.DataFrame
    trades: pd.DataFrame
    initial_capital: float
    transaction_cost_pct: float
    slippage_pct: float = 0.0
    execution_delay: int = 1


def run_backtest(data, initial_capital=100000.0, transaction_cost_pct=0.1, *,
                 slippage_pct=0.0, execution_delay=1):
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("Initial capital must be a finite positive number.")
    if not np.isfinite(transaction_cost_pct) or not 0 <= transaction_cost_pct < 100:
        raise ValueError("Transaction cost must be at least 0% and below 100%.")
    if not np.isfinite(slippage_pct) or not 0 <= slippage_pct < 100:
        raise ValueError("Slippage must be at least 0% and below 100%.")
    if isinstance(execution_delay, bool) or not isinstance(execution_delay, Integral) or execution_delay < 1:
        raise ValueError("Execution delay must be a positive integer number of available bars.")
    if data.empty or not {"Open", "Close", "Signal"}.issubset(data.columns):
        raise ValueError("Backtest requires nonempty Open, Close, and Signal columns.")
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.hasnans:
        raise ValueError("Backtest requires valid dates.")
    if not data.index.is_monotonic_increasing or data.index.has_duplicates:
        raise ValueError("Dates must be sorted and unique.")
    prices = data[["Open", "Close"]].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Execution and closing prices must be finite and positive.")
    if not data.Signal.isin([-1, 0, 1]).all():
        raise ValueError("Signals must be -1 (sell), 0 (wait), or 1 (buy).")

    fee_rate = transaction_cost_pct / 100
    slip_rate, total_slippage = slippage_pct / 100, 0.0
    cash, quantity, cost_basis, realized, total_fees = float(initial_capital), 0.0, 0.0, 0.0, 0.0
    entry = None
    orders, trades, daily = [], [], []
    # A delay of 1 is the next open. Additional delays retain the original intent.
    executable = data.Signal.shift(execution_delay, fill_value=0)
    benchmark_quantity = initial_capital / (float(data.Open.iloc[0]) * (1 + slip_rate) * (1 + fee_rate))
    for i, (day, row) in enumerate(data.iterrows()):
        intent, market_open = int(executable.iloc[i]), float(row.Open)
        before = (cash, quantity, cost_basis)
        order_count = len(orders)
        if intent == 1 and quantity == 0:
            price = market_open * (1 + slip_rate)  # Adverse fill; do not alter indicator prices.
            quantity = cash / (price * (1 + fee_rate))
            notional = quantity * price
            fee = notional * fee_rate
            cost_basis = notional + fee
            cash = max(0.0, cash - cost_basis)  # Only floating-point dust is clipped.
            entry = {"date": day, "price": price, "fee": fee}
            total_fees += fee
            orders.append([day, data.index[i - execution_delay], "BUY", price, quantity, notional, fee,
                           cash, quantity, np.nan])
        elif intent == -1 and quantity > 0:
            price = market_open * (1 - slip_rate)
            sold_quantity = quantity
            notional = quantity * price
            fee = notional * fee_rate
            proceeds = notional - fee
            pnl = proceeds - cost_basis  # Both entry and exit costs reduce profit.
            realized += pnl
            cash += proceeds
            total_fees += fee
            trades.append([entry["date"], day, entry["price"], price, quantity,
                           entry["fee"], fee, pnl, pnl / cost_basis * 100,
                           (day - entry["date"]).days])
            quantity, cost_basis, entry = 0.0, 0.0, None
            orders.append([day, data.index[i - execution_delay], "SELL", price, sold_quantity, notional,
                           fee, cash, quantity, pnl])
        if len(orders) > order_count:
            # Slippage is already in the fill price; never debit it again as a fee.
            slippage = abs(price - market_open) * orders[-1][4]
            total_slippage += slippage
            orders[-1].extend([len(orders), market_open, slippage, *before, cost_basis])
        market_value = quantity * float(row.Close)
        unrealized = market_value - cost_basis if quantity > 0 else 0.0
        daily.append([day, cash, quantity, market_value, cash + market_value, realized,
                      unrealized, total_fees, benchmark_quantity * float(row.Close), cost_basis, total_slippage])
    equity = pd.DataFrame(daily, columns=["Date", "Cash", "Holdings", "Market Value", "Equity",
                                         "Realized P&L", "Unrealized P&L", "Cumulative Fees",
                                         "Buy & Hold", "Cost Basis", "Cumulative Slippage"]).set_index("Date")
    # Initial capital is part of the high-water mark, including first-day entry fees.
    equity["Drawdown"] = equity.Equity / equity.Equity.cummax().clip(lower=initial_capital) - 1
    equity["Daily Return"] = equity.Equity.pct_change(fill_method=None)
    equity.iloc[0, equity.columns.get_loc("Daily Return")] = equity.Equity.iloc[0] / initial_capital - 1
    return BacktestResult(equity, pd.DataFrame(orders, columns=ORDER_COLUMNS),
                          pd.DataFrame(trades, columns=TRADE_COLUMNS),
                          float(initial_capital), float(transaction_cost_pct), float(slippage_pct), int(execution_delay))
