"""Metrics computed from net equity and completed round trips, without rounding inputs."""
import numpy as np
from backtester import BacktestResult


def calculate_metrics(result: BacktestResult, risk_free_rate_pct=0.0, periods_per_year=252):
    if not np.isfinite(risk_free_rate_pct) or risk_free_rate_pct <= -100:
        raise ValueError("Annual risk-free rate must be finite and above -100%.")
    if not np.isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("Trading periods per year must be positive.")
    equity, trades = result.equity, result.trades
    returns = equity["Daily Return"]
    std = float(returns.std(ddof=1)) if len(returns) > 1 else np.nan
    daily_rf = (1 + risk_free_rate_pct / 100) ** (1 / periods_per_year) - 1
    sharpe = ((float(returns.mean()) - daily_rf) / std * np.sqrt(periods_per_year)
              if np.isfinite(std) and std > 1e-12 else np.nan)
    pnl = trades["Net P&L"].astype(float)
    winners, losers = pnl[pnl > 1e-8], pnl[pnl < -1e-8]
    gross_profit, gross_loss = float(winners.sum()), float(-losers.sum())
    profit_factor = (gross_profit / gross_loss if gross_loss > 0 else
                     np.inf if gross_profit > 0 else np.nan)
    return {
        "Initial capital": result.initial_capital,
        "Final portfolio value": float(equity.Equity.iloc[-1]),
        "Total return %": (equity.Equity.iloc[-1] / result.initial_capital - 1) * 100,
        "Buy-and-hold return %": (equity["Buy & Hold"].iloc[-1] / result.initial_capital - 1) * 100,
        "Completed trades": len(trades), "Winning trades": len(winners), "Losing trades": len(losers),
        "Breakeven trades": len(pnl) - len(winners) - len(losers),
        "Win rate %": len(winners) / len(trades) * 100 if len(trades) else np.nan,
        "Average P&L per trade": float(pnl.mean()) if len(trades) else np.nan,
        "Maximum drawdown %": -float(equity.Drawdown.min()) * 100,
        "Annualized volatility %": std * np.sqrt(periods_per_year) * 100,
        "Sharpe ratio": sharpe, "Profit factor": profit_factor,
        "Realized P&L": float(equity["Realized P&L"].iloc[-1]),
        "Unrealized P&L": float(equity["Unrealized P&L"].iloc[-1]),
        "Total transaction costs": float(equity["Cumulative Fees"].iloc[-1]),
        "Total modeled slippage": float(equity["Cumulative Slippage"].iloc[-1]) if "Cumulative Slippage" in equity else 0.0,
        "Final cash": float(equity.Cash.iloc[-1]), "Final holdings": float(equity.Holdings.iloc[-1]),
    }
