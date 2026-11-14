# QuantLab — Algorithmic Trading Strategy Backtester

A modular Python project for researching simple trading rules and explaining their performance. Download daily market data, run one of three independent strategies, stress-test the result, and click actual orders to inspect their decision and accounting evidence.

**Stack:** Python · Pandas · NumPy · yfinance · Plotly · Streamlit  
**Execution model:** long only · one position · fractional units · close-time decisions · next-open fills

## Project overview

This project separates market-data handling, signal generation, portfolio accounting, performance measurement, and presentation. It is intended for a computer science student learning quantitative finance and for placement-interview demonstrations. It models a portfolio rather than simply multiplying price changes by unshifted signals.

## Interface redesign

The workspace uses warm white surfaces, forest-green accents, a locally bundled Inter font, and a clear portfolio-first layout. **Yahoo Finance is the only dashboard data source.** Search for a real company, select its listing and exchange, then run a backtest. The initial page makes no network request and shows no fabricated results.

The QuantLab logo pairs an upward chart with a subtle brain-shaped outline. Its wordmark sits in a compact full-width page header; style injection adds no empty row above it. All setup controls appear in a horizontal panel below it, arranged as **Market**, **Period**, **Strategy**, and **Capital & costs**. The Run backtest action sits at the bottom right of that panel. There is no sidebar or data-source dropdown. Each date field uses the full width of its group; the groups wrap into two columns on smaller screens and stack on phones.

- A larger portfolio value and equity chart lead the Overview tab.
- A strategy summary compares net strategy returns, buy-and-hold, and their difference in percentage points.
- Compact risk/performance cards complement the main chart.
- The chart can switch between portfolio value and cumulative return.
- Candles or closing prices show executed BUY/SELL markers and strategy indicators.
- Drawdown and monthly returns appear side by side. First/last months may be partial; the bar chart displays the latest 18 months.
- The Trade ledger tab filters BUY/SELL orders and formats dates, prices, quantities, and fees.
- **Export report** downloads a ZIP containing orders, completed trades, daily equity, all metrics, the saved run's parameters, and data-source metadata.
- Grouped top-panel controls, responsive styles, and Research notes organize setup and interpretation.
- **Failure report** tests fees, slippage, delayed execution, nearby parameters, and later start dates on the saved market snapshot.
- **Trade evidence** connects clickable order markers to the exact signal-time conditions, fill details, and cash/holdings reconciliation.
- Default strategy signals and next-open execution remain unchanged; explicit stress scenarios can use adverse slippage or additional delay.

### Updating an existing installation

Stop Streamlit with `Ctrl+C`. Extract **quantlab-branding-update.zip** directly into your existing `algorithmic-trading-backtester` folder and allow it to replace matching files. This patch tightens the top spacing and replaces the brand mark and browser-tab icon with an upward chart inside a brain-shaped outline. It updates the theme injection, header styling, vector logo assets, and documentation. Keep your existing virtual environment. It uses the same dependencies and requires no installation command. This patch assumes the horizontal top-controls update is already installed; for a fresh installation use the complete-project ZIP. Run a new backtest after restarting to restore your results in the refreshed layout.

If you created `.venv313` during setup, restart from VS Code's terminal:

```powershell
cd C:\Users\saiya\OneDrive\Documents\Projects\algorithmic-trading-backtester
.\.venv313\Scripts\python.exe -m streamlit run app.py
```

For the complete-project ZIP, copy its contents into the existing project rather than putting a second project directory inside it. Restart Streamlit after updating the theme configuration. If the browser still shows the old styling, hard-refresh with `Ctrl+F5`.

## Features

