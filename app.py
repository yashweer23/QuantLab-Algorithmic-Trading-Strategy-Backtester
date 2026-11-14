"""QuantLab research workspace. Run with: python -m streamlit run app.py."""
from datetime import date, timedelta
from html import escape
from io import BytesIO
import json
import zipfile

import pandas as pd
import streamlit as st

from backtester import run_backtest
from data_loader import DataError, load_market_data, search_stocks
from metrics import calculate_metrics
from research_ui import failure_report_tab, trade_evidence_tab
from strategies import STRATEGIES
from ui import (brand, drawdown_chart, equity_chart, fmt, html,
                install_theme, monthly_return_chart, plot, price_chart, section_title,
                small_stat, sparkline, tone, ASSETS)

st.set_page_config(page_title="QuantLab — Strategy research", page_icon=str(ASSETS / "quantlab-icon.svg"), layout="wide", initial_sidebar_state="collapsed")
install_theme()

STRATEGY_NOTES = {
    "Moving Average Crossover": ("Follow the trend.", "Enter on a bullish moving-average crossover. Exit when the trend reverses."),
    "RSI Strategy": ("Find the reversal.", "Buy below the oversold threshold. Exit above the overbought threshold."),
    "Momentum Strategy": ("Trade the momentum.", "Enter when lookback returns clear your threshold. Exit when momentum weakens."),
}


@st.cache_data(ttl=3600, show_spinner=False, max_entries=32)
def cached_market_data(ticker, start, end):
    return load_market_data(ticker, start, end)


@st.cache_data(ttl=900, show_spinner=False, max_entries=128)
def cached_stock_search(query):
    return search_stocks(query)


def market_picker():
    """A new search requires explicit selection; never guess the user's exchange."""
    mode = st.radio("Find a market", ["Search companies", "Enter ticker"], horizontal=True, key="lookup_mode")
    if mode == "Enter ticker":
        ticker = st.text_input("Ticker symbol", placeholder="AAPL, RELIANCE.NS, TCS.NS…",
                               key="custom_ticker", max_chars=30).strip().upper()
        st.caption("Use Yahoo symbols: .NS for NSE, .BO for BSE. Examples: MSFT, SPY, ^NSEI.")
        return dict(ticker=ticker, company="", exchange="", asset_type="")

    with st.form("company_search_form", border=False):
        query = st.text_input("Company name or ticker", placeholder="Try Apple, Reliance, or TCS",
                              key="stock_query", max_chars=100)
        search = st.form_submit_button("Search stocks", icon=":material/search:", width="stretch", key="search_stocks")
    if search:
        # Clear old selections even when this lookup fails, to avoid testing the wrong stock.
        st.session_state.pop("selected_stock", None)
        lookup = dict(query=query.strip(), matches=[], error="")
        try:
            with st.spinner("Searching companies…"):
                lookup["matches"] = cached_stock_search(query.strip())
        except DataError as exc:
            lookup["error"] = str(exc)
        st.session_state["stock_lookup"] = lookup

    lookup = st.session_state.get("stock_lookup")
    if lookup:
        if lookup["error"]:
            st.error(lookup["error"])
        elif not lookup["matches"]:
            st.info("No matching stocks, ETFs or indices returned. Try a shorter name or use Enter ticker.")
        else:
            st.caption(f"Results for ‘{lookup['query']}’. Select the company and exchange you want.")
            by_symbol = {item["symbol"]: item for item in lookup["matches"]}
            symbol = st.selectbox("Matching listings", list(by_symbol), index=None,
                placeholder="Choose a company and exchange", key="selected_stock",
                format_func=lambda s: f"{by_symbol[s]['name']} · {s} · {by_symbol[s]['exchange']} · {by_symbol[s]['type']}")
            if symbol:
                item = by_symbol[symbol]
                return dict(ticker=symbol, company=item["name"], exchange=item["exchange"], asset_type=item["type"])
    else:
        st.caption("Search real stocks, ETFs and indices covered by Yahoo Finance. No API key needed.")
    return dict(ticker="", company="", exchange="", asset_type="")


