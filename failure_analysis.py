"""Bounded, one-change-at-a-time experiments on one saved market-data snapshot."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
from numbers import Integral
import zipfile

import numpy as np
import pandas as pd

from backtester import BacktestResult, run_backtest
from metrics import calculate_metrics
from strategies import STRATEGIES

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
RETURN_TOLERANCE = 1e-9  # Percentage points; only numerical dust is treated as zero.
DEFAULT_LIMITS = dict(extra_cost=0.5, slippage=0.25, extra_delay=3, start_shift=10)


@dataclass
class Scenario:
    id: str
    family: str
    change: str
    magnitude: float
    params: dict
    cost: float
    slippage: float = 0.0
    delay: int = 1
    start_offset: int = 0


@dataclass
class ScenarioRun:
    scenario: Scenario
    signals: pd.DataFrame | None = None
    result: BacktestResult | None = None
    stats: dict | None = None
    error: str = ""


@dataclass
class FailureReport:
    fingerprint: str
    config: dict
    limits: dict
    runs: dict
    table: pd.DataFrame
    findings: pd.DataFrame


def market_snapshot(data):
    """Strip previously calculated indicators before every independent rerun."""
    return data.loc[:, [c for c in PRICE_COLUMNS if c in data]].copy()


def snapshot_id(data, config):
    raw = market_snapshot(data)
    digest = sha256(json.dumps(config, sort_keys=True, default=str).encode())
    digest.update("|".join(raw.columns).encode())
    digest.update(pd.util.hash_pandas_object(raw, index=True).to_numpy().tobytes())
    return digest.hexdigest()


def build_scenarios(config, limits=None):
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    for key in ("extra_cost", "slippage"):
        if not np.isfinite(limits[key]) or not 0 < limits[key] <= 20:
            raise ValueError(f"{key} must be above zero and at most 20 percentage points.")
    for key in ("extra_delay", "start_shift"):
        if isinstance(limits[key], bool) or not isinstance(limits[key], Integral) or not 1 <= limits[key] <= 20:
            raise ValueError(f"{key} must be an integer between 1 and 20 sessions.")
    if config["strategy"] not in STRATEGIES:
        raise ValueError("Choose a registered strategy.")
    cases = []

    def add(family, change, magnitude, **overrides):
        values = dict(params=deepcopy(config["params"]), cost=float(config["cost"]))
        values.update(overrides)
        cases.append(Scenario("baseline" if not cases else f"case_{len(cases):02d}",
                              family, change, float(magnitude), **values))

    add("Baseline", "Saved strategy and execution settings", 0)
    for extra in np.linspace(limits["extra_cost"] / 5, limits["extra_cost"], 5):
        cost = round(config["cost"] + float(extra), 10)
        add("Transaction costs", f"{cost:g}% per side (+{extra:g} pp)", extra, cost=cost)
    for slip in np.linspace(limits["slippage"] / 5, limits["slippage"], 5):
        slip = round(float(slip), 10)
        add("Slippage", f"{slip:g}% adverse slippage per fill", slip, slippage=slip)
    for extra in range(1, limits["extra_delay"] + 1):
        add("Execution delay", f"{extra} extra session(s); fill {extra + 1} bars after signal",
            extra, delay=extra + 1)
    for name, value in config["params"].items():
        # Periods move about 10%; RSI thresholds move 5 points, momentum 1 pp.
        period = name in {"short_window", "long_window", "period", "lookback"}
        step = max(1, round(value * 0.1)) if period else 5.0 if name in {"lower", "upper"} else 1.0
        for direction in (-1, 1):
            params = deepcopy(config["params"])
            params[name] = value + direction * step
            add(f"Parameter: {name}", f"{name}: {value:g} → {params[name]:g}", step, params=params)
    for offset in sorted({1, max(1, limits["start_shift"] // 2), limits["start_shift"]}):
        add("Start date", f"Start {offset} available session(s) later", offset, start_offset=offset)
    return cases, limits


def evaluate_scenario(data, config, scenario):
    raw = market_snapshot(data).iloc[scenario.start_offset:].copy()
    # Restart in cash and warm up again after a start-date change. Never retain old signals.
    try:
        signals = STRATEGIES[config["strategy"]](raw, **scenario.params)
        result = run_backtest(signals, config["capital"], scenario.cost,
                              slippage_pct=scenario.slippage, execution_delay=scenario.delay)
        stats = calculate_metrics(result, config["risk_free"])
        return ScenarioRun(scenario, signals, result, stats)
    except ValueError as exc:
        return ScenarioRun(scenario, error=str(exc))


def scenario_table(runs):
    baseline = runs["baseline"].stats["Total return %"]
    rows = []
    for id_, run in runs.items():
        s = run.scenario
        row = {"Scenario": id_, "Category": s.family, "Change": s.change,
               "Magnitude": s.magnitude, "Cost %": s.cost, "Slippage %": s.slippage,
               "Fill delay bars": s.delay, "Start offset bars": s.start_offset}
        if run.error:
            row.update(Status="Skipped", Outcome="Not evaluated", Reason=run.error)
        else:
            stats = run.stats
            value = float(stats["Total return %"])
            outcome = ("No trades" if run.result.orders.empty else "Loss" if value < -RETURN_TOLERANCE
                       else "Profit" if value > RETURN_TOLERANCE else "Breakeven")
            row.update({"Status": "Completed", "Outcome": outcome, "Reason": "",
                        "Return %": value, "Change vs baseline (pp)": value - baseline,
                        "Max drawdown %": stats["Maximum drawdown %"], "Sharpe": stats["Sharpe ratio"],
                        "Closed trades": stats["Completed trades"], "Orders": len(run.result.orders),
                        "Final value": stats["Final portfolio value"],
                        "First bar": run.signals.index[0], "Last bar": run.signals.index[-1]})
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_findings(table):
    baseline = table.iloc[0]
    can_break = baseline["Outcome"] == "Profit"
    findings = []
    for family, rows in table.iloc[1:].groupby("Category", sort=False):
        valid = rows[rows.Status == "Completed"]
        losses = valid[valid.Outcome == "Loss"].sort_values("Magnitude", kind="stable")
        if not can_break:
            verdict = f"Baseline is {baseline['Outcome'].lower()}; no positive-return failure threshold"
        elif valid.empty:
            verdict = "No valid scenarios in this category"
        elif len(losses):
            verdict = "Smallest tested failing change found"
        else:
            verdict = "No negative return found in this tested grid"
        chosen = losses.iloc[0] if can_break and len(losses) else None
        findings.append({"Category": family, "Finding": verdict,
                         "Scenario": chosen["Scenario"] if chosen is not None else "",
                         "Change": chosen["Change"] if chosen is not None else "—",
                         "Return %": chosen["Return %"] if chosen is not None else np.nan,
                         "Completed": len(valid), "Skipped": len(rows) - len(valid),
                         "No-trade scenarios": int((valid.Outcome == "No trades").sum())})
    return pd.DataFrame(findings)


def run_failure_analysis(data, config, limits=None, progress=None):
    cases, limits = build_scenarios(config, limits)
    runs = {}
    for i, case in enumerate(cases):
        runs[case.id] = evaluate_scenario(data, config, case)
        if case.id == "baseline" and runs[case.id].error:
            raise ValueError(runs[case.id].error)
        if progress:
            progress((i + 1) / len(cases))
    table = scenario_table(runs)
    return FailureReport(snapshot_id(data, config), deepcopy(config), dict(limits), runs,
                         table, summarize_findings(table))


def export_failure_report(report):
    """Include the price snapshot and every evaluated path, so claims are inspectable."""
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scenarios.csv", report.table.to_csv(index=False))
        archive.writestr("findings.csv", report.findings.to_csv(index=False))
        archive.writestr("adjusted_prices.csv", market_snapshot(report.runs["baseline"].signals).to_csv())
        archive.writestr("manifest.json", json.dumps({
            "analysis_version": "1.0", "snapshot_sha256": report.fingerprint,
            "configuration": report.config, "limits": report.limits,
            "failure_definition": "Total portfolio return < -1e-9 percentage points",
            "scenarios": [dict(**asdict(r.scenario), error=r.error) for r in report.runs.values()],
            "data_source": report.runs["baseline"].signals.attrs.get("source", "Yahoo Finance"),
            "fetched_at_utc": report.runs["baseline"].signals.attrs.get("fetched_at_utc"),
        }, indent=2, allow_nan=False))
        for id_, run in report.runs.items():
            if run.result is not None:
                archive.writestr(f"{id_}/orders.csv", run.result.orders.to_csv(index=False))
                archive.writestr(f"{id_}/closed_trades.csv", run.result.trades.to_csv(index=False))
                archive.writestr(f"{id_}/equity.csv", run.result.equity.to_csv())
                archive.writestr(f"{id_}/indicators.csv", run.signals.to_csv())
        archive.writestr("READ_ME.txt", (
            "Historical sensitivity analysis, not a forecast or probability of success.\n"
            "Each scenario changes one setting from baseline; combined shocks are not tested.\n"
            "Failure thresholds are the smallest tested changes per category, not exact boundaries.\n"
            "No-trade cases and invalid/skipped scenarios are listed separately.\n"
            "Start-date changes restart in cash and re-warm indicators over a shorter period.\n"
            "Slippage changes fills (buy above open, sell below open), not OHLC/indicator prices.\n"
            "Delay is a fixed shift of intent; intervening signals do not cancel an older intent.\n"
            "Benchmark invests at the first available open with that run's fees/slippage, without delay.\n"
            "Orders contain accounting evidence; indicators.csv contains signal-time indicator values.\n"
            "Adjusted Yahoo history can be revised; this snapshot is not point-in-time certification.\n"))
    return out.getvalue()