- Search by company name or ticker and choose a stock, ETF or index with its exchange clearly shown.
- Enter any supported Yahoo Finance ticker directly without using company search.
- Yahoo historical data powers every dashboard run; failed requests never fall back to synthetic data.
- Reports identify the selected listing, actual available dates, and retrieval time (UTC).
- Inclusive start/end dates, starting capital, and per-side transaction costs.
- Configurable moving-average crossover, RSI, and momentum strategies.
- Explicit next-session execution to prevent same-bar look-ahead bias.
- Daily cash, holdings, cost basis, realized/unrealized P&L, and equity.
- Net returns, benchmark returns, closed-trade statistics, drawdown, volatility, Sharpe ratio, and profit factor.
- Interactive candles/closing prices, execution markers, indicators, equity, return comparison, and drawdown charts.
- Complete order ledger and completed-round-trip table, plus CSV exports and run-parameter JSON.
- One-change-at-a-time failure analysis, with skipped and no-trade scenarios distinguished from profitable results.
- Clickable scenario rows and BUY/SELL markers, with native dropdown alternatives.
- Deterministic rule explanations, pre-/post-fill accounting, and per-order JSON downloads.
- Sampled future-data consistency audit and downloadable price/scenario evidence bundles.
- Graceful handling of empty/invalid data, bad parameters, insufficient history, and no-trade results.
- Deterministic tests covering accounting, causality, data cleaning, and Streamlit interactions.

## Architecture

| Path | Responsibility |
|---|---|
| `app.py` | Workspace layout, grouped controls, session state, report and table exports |
| `ui.py` | Presentation helpers, Plotly figures, formatting, and theme loading |
| `assets/theme.css` | Fintech-style layout, component styling, and responsive rules |
| `assets/inter-latin.woff2` | Bundled Inter font, usable offline |
| `assets/quantlab-logo.svg`, `assets/quantlab-icon.svg` | Header wordmark and compact logo |
| `assets/INTER-LICENSE.txt` | Inter SIL Open Font License |
| `data_loader.py` | Company search, listing normalization, input validation, yfinance download, OHLCV cleaning; synthetic fixtures for tests |
| `backtester.py` | Chronological execution, optional slippage/delay, fees, cash/holdings, and evidence-rich ledgers |
| `metrics.py` | Portfolio and completed-trade performance metrics |
| `failure_analysis.py` | Independent stress scenarios, failure summaries, snapshot fingerprints, and ZIP export |
| `trade_evidence.py` | Rule/accounting explanations, order selection, and sampled future-data checks |
| `research_ui.py` | Failure report, clickable trade evidence, and audit interface |
| `strategies/__init__.py` | Common validation and strategy registry |
| `strategies/moving_average.py` | SMA crossover strategy |
| `strategies/rsi.py` | Wilder RSI calculation and threshold strategy |
| `strategies/momentum.py` | Percentage momentum and threshold strategy |
| `requirements.txt` | Tested runtime dependency versions |
| `requirements-dev.txt` | Runtime dependencies plus pytest |
| `.streamlit/config.toml` | Dashboard theme and telemetry preference |
| `pytest.ini` | Test discovery and import-path configuration |
| `tests/test_core.py` | Financial accounting, data validation, and strategy tests |
| `tests/test_app.py` | Streamlit interaction tests for all three strategies |
| `tests/test_market_search.py` | Search identity, supported asset filtering, empty/malformed responses, provider failures |
| `tests/test_research.py` | Slippage/delay accounting, scenario isolation, evidence, and future-data audit |
| `tests/test_research_ui.py` | Scenario/trade click callbacks and research dashboard flows |

### Workflow