def top_controls():
    """Keep setup above the results, with four responsive groups on desktop."""
    with st.container(key="setup_panel"):
        html('<div class="setup-heading"><strong>Backtest setup</strong><span>One market. Your rules. Every trade explained.</span></div>')
        with st.container(key="setup_grid"):
            market_col, period_col, strategy_col, capital_col = st.columns([1.65, 1, 1.25, 1.15], gap="medium")
            with market_col:
                html('<div class="control-section"><span>01</span> MARKET</div>')
                market = market_picker()
            with period_col:
                html('<div class="control-section"><span>02</span> PERIOD</div>')
                yesterday = date.today() - timedelta(days=1)
                # Each date occupies its entire group width, without truncated years.
                start = st.date_input("Start date", value=yesterday - timedelta(days=3 * 365),
                                      min_value=date(1970, 1, 1), max_value=yesterday, key="start",
                                      format="DD/MM/YYYY", width="stretch")
                end = st.date_input("End date", value=yesterday, min_value=date(1970, 1, 1),
                                    max_value=yesterday, key="end", format="DD/MM/YYYY", width="stretch")
                st.caption("Daily history · End date included")
            with strategy_col:
                html('<div class="control-section"><span>03</span> STRATEGY</div>')
                strategy = st.selectbox("Trading rule", list(STRATEGIES), key="strategy")
                params = {}
                if strategy == "Moving Average Crossover":
                    left, right = st.columns(2)
                    params["short_window"] = left.number_input("Short MA", 1, 500, 20, key="short")
                    params["long_window"] = right.number_input("Long MA", 2, 1000, 50, key="long")
                    st.caption("Buy on an upward crossover. Sell on a downward crossover.")
                elif strategy == "RSI Strategy":
                    params["period"] = st.number_input("RSI period", 2, 250, 14, key="rsi_period")
                    left, right = st.columns(2)
                    params["lower"] = left.number_input("Buy below", 0.0, 100.0, 30.0, key="rsi_lower")
                    params["upper"] = right.number_input("Sell above", 0.0, 100.0, 70.0, key="rsi_upper")
                else:
                    params["lookback"] = st.number_input("Lookback period", 1, 500, 20, key="lookback")
                    left, right = st.columns(2)
                    params["entry_threshold"] = left.number_input("Entry (%)", -100.0, 1000.0, 5.0, key="entry")
                    params["exit_threshold"] = right.number_input("Exit (%)", -100.0, 1000.0, 0.0, key="exit")
            with capital_col:
                html('<div class="control-section"><span>04</span> CAPITAL & COSTS</div>')
                capital = st.number_input("Starting capital", min_value=1.0, max_value=1e12, value=100000.0,
                                          step=1000.0, key="capital", help="Measured in the asset's quote units; no currency conversion.")
                cost = st.number_input("Cost per side (%)", min_value=0.0, max_value=20.0, value=0.1,
                                       step=0.01, format="%.2f", key="cost", help="0.1 means 0.1% of each buy and sell's notional.")
                risk_free = st.number_input("Risk-free rate (%)", 0.0, 50.0, 0.0, step=0.25, key="risk_free",
                                            help="Annual rate used for Sharpe; cash earns no interest in this model.")
        with st.container(key="setup_actions"):
            details, action = st.columns([3.5, 1], gap="medium", vertical_alignment="center")
            with details:
                if market["ticker"]:
                    html(f'<div class="setup-status"><span class="status-dot"></span><strong>{escape(market["ticker"])}</strong><span>Ready to backtest · Simulated execution</span></div>')
                else:
                    st.caption("Select a search result or enter a ticker to continue.")
                with st.expander("Data & execution details"):
                    st.caption("Yahoo Finance · Daily adjusted prices · next-open fills · long only · fractional units. End date is inclusive. Indian shares use .NS or .BO. Indices are research proxies. No real orders are placed.")
                    if st.button("Clear market-data cache", key="clear_market_cache"):
                        cached_market_data.clear()
                        cached_stock_search.clear()
                        st.success("Cache cleared. Search or run again to refresh.")
            with action:
                run = st.button("Run backtest", type="primary", width="stretch", key="run", icon=":material/play_arrow:",
                                disabled=not market["ticker"])
    config = dict(source="Yahoo Finance", **market, start=str(start), end=str(end),
                  capital=capital, cost=cost, strategy=strategy, params=params, risk_free=risk_free)
    return config, run


def run_report(config):
    data = cached_market_data(config["ticker"], config["start"], config["end"])
    signals = STRATEGIES[config["strategy"]](data, **config["params"])
    result = run_backtest(signals, config["capital"], config["cost"])
    stats = calculate_metrics(result, config["risk_free"])
    return config, signals, result, stats


def export_report(saved, result, stats, signals):
    """Export the saved run, even when the setup panel contains pending edits."""
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("orders.csv", result.orders.to_csv(index=False))
        archive.writestr("completed_trades.csv", result.trades.to_csv(index=False))
        archive.writestr("daily_equity.csv", result.equity.to_csv())
        archive.writestr("metrics.csv", pd.DataFrame(list(stats.items()), columns=["Metric", "Value"]).to_csv(index=False))
        archive.writestr("parameters.json", json.dumps(saved, indent=2))
        archive.writestr("data_metadata.json", json.dumps({
            "source": signals.attrs.get("source", saved["source"]),
            "symbol": saved["ticker"],
            "first_bar": str(signals.index[0].date()),
            "last_bar": str(signals.index[-1].date()),
            "daily_bars": len(signals),
            "removed_rows": signals.attrs.get("removed_rows", 0),
            "fetched_at_utc": signals.attrs.get("fetched_at_utc"),
            "synthetic": saved["source"] != "Yahoo Finance",
        }, indent=2))
    return output.getvalue()


def summary_card(saved, stats):
    excess = stats["Total return %"] - stats["Buy-and-hold return %"]
    title, description = STRATEGY_NOTES[saved["strategy"]]
    params = saved["params"]
    if "short_window" in params:
        rule = f"SMA {params['short_window']} / {params['long_window']}"
    elif "period" in params:
        rule = f"RSI {params['period']} · {params['lower']:g} / {params['upper']:g}"
    else:
        rule = f"{params['lookback']}-day momentum · {params['entry_threshold']:g}% / {params['exit_threshold']:g}%"
    html(f'''<div class="summary-card"><div class="summary-eyebrow">THE STRATEGY</div>
    <h2 class="summary-heading">{escape(title)}</h2><div class="summary-description">{escape(description)}</div>
    <div class="summary-row"><span>Strategy return</span><strong>{fmt(stats['Total return %'], '%', signed=True)}</strong></div>
    <div class="summary-row"><span>Buy & hold return</span><strong>{fmt(stats['Buy-and-hold return %'], '%', signed=True)}</strong></div>
    <div class="summary-row accent {'under' if excess < 0 else ''}"><span>Difference</span><strong>{fmt(excess, ' pp', signed=True)}</strong></div>
    <div class="summary-row"><span>Initial capital</span><strong>{fmt(stats['Initial capital'], decimals=0)}</strong></div>
    <div class="summary-footer"><div class="summary-label">{escape(rule)}</div>
    <span class="summary-badge">LONG ONLY</span> <span class="summary-badge">NEXT-OPEN FILLS</span>
    <p>Same dates. Same starting capital.<br>All returns include modeled trading costs.</p></div></div>''')