1. Search a company, explicitly select the correct ticker/exchange, set your inputs and click **Run backtest**. Alternatively enter a ticker directly. Searching alone does not download price history.
2. Validate dates/ticker and obtain daily adjusted OHLCV bars. The selected end date is inclusive; the loader adds a day for yfinance's exclusive upper bound.
3. Normalize prices and discard invalid bars without forward-filling or backfilling prices.
4. Calculate indicators using only the current and previous observations. Indicator warm-up rows generate no intent.
5. Return a DataFrame with unshifted `Signal`: `1` = buy intent, `-1` = sell intent, `0` = wait.
6. The engine shifts signals **exactly once**. A signal on day t executes at the open of the next available valid bar.
7. Execute an eligible order, charge costs, and value holdings at that day's close.
8. Calculate net metrics and compare with buy-and-hold across the same observed dates.
9. Display the report and allow CSV/parameter downloads.
10. On demand, rerun independent stress scenarios against the same downloaded snapshot; select a scenario and click its orders to inspect the evidence.

Changing controls does not silently rerun an old report: a warning identifies stale results until the next run. Downloads and headings refer to the saved run.

## Installation

Use **standard 64-bit Python 3.11, 3.12, or 3.13**; the project tests were run on Python 3.12. The pinned Pandas 2.2.3 release supports Python 3.13. Do not use Python 3.14 with these dependency pins. Extract the archive, open a terminal, and enter the project directory. No API key is needed for yfinance. Real market downloads require internet access to Yahoo Finance.

### Windows PowerShell

```powershell
cd algorithmic-trading-backtester
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The Windows example selects Python 3.13 explicitly. Run `py -0p` to see installed versions; use `py -3.12` or `py -3.11` instead if needed. These commands invoke the virtual environment directly, so PowerShell activation permissions are not required. Install dependencies successfully before starting Streamlit. If pip attempts to compile NumPy or Pandas, check the Python version and try `--only-binary="numpy,pandas"` on the install command.

### macOS / Linux

```bash
cd algorithmic-trading-backtester
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

On macOS/Linux, use an installed Python 3.11–3.13 interpreter in place of `python3.12` if necessary. Open **http://localhost:8501**. Press `Ctrl+C` in the terminal to stop the server. If port 8501 is busy, append `--server.port 8502` to the Streamlit command.

## Quick demonstration

1. Open the dashboard; Yahoo Finance is used automatically.
2. Under **Search companies**, enter `Apple`, `Reliance`, or `TCS` and click **Search stocks** (or press Enter inside the search field).
3. Choose the correct company and exchange under **Matching listings**. The app does not select the first result automatically: similarly named listings may trade on different exchanges.
4. Keep three years of data, capital `100000`, cost `0.1`, and SMA windows `20`/`50`, then click **Run backtest**.
5. Hover over candles and fill markers; inspect equity/drawdown panels. Open **Trade ledger** and compare a signal date with its following execution date.
6. Switch to RSI or momentum, rerun, and compare performance. **Export report** includes the saved listing and the data retrieval timestamp.

Already know the ticker? Choose **Enter ticker** and type `AAPL`, `MSFT`, `SPY`, `RELIANCE.NS`, `TCS.NS`, `^GSPC`, or `^NSEI`. There is no fixed preset-stock list. `.NS` identifies NSE listings and `.BO` identifies BSE listings in Yahoo's symbol format.

Dashboard runs require an internet connection to Yahoo Finance. The deterministic synthetic-price generator remains available to automated tests only; there is no demo selector in the app.

### How the market API integration works

- `yf.Search(query).quotes` looks up current company/ticker listings. The loader retains equities, ETFs and indices, removes duplicate symbols, and keeps company names and exchange labels.
- Search runs only when submitted, with a 15-second request timeout. Results are cached for 15 minutes. Starting a new search clears the previous selection, including on errors or zero matches.
- `yf.download(...)` fetches daily adjusted historical OHLCV for the selected symbol and inclusive date range. Downloaded bars are cached for one hour, so changing a strategy or capital reuses the same data snapshot.
- Names/exchanges are display metadata only; indicators still use only the historical price bars. Current search results are not a point-in-time historical universe and cannot eliminate survivorship bias.
- The report shows its last available bar **within the requested range**, not a streaming/live quote. The UTC retrieval time belongs to the cached download; it is not refreshed merely by changing strategy settings.
- `data_metadata.json` in the exported report records source, symbol, first/last bar, bar count, removed rows, retrieval time and whether data is synthetic. This is provenance, not a stored raw market-data snapshot.
- No API key is needed. `yfinance` is an unofficial Yahoo integration, intended for research/personal use. Follow Yahoo's terms. Public/commercial deployments may require a licensed provider and appropriate display rights.
- Coverage is limited to listings available from Yahoo. Private companies do not have exchange-traded price histories; some delisted or international symbols may be unavailable. A search match does not guarantee history exists for the selected dates.

If search fails, try again later or choose **Enter ticker**. If history fails, verify the symbol and dates, check your connection and wait before retrying rate-limited requests. Direct entry bypasses the search endpoint, but still needs Yahoo's historical-data service. Neither path substitutes fake prices.

The capital and P&L are denominated in the symbol's quote units. The program does not infer or convert currencies. Most US shares are quoted in USD and NSE shares in INR, but other symbols can use different units. Indices are modeled as synthetic research assets and cannot generally be bought directly; use an appropriate tradable ETF for a more practical approximation.

## Strategy failure report with clickable evidence

### Try it in the dashboard

1. Run a normal backtest and open **Failure report**.
2. Expand **Stress-test ranges** if you want to change the limits, then click **Break my strategy**.
3. Inspect the smallest tested failing changes and the full scenario table. Click a row, or use **Scenario to inspect**.
4. Compare its equity curve with the original strategy and original buy-and-hold reference.
5. Click a BUY/SELL marker in the scenario's price chart. The order picker updates to that exact ledger order, showing its original signal date and later fill date.
6. Inspect the numerical rule checks, information available at the signal close, and pre-/post-fill cash, units, fees, slippage, and cost basis. Historical outcomes appear separately because they were not known at the decision time.
7. Download one order's evidence JSON, or the complete failure-report ZIP. Open **Trade evidence** to inspect the original baseline and run **Audit future-data use**.

The explanations are computed from the actual recorded values and strategy rules; no language-model API or extra market-data API is required. Diagnostics always refer to the saved baseline. Pending setup edits and changed stress ranges produce warnings rather than silently changing the displayed analysis. Running a new baseline discards its previous failure report.

### What gets tested

Each scenario changes exactly one setting. It recalculates indicators, trades, and metrics independently from the same OHLCV snapshot. It never reuses indicators calculated with another parameter or starting date.

| Category | Default experiments | Interpretation |
|---|---|---|
| Transaction costs | Five increases from +0.1 to +0.5 percentage points per side | If the baseline fee is 0.1%, the tested rates are 0.2% through 0.6% |
| Adverse slippage | Five levels from 0.05% to 0.25% per fill | Buys execute above the open and sells below it |
| Execution delay | 1, 2, and 3 extra available sessions | Signal-to-fill gaps become 2, 3, and 4 bars; baseline is 1 |
| Nearby parameters | Each period about ±10%, at least 1 bar; RSI thresholds ±5 points; momentum thresholds ±1 percentage point | Each individual parameter moves while the others stay fixed |
| Later start date | Start 1, 5, and 10 available sessions later | Restart in cash and warm up again over a shorter evaluation period |

The four configurable limits control the fee/slippage grids, maximum extra delay, and maximum start offset. Later-start offsets are 1, half the selected maximum rounded down, and the maximum, with duplicates removed. Invalid neighboring parameters (for example short MA greater than long MA) and insufficient history are explicitly **Skipped**, with reasons. No-order scenarios are **No trades**; an entry that remains open is still an executed order and has a marked portfolio return.

### What “failure” means

For this report, failure means **negative total portfolio return after modeled costs**, including unrealized P&L on remaining holdings. A 1e-9 percentage-point tolerance treats numerical rounding around zero as breakeven. Failure does not mean merely underperforming buy-and-hold.