def performance_tab(saved, signals, result, stats):
    eq = result.equity
    specs = [("Total return", "Total return %", "%", f"{fmt(stats['Final portfolio value'] - stats['Initial capital'], signed=True)} net P&L", "normal"),
             ("Max. drawdown", "Maximum drawdown %", "%", "Largest decline from peak", "off"),
             ("Sharpe ratio", "Sharpe ratio", "", "Risk-adjusted daily returns", "off"),
             ("Win rate", "Win rate %", "%", f"{stats['Winning trades']} wins / {stats['Completed trades']} closed trades", "off")]
    for col, (label, key, suffix, note, color) in zip(st.columns(4), specs):
        col.metric(label, fmt(stats[key], suffix), delta=note, delta_color=color)
    st.write("")
    main, aside = st.columns([2.2, 1], gap="medium")
    with main:
        with st.container(key="equity_panel"):
            left, right = st.columns([2, 1])
            with left:
                html(f'''<div class="eyebrow">PORTFOLIO VALUE</div>
                <div class="portfolio-value">{fmt(stats['Final portfolio value'])}</div>
                <div class="portfolio-gain"><span class="gain-pill {tone(stats['Total return %'])}">{fmt(stats['Total return %'], '%', signed=True)}</span>
                <span>over the selected period</span></div>''')
            with right:
                mode = st.selectbox("Equity chart display", ["Portfolio value", "Cumulative return"], key="equity_display", label_visibility="collapsed")
            html('<div class="chart-legend"><span><i class="legend-dot"></i>Strategy</span><span><i class="legend-dot purple"></i>Buy & hold</span></div>')
            plot(equity_chart(eq, result.initial_capital, mode == "Cumulative return"), "equity_chart")
            html(f'<div class="card-footer"><span>{eq.index[0]:%d %b %Y} — {eq.index[-1]:%d %b %Y}</span><span><strong>{len(eq):,}</strong> trading sessions · quote units</span></div>')
    with aside:
        summary_card(saved, stats)
    with st.container(key="quality_panel"):
        for col, label, value, note in zip(st.columns(4),
            ["Completed trades", "Profit factor", "Annual volatility", "Transaction costs"],
            [fmt(stats["Completed trades"], decimals=0), fmt(stats["Profit factor"]), fmt(stats["Annualized volatility %"], "%"), fmt(stats["Total transaction costs"])],
            ["Closed round trips", "Gross wins / gross losses", "252-session convention", f"{saved['cost']:g}% on each side"]):
            with col:
                small_stat(label, value, note)
    with st.container(key="price_panel"):
        left, right = st.columns([4, 1])
        with left:
            section_title("Price action & executions", "Actual fills overlaid on adjusted market prices.")
        with right:
            chart_type = st.selectbox("Price display", ["Candlestick", "Closing price"], key="display", label_visibility="collapsed")
        close = float(signals.Close.iloc[-1])
        change = (close / float(signals.Close.iloc[-2]) - 1) * 100 if len(signals) > 1 else 0
        html(f'<div class="market-quote"><strong>{fmt(close)}</strong><span class="{tone(change)}">{fmt(change, "%", signed=True)}<small>last session</small></span>{sparkline(signals.Close.tail(60))}</div>')
        plot(price_chart(signals, result.orders, saved["params"], chart_type), "price_chart")
        html('<div class="card-footer"><span>▲ BUY &nbsp; ▾ SELL · markers show next-open fills</span><span>Daily bars · adjusted prices</span></div>')
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(key="risk_panel"):
            section_title("Drawdown", "Distance below the portfolio's previous peak.")
            plot(drawdown_chart(eq), "drawdown_chart")
    with right:
        with st.container(key="monthly_panel"):
            section_title("Monthly returns", "Latest 18 months · first and last months may be partial.")
            plot(monthly_return_chart(eq, result.initial_capital), "monthly_chart")


def trade_table(frame, key):
    formats = {}
    for col in frame:
        if "Date" in col:
            formats[col] = st.column_config.DateColumn(col, format="DD MMM YYYY")
        elif col == "Order ID":
            formats[col] = st.column_config.NumberColumn(col, format="%d")
        elif col in ["Quantity", "Holdings After"]:
            formats[col] = st.column_config.NumberColumn(col, format="%.4f")
        elif pd.api.types.is_numeric_dtype(frame[col]):
            formats[col] = st.column_config.NumberColumn(col, format="%.2f")
    st.dataframe(frame, hide_index=True, width="stretch", column_config=formats, key=key)