When the baseline is profitable, the report identifies the smallest **tested** change that produces a loss in each category. Period/threshold parameters each have their own category. Equal-size upward/downward changes can differ; the scenario table shows both. A finite grid does not locate an exact break-even boundary or prove robustness. If the baseline is already losing, breakeven, or has no trades, the report says there is no positive baseline return to break. Skipped and no-trade scenarios do not count as successful robustness tests. Scenario counts are not probabilities.

### Slippage and delayed execution

For slippage rate `s`, buy price is `Open × (1 + s)` and sell price is `Open × (1 − s)`. Quantity and fees use this actual modeled fill price. The reported slippage amount is `abs(fill − open) × quantity`; it is already embedded in the price and is never deducted a second time. Holdings are still valued at the original adjusted close. This is a sensitivity assumption, not a calibrated spread/liquidity model; large assumptions can produce a fill outside the daily candle.

A delay is a fixed shift of the original signal, measured in retained valid bars. Later signals do not cancel an earlier pending intent. The engine checks position eligibility at execution, ignores duplicate buys/sells, and cannot fill intentions scheduled beyond the final bar. No scenario fills before its signal becomes available.

Each scenario's internal benchmark buys at its first open with that scenario's fee and slippage, without a signal delay. The comparison chart explicitly uses the **original baseline buy-and-hold** as a common reference. Start-date scenarios cover different periods and rebuild their warm-up, so their return differences are not a like-for-like causal effect of one market day.

The reusable engine remains backward compatible:

```python
from backtester import run_backtest

# signals is an OHLCV DataFrame with unshifted -1/0/1 Signal values.
result = run_backtest(signals, initial_capital=100000, transaction_cost_pct=0.1,
                      slippage_pct=0.2, execution_delay=2)
```

### Evidence and audit

Each order has a run-local **Order ID**. Plotly marker `customdata` carries that ID; trace-local point numbers are never used to identify an order. Evidence shows the previous/current MA relationship or the exact RSI/momentum threshold comparison, the originating signal date, and the fill accounting. Decision-time context stops at the signal close. Outcome information is clearly retrospective.

The optional future-data audit checks up to six historical cutoffs. It recomputes indicators on truncated history, deliberately changes only later OHLC prices, and compares portfolio prefixes. Differences identify the cutoff and first affected field/date. Passing sampled checks is evidence of consistency, not proof against every form of look-ahead bias. It cannot certify provider data vintages, a survivorship-free universe, or performance on unseen data.

The complete diagnostic download contains:

- `scenarios.csv` and `findings.csv`, including skipped/no-trade outcomes.
- `adjusted_prices.csv`, the exact cleaned snapshot used for the experiments.
- `manifest.json`, with parameters, limits, scenario definitions, source/retrieval metadata, and a SHA-256 fingerprint of the baseline configuration and price frame.
- One folder per evaluated scenario containing orders, completed trades, equity, and indicators.
- `READ_ME.txt`, with execution and interpretation assumptions.

Order IDs are meaningful within their scenario, not across different scenarios. Audit CSV and individual evidence JSON have separate download buttons. The fingerprint identifies an in-memory configuration/data snapshot; it is not a provider signature or a cross-version storage-format guarantee.

## Trading strategies

### 1. Moving Average Crossover

`SMA(n)` is the mean of the last n closing prices. Buy when the short SMA moves strictly above the long SMA after being at or below it. Sell when it moves strictly below after being at or above it. The short period must be smaller than the long period.

The first valid pair of averages establishes a relationship; it is not automatically a crossover. Both the current and previous averages must be available. At least `long_window + 2` bars are required to allow comparison and a possible next-open fill. An already-rising market may produce no entry until a new crossover occurs.

### 2. RSI Strategy

Relative Strength Index compares smoothed gains with smoothed losses:

`RS = average gain / average loss`  
`RSI = 100 − 100 / (1 + RS)`

The default period is 14. The first average uses the first 14 close-to-close changes. Later values use Wilder smoothing: `(previous average × (period − 1) + current change) / period`. A zero-loss rising series has RSI 100; a zero-gain falling series has RSI 0; a completely flat series is assigned neutral RSI 50.

Buy when RSI is strictly below the lower threshold (default 30); sell when strictly above the upper threshold (default 70). At equality, wait. Thresholds and period are configurable. This is a threshold-state rule: it emits a buy intent on each oversold day, but the engine ignores duplicate buys while holding a position. No crossing from a previously valid RSI is required for the first eligible intent.

### 3. Momentum Strategy

`Momentum (%) = (Close[t] / Close[t − lookback] − 1) × 100`

Buy when momentum exceeds the entry threshold; sell when it falls below the exit threshold. Defaults: 20-bar lookback, entry above 5%, exit below 0%. The exit threshold must be below entry to avoid conflicting rules. Between the two thresholds, retain the current cash/position state. All thresholds use percentage points: `5` means 5%, not 500%.

## Backtesting and accounting assumptions

- By default, signals use the close and trades fill at the following available open. Stress tests can add delay. No trade occurs on the first bar and the final bar's intent cannot fill within the test.
- All capital is used for each buy, with fractional units and no leverage, shorting, or repeated accumulation.
- Let cash be C, execution price P, and cost rate f. Buy quantity is `C / (P × (1 + f))`. This reserves enough cash for the entry fee.
- Every buy/sell fee is `quantity × execution price × f`.
- Entry cost basis is buy notional plus entry fee. Net exit proceeds are sell notional minus exit fee.
- Realized P&L is net exit proceeds minus entry cost basis. Unrealized P&L is current market value minus entry cost basis.
- Daily equity is `cash + quantity × close`.
- The accounting identity is `equity − initial capital = cumulative realized P&L + current unrealized P&L`.
- Open positions are not forcibly liquidated at the end. Their unrealized P&L includes entry costs but no hypothetical exit cost. Closed-trade statistics exclude them.
- Cash earns no interest. The risk-free-rate input affects only the Sharpe calculation; it does not change portfolio cash.
- Indicators warm up inside the requested range; no pre-start price history is fetched. The strategy stays in cash during warm-up.
- Buy-and-hold invests at the first valid bar's open with the same entry fee, then marks to the last close. It also remains open without a final sale. It is invested during the strategy's warm-up, which is deliberately included in the comparison.
- Adjusted OHLC handles corporate-action adjustments as a simplified adjusted-price model. Quantity represents adjusted units, not a literal historical share count. Dividends are not separately credited, avoiding double counting, but this is not a detailed dividend/tax/share-action simulator.
- The software's indicators and execution logic use no future bars. Downloaded adjusted historical data can still be revised by the provider and is not a point-in-time institutional dataset.

### Example: transaction costs

With capital 1,000, price 100, and a 1% fee, the engine buys `1000 / 101 = 9.90099` units. The purchase notional is about 990.10 and the entry fee about 9.90. Selling at 110 produces about 1,089.11 before fees and 1,078.22 after the exit fee. Net profit is about 78.22, not 100.

## Metrics explained

| Metric | Definition |
|---|---|
| Initial capital | Cash allocated at the beginning |
| Final portfolio value | Final cash plus closing market value of holdings |
| Total return | `(final equity / initial capital − 1) × 100` |
| Buy-and-hold return | Same formula applied to the fee-adjusted benchmark |
| Completed trades | Closed buy/sell round trips; two orders make one completed trade |
| Winning / losing trades | Completed trades with positive / negative net P&L after both fees |
| Breakeven trades | P&L within an absolute 1e-8 quote-unit numerical tolerance of zero |
| Win rate | `winning completed trades / all completed trades × 100`; breakevens stay in the denominator |
| Average P&L per trade | Mean net P&L of completed trades, in quote units |
| Maximum drawdown | Largest percentage decline from the running equity peak, displayed as a positive loss magnitude |
| Annualized volatility | Sample standard deviation of daily equity returns × √252 × 100 |
| Sharpe ratio | Mean daily excess return / sample daily return standard deviation × √252 |
| Profit factor | Sum of winning net P&L / absolute sum of losing net P&L |
| Total modeled slippage | Sum of absolute fill-to-open differences × units, already reflected in P&L |