def ledger_tab(saved, result, stats, symbol):
    section_title("Every execution. Fully accounted for.", "Inspect when a decision was made, where it filled, and what it cost.")
    for col, key in zip(st.columns(4), ["Final cash", "Final holdings", "Realized P&L", "Unrealized P&L"]):
        col.metric(key, fmt(stats[key], decimals=4 if key == "Final holdings" else 2))
    position = "Long position open" if stats["Final holdings"] > 0 else "Portfolio in cash"
    html(f'<div class="position-strip"><strong>{position}</strong><span>Open positions are marked at the final close.</span></div>')
    st.write("")
    left, right = st.columns([4, 1])
    with left:
        html(f'<div class="ledger-title-row"><h3 class="section-title">Order history</h3><span class="count-badge">{len(result.orders)} orders</span></div>')
    with right:
        side = st.selectbox("Filter orders", ["All orders", "BUY", "SELL"], key="order_filter", label_visibility="collapsed")
    visible = result.orders if side == "All orders" else result.orders.loc[result.orders.Side == side]
    trade_table(visible, "order_table")
    st.caption("Blank realized P&L on a buy is expected. Both buy and sell fees are included when a trade closes.")
    st.write("")
    section_title("Completed round trips", "A matched buy and sell form one completed trade.")
    trade_table(result.trades, "trade_table")
    with st.expander("Daily cash, holdings & equity"):
        st.dataframe(result.equity, width="stretch", key="daily_table")
    st.caption("Unrealized P&L includes the entry fee. No hypothetical exit fee is charged on open holdings.")
    downloads = st.columns(3)
    for col, label, frame, filename, index in [
        (downloads[0], "Orders CSV", result.orders, "orders.csv", False),
        (downloads[1], "Closed trades CSV", result.trades, "completed_trades.csv", False),
        (downloads[2], "Daily equity CSV", result.equity, "daily_equity.csv", True),
    ]:
        col.download_button(label, frame.to_csv(index=index).encode("utf-8"), f"{symbol}_{filename}", "text/csv", width="stretch", icon=":material/download:")


def methodology_tab(saved, stats, symbol):
    section_title("Understand the assumptions.", "A transparent model is the starting point for useful research.")
    for col, number, title, body in zip(st.columns(3), ["01 / SIGNALS", "02 / EXECUTION", "03 / MEASUREMENT"],
        ["Decide at the close", "Fill at the next open", "Measure after costs"],
        ["Indicators use the current and previous bars. Warm-up stays in cash. A final-bar signal has no following fill.",
         "One long position with fractional units. No shorting or leverage. Both sides incur transaction costs.",
         "Daily equity includes cash and open holdings. Completed-trade statistics include only matched buy/sell pairs."]):
        with col:
            html(f'<div class="method-card"><div class="number">{number}</div><h4>{title}</h4><p>{body}</p></div>')
    st.write("")
    with st.expander("Benchmark and market-data assumptions", expanded=True):
        st.write("Buy-and-hold invests at the first available open with the same entry fee and stays invested during strategy warm-up. Both portfolios are valued at the last close; open positions are not forcibly sold.")
        st.write("Money is shown in the asset's quote units without currency conversion. Adjusted OHLC is a simplified corporate-action model, not a raw-share dividend ledger. Indices are research proxies. Missing bars can delay fills. Slippage, taxes, market impact, and interest on cash are excluded.")
    with st.expander("How the risk metrics work"):
        st.write("Sharpe uses mean daily excess return divided by sample daily volatility, scaled by √252. The annual risk-free input is converted to a daily rate. Maximum drawdown measures the worst drop from a prior equity peak, including initial capital.")
        st.write("Win rate uses completed round trips after both fees. Profit factor is gross winning P&L divided by absolute losing P&L. With wins and no losses it is infinite. No completed trades gives N/A; zero volatility gives an undefined Sharpe ratio.")
        st.write("Monthly bars use consecutive month-end equity. The first month starts from initial capital; the final month stops at the selected end date.")
    section_title("Complete performance report")
    st.dataframe(pd.DataFrame({"Metric": list(stats), "Value": [fmt(v, decimals=4 if k == "Final holdings" else 2) for k, v in stats.items()]}),
                 width="stretch", hide_index=True, key="metrics_table")
    st.download_button("Run parameters JSON", json.dumps(saved, indent=2), f"{symbol}_parameters.json", "application/json", icon=":material/download:")