Daily return is `equity[t] / equity[t−1] − 1`. The first return uses initial capital as the denominator. The equity peak includes initial capital, so an early loss is not hidden. The drawdown chart shows negative percentages; its KPI reports the worst loss as a positive magnitude.

Sharpe measures excess return per unit of variability. Annual risk-free input R is converted to a daily rate with `(1 + R/100)^(1/252) − 1`. This uses arithmetic mean daily excess returns, not CAGR. Volatility and Sharpe use a 252-session stock-market convention, which is unsuitable for 24/7 crypto without modification. Dropped/missing sessions can also distort annualization.

With no completed trades, win rate, average trade P&L, and profit factor are **N/A**. With winners and no losses, profit factor is **∞**. With only losing trades, it is zero. Sharpe is N/A when volatility is effectively zero or fewer than two returns exist. One-day samples have undefined sample volatility. A high win rate alone does not imply profitability: occasional large losses can dominate many small wins.

## Data quality and error handling

- The UI excludes today and future dates to avoid incomplete daily bars; this is conservative across exchanges.
- Empty provider responses can mean an invalid/delisted ticker, non-trading dates, an outage, or a rate limit. The app reports these possibilities instead of incorrectly identifying every empty response as an invalid symbol.
- Required OHLC prices must be finite, positive, and internally consistent. Invalid bars are removed, duplicate dates are deduplicated, and dates are sorted. A warning reports removed rows.
- No price is backfilled or interpolated. If an invalid bar is removed, a pending order executes at the next retained valid bar; this simplification can distort results around gaps.
- Missing volume is allowed because these strategies do not use it. Entire missing sessions absent from the provider response are not reconstructed from an exchange calendar.
- Insufficient history and invalid periods/thresholds produce actionable errors.
- A valid run with no orders shows a flat strategy equity curve and still calculates the benchmark.
- Downloads are cached for one hour; searches are cached for 15 minutes. **Clear market-data cache** clears both; submit a new search or run to refresh. Clearing a cache does not bypass a provider's rate limit.
- Synthetic test fixtures are seeded simulations on business weekdays, not an exchange-holiday calendar or stored market dataset. They are not used by the dashboard.

## Tests

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests require no external data. They verify next-open timing, transaction costs, accounting identities, closed/open positions, benchmark fees, risk formulas, RSI seeding, MA crossovers, momentum units, invalid data/parameters, and all three dashboard modes. Search tests cover explicit exchange selection, no initial network calls, cache reuse, empty/failed searches clearing selection, direct entry, and no synthetic fallback. Research tests cover adverse fills without double-charging, delayed original signal dates, independent scenarios, invalid/no-trade cases, evidence exports, and stale report handling. Native table/chart selection callbacks are tested with serialized frontend event payloads. Prefix checks pass for the supplied strategies and detect a deliberately future-dependent indicator. Network-dependent availability must be checked separately; mocked integration tests do not prove Yahoo is currently reachable.

## Screenshots

Create the following captures from your locally running app for your GitHub README or placement presentation:

| Capture | What to show |
|---|---|
| Performance dashboard | Top-panel configuration, KPI cards, price chart, and BUY/SELL markers |
| Portfolio comparison | Equity curve, strategy versus buy-and-hold returns, and drawdown |
| Trade ledger | Signal/execution dates, prices, fees, completed trades, and current holdings |
| RSI analysis | Price chart and RSI oscillator with configurable threshold lines |
| Real-stock search | Company query, multiple exchange results, and the selected listing |
| Failure report | Smallest tested failures, scenario table, and selected equity comparison |
| Clickable evidence | Selected BUY/SELL marker, rule checks, and reconciled accounting |