def main():
    # Older sessions may contain demo data or lack the new order evidence fields.
    previous = st.session_state.get("report")
    if previous and (previous[0].get("source") != "Yahoo Finance" or "Order ID" not in previous[2].orders):
        st.session_state.pop("report", None)
    brand()
    config, run = top_controls()
    # Fetch only on explicit requests; widget reruns do not send more market downloads.
    if run:
        st.session_state.pop("failure_report", None)
        try:
            with st.spinner("Running your strategy…"):
                st.session_state["report"] = run_report(config)
        except (DataError, ValueError) as exc:
            st.session_state.pop("report", None)
            st.error(str(exc))
        except Exception:
            st.session_state.pop("report", None)
            st.error("The backtest could not finish. Check your inputs or retry the market download.")
    if "report" not in st.session_state:
        html('<h1 class="page-heading">Real markets. Your strategy.</h1><p class="page-subtitle">Find a company, explore its history, and put your trading idea to the test.</p>')
        st.info("Search by company name in the top panel, select the right listing, then choose your dates and Run backtest. You can also enter a Yahoo Finance ticker directly.")
        st.caption("Historical daily prices, not a live quote feed. Availability depends on Yahoo Finance coverage.")
        return
    saved, signals, result, stats = st.session_state["report"]
    symbol = saved["ticker"]
    left, right = st.columns([4, 1], vertical_alignment="center")
    with left:
        html('<h1 class="page-heading">Strategy overview</h1><p class="page-subtitle">The full picture of your strategy, from the first signal to the final return.</p>')
    with right:
        st.download_button("Export report", export_report(saved, result, stats, signals), f"{symbol}_backtest_report.zip", "application/zip",
                           width="stretch", icon=":material/download:", key="export")
    html(f'<div class="run-strip"><div class="run-strip-left"><span class="tag asset">{escape(symbol)}</span><span class="tag">{escape(saved["strategy"])}</span><span class="tag">HISTORICAL DATA</span></div><span>{signals.index[0]:%d %b %Y} — {signals.index[-1]:%d %b %Y}</span></div>')
    identity = " · ".join(filter(None, [saved.get("company"), saved.get("exchange"), saved.get("asset_type")]))
    if identity:
        html(f'<p class="page-subtitle">{escape(identity)}</p>')
    fetched = signals.attrs.get("fetched_at_utc")
    stamp = f" · Retrieved {pd.Timestamp(fetched):%d %b %Y %H:%M UTC}" if fetched else ""
    st.caption(f"Yahoo Finance · Daily adjusted prices · Last available bar in selected range: {signals.index[-1]:%d %b %Y}{stamp}")
    if saved != config:
        st.warning("Inputs changed. These are the previous run's results; select Run backtest to update.")
    if signals.attrs.get("removed_rows", 0):
        st.warning(f"Removed {signals.attrs['removed_rows']} invalid or duplicate bars. Executions use the next available valid bar; gaps may affect results.")
    if result.orders.empty:
        st.info("No trades were executed. Capital stayed in cash. Try a longer period or different parameters.")
    elif result.trades.empty:
        st.info("No completed trades yet. Open holdings contribute to equity, but not to win rate or profit factor.")
    performance, failure, evidence, ledger, methodology = st.tabs(
        ["Overview", "Failure report", "Trade evidence", "Trade ledger", "Research notes"])
    with performance:
        performance_tab(saved, signals, result, stats)
    with failure:
        failure_report_tab(saved, signals)
    with evidence:
        trade_evidence_tab(saved, signals, result)
    with ledger:
        ledger_tab(saved, result, stats, symbol)
    with methodology:
        methodology_tab(saved, stats, symbol)
    html('<div class="app-footer"><span><strong>quantlab.</strong> &nbsp; A clearer view of your strategy.</span><span>Educational research only · Not financial advice · Past performance does not predict future returns.</span></div>')


if __name__ == "__main__":
    main()