Run a historical download, open the appropriate tab, and use your browser or operating system screenshot tool. Keep the ticker, data-source and date labels visible. Screenshot images are not bundled. The desktop and mobile top-panel layout can be captured directly from your running app; the existing Streamlit interaction checks cover all three strategies and the research tools.

## Extending the project

Add a module under `strategies/` that accepts a validated OHLCV DataFrame and returns a copy with indicator columns and an **unshifted** `Signal` column containing -1, 0, or 1. Register the function in `STRATEGIES` and add its parameter controls and indicator chart in `app.py`/`ui.py`. The engine needs no strategy-specific changes. Do not shift inside the new strategy: the engine already handles execution timing. To support diagnostics for a new strategy, also define its parameter neighborhoods in `failure_analysis.py` and its rule explanation/minimum audit history in `trade_evidence.py`.

## Interview discussion points

- Explain why same-close fills using close-derived signals introduce look-ahead bias.
- Walk through cash, quantity, fees, cost basis, and P&L for one round trip.
- Explain the difference between an order, a completed trade, and an open position.
- Show the causality tests and explain why future data must not change previous decisions.
- Discuss benchmark warm-up differences, overfitting, drawdown, and model limitations.
- Change a tested assumption, click an affected trade, and trace its signal, delayed fill, and fee-adjusted cash flow. Explain why a finite stress grid cannot prove robustness.

Suggested resume bullet after you run and understand the project:

> Built a modular Python/Streamlit backtester with three strategies, an automated strategy-failure report, clickable trade evidence, and tests for execution accounting, scenario isolation, and future-data dependence.

Avoid claiming profitable strategies or production trading readiness from in-sample results.

## Future improvements

- Walk-forward evaluation, out-of-sample testing, combined stress scenarios, and broader parameter surfaces.
- Pre-start indicator warm-up with an explicitly controlled evaluation window.
- Calibrated bid/ask spread and market-impact models, partial fills, lot sizes, and liquidity constraints.
- Risk-based sizing, stops, take-profit rules, and position limits.
- Point-in-time data, exchange calendars, corporate-action ledgers, and survivorship-bias controls.
- Multi-asset portfolios, rebalancing, exposure limits, and currency conversion.
- CAGR, Sortino/Calmar ratios, rolling risk metrics, and benchmark excess-return analysis.
- Persistent snapshot storage, provider data-version tracking, and one-click replay of exported scenarios.
- A provider interface for licensed historical APIs such as Twelve Data or Alpha Vantage, with server-side key management.
- Broker paper-trading integration only after a separate execution/risk-control design.

## Design references and assets

The visual direction draws on the chart emphasis of [Robinhood Legend](https://robinhood.com/us/en/legend/), the financial-summary hierarchy of [Stripe's dashboard](https://support.stripe.com/questions/dashboard-home-page-charts-for-business-insights), and clean investment-product layouts. This project is independent and is not affiliated with those companies. No company logos or proprietary graphics are included.

The Inter font is bundled under the SIL Open Font License; see `assets/INTER-LICENSE.txt`. Native system fonts remain the fallback if that font file is unavailable.

## Documentation references

- [yfinance search API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Search.html): company-name/ticker search and listing results.
- [yfinance download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html): adjusted OHLC, date bounds, and column format.
- [Streamlit Plotly charts](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart): interactive chart integration.
- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest): widget and app-flow testing.

## Disclaimer

This project is for educational and historical-backtesting purposes only. It is not financial advice, investment research, or a recommendation to trade any security. Historical and synthetic results do not guarantee future performance. Real trading has risks and costs not fully represented here. Follow the market-data provider's terms for data access and use.
