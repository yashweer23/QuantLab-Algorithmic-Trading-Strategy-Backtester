"""Failure analysis and clickable, deterministic order explanations for Streamlit."""
from hashlib import sha256
from html import escape
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from failure_analysis import (DEFAULT_LIMITS, export_failure_report, run_failure_analysis,
                              snapshot_id)
from trade_evidence import (audit_future_data, evidence_for_order, evidence_json,
                            selected_order_id)
from ui import (CHART_CONFIG, GREEN, PURPLE, RED, fmt, html, plot, price_chart,
                section_title, style_figure)


def choose_order_from_chart(chart_key, choice_key, ids):
    chosen = selected_order_id(st.session_state.get(chart_key), ids)
    if chosen is not None:
        st.session_state[choice_key] = int(chosen)


def choose_scenario_from_table(table_key, choice_key, ids):
    rows = st.session_state.get(table_key, {}).get("selection", {}).get("rows", [])
    if rows and 0 <= rows[0] < len(ids):
        st.session_state[choice_key] = ids[rows[0]]


def comparison_chart(baseline, selected):
    fig = go.Figure()
    for values, name, color, dash in [
        (baseline.equity.Equity, "Baseline strategy", GREEN, "solid"),
        (selected.equity.Equity, "Selected scenario", RED, "solid"),
        (baseline.equity["Buy & Hold"], "Baseline buy & hold", PURPLE, "dot"),
    ]:
        fig.add_trace(go.Scatter(x=values.index, y=values, name=name, line=dict(color=color, width=2, dash=dash)))
    style_figure(fig, 300)
    fig.update_layout(margin=dict(t=40), legend=dict(y=1.16))
    return fig


def evidence_view(signals, result, strategy, params, scope):
    if result.orders.empty:
        st.info("This run has no executed orders to inspect. Signals during warm-up or beyond the last possible fill do not create trades.")
        return
    section_title("Click a trade. Follow the evidence.", "Select a BUY/SELL marker or use the order picker. Values below belong to this run.")
    ids = [int(x) for x in result.orders["Order ID"]]
    chart_key, choice_key = f"{scope}_chart", f"{scope}_order"
    fig = price_chart(signals, result.orders, params, "Closing price")
    fig.update_layout(clickmode="event+select", hovermode="closest")
    st.plotly_chart(fig, width="stretch", theme=None, key=chart_key, config=CHART_CONFIG,
                    on_select=lambda: choose_order_from_chart(chart_key, choice_key, ids), selection_mode="points")
    lookup = result.orders.set_index("Order ID")
    chosen = st.selectbox("Order to inspect", ids, key=choice_key,
        format_func=lambda id_: f"#{id_} · {lookup.loc[id_, 'Side']} · {lookup.loc[id_, 'Date']:%d %b %Y} · fill {lookup.loc[id_, 'Price']:,.2f}")
    evidence = evidence_for_order(signals, result, strategy, params, chosen)
    order = evidence["order"]
    html(f'<div class="evidence-banner"><span>ORDER #{chosen} · {escape(order["Side"])}</span>'
         f'<strong>{escape(evidence["explanation"])}</strong>'
         f'<small>Decision at close: {order["Signal Date"]:%d %b %Y} · Filled at open: {order["Date"]:%d %b %Y} '
         f'· {evidence["fill_delay_bars"]} available bar(s) later</small></div>')
    st.write("")
    left, right = st.columns(2, gap="medium")
    with left:
        section_title("1. Information available at the signal close")
        st.caption(f"Adjusted close: {evidence['signal_close']:,.4f} · Parameters: {json.dumps(params)}")
        st.dataframe(pd.DataFrame(evidence["checks"]), hide_index=True, width="stretch", key=f"{scope}_checks")
        check_ok = all(c["Satisfied"] for c in evidence["checks"]) and evidence["signal_matches_side"] and evidence["position_eligible"]
        if check_ok:
            st.success("Rule conditions match the signal; the position was eligible when it filled.")
        else:
            st.error("The recorded order does not match all rule/position checks. Inspect the evidence before relying on this run.")
        with st.expander("Decision-time bars and indicators"):
            st.dataframe(evidence["decision_context"], width="stretch", key=f"{scope}_context")
            st.caption("Only bars through the signal close appear here. Adjusted history is the downloaded snapshot and may have been revised by Yahoo.")
    with right:
        section_title("2. Execution and portfolio accounting")
        fields = ["Market Open", "Price", "Quantity", "Notional", "Fee", "Slippage Cost",
                  "Cash Before", "Cash After", "Holdings Before", "Holdings After",
                  "Cost Basis Before", "Cost Basis After", "Realized P&L"]
        st.dataframe(pd.DataFrame({"Field": fields, "Value": [order[x] for x in fields]}),
                      hide_index=True, width="stretch", key=f"{scope}_accounting",
                      column_config={"Value": st.column_config.NumberColumn(format="%.6f")})
        st.caption(f"Fee: {evidence['cost_pct']:g}% per side · Adverse slippage: {evidence['slippage_pct']:g}%. Slippage is embedded in the fill price, not charged twice.")
        if evidence["accounting_matches"]:
            st.caption("Cash and quantity reconcile to the recorded order.")
        else:
            st.error("Cash or holdings failed the reconciliation check.")
    with st.expander("3. Outcome — known after the decision"):
        trades = result.trades
        match = trades[trades["Entry Date" if order["Side"] == "BUY" else "Exit Date"] == order["Date"]]
        if not match.empty:
            st.dataframe(match, hide_index=True, width="stretch", key=f"{scope}_outcome")
        else:
            st.write(f"This position remains open at the last bar. Unrealized P&L: {fmt(result.equity['Unrealized P&L'].iloc[-1])}.")
        st.caption("Outcome information explains the historical result; it was not available when the entry signal was generated.")
    st.download_button("Download this order's evidence", evidence_json(evidence), f"order_{chosen}_evidence.json",
                        "application/json", key=f"{scope}_download")


def audit_view(saved, signals, result, scope):
    section_title("Check for future-data dependence", "Recalculate sampled historical prefixes and deliberately change later prices.")
    key = f"{scope}_audit_result"
    if st.button("Audit future-data use", key=f"{scope}_audit_button", icon=":material/fact_check:"):
        with st.spinner("Checking indicator and portfolio prefixes…"):
            st.session_state[key] = audit_future_data(
                signals, saved["strategy"], saved["params"], initial_capital=result.initial_capital,
                cost=result.transaction_cost_pct, slippage=result.slippage_pct, delay=result.execution_delay)
    if key in st.session_state:
        table = st.session_state[key]
        if (table.Status == "Pass").all():
            st.success(f"No historical changes found at {len(table)} tested cutoffs.")
        elif table.Status.isin(["Fail", "Error"]).any():
            st.error("Some checks failed or could not complete. Review the cutoffs and mismatch details.")
        else:
            st.info("There is insufficient history for a meaningful prefix check.")
        st.dataframe(table, hide_index=True, width="stretch", key=f"{scope}_audit_table")
        st.download_button("Download audit checks", table.to_csv(index=False), "future_data_audit.csv",
                            "text/csv", key=f"{scope}_audit_download")
    st.caption("These are sampled consistency checks, not proof against all bias. They do not certify historical data vintages, survivorship, or out-of-sample performance.")


def trade_evidence_tab(saved, signals, result):
    token = snapshot_id(signals, saved)[:12]
    evidence_view(signals, result, saved["strategy"], saved["params"], f"baseline_{token}")
    st.divider()
    audit_view(saved, signals, result, f"baseline_{token}")


def failure_report_tab(saved, signals):
    section_title("Break My Strategy", "Find which tested assumptions change your historical result, then inspect the trades behind it.")
    st.caption(f"Analyzes the saved {saved['ticker']} run with {saved['strategy']}. Pending setup edits are not included.")
    with st.expander("Stress-test ranges", expanded=False):
        a, b = st.columns(2)
        extra_cost = a.number_input("Maximum extra fee (percentage points)", 0.01, 20.0, DEFAULT_LIMITS["extra_cost"], step=0.05, key="stress_cost")
        slippage = b.number_input("Maximum adverse slippage (%)", 0.01, 20.0, DEFAULT_LIMITS["slippage"], step=0.05, key="stress_slippage")
        extra_delay = a.number_input("Maximum extra delay (sessions)", 1, 20, DEFAULT_LIMITS["extra_delay"], key="stress_delay")
        start_shift = b.number_input("Maximum later start (sessions)", 1, 20, DEFAULT_LIMITS["start_shift"], key="stress_start")
        st.caption("Five fee levels and five slippage levels; every delay up to the maximum; three later starts (deduplicated). Each period changes about ±10% (at least 1 bar), each RSI threshold ±5 points, each momentum threshold ±1 percentage point. One setting changes at a time.")
    limits = dict(extra_cost=extra_cost, slippage=slippage, extra_delay=extra_delay, start_shift=start_shift)
    token = snapshot_id(signals, saved)
    report = st.session_state.get("failure_report")
    if report is not None and report.fingerprint != token:
        st.session_state.pop("failure_report", None)
        report = None
    if st.button("Break my strategy", type="primary", key="run_failure", icon=":material/science:"):
        progress = st.progress(0.0, text="Evaluating independent scenarios…")
        try:
            report = run_failure_analysis(signals, saved, limits, progress=lambda x: progress.progress(x))
            st.session_state["failure_report"] = report
        except ValueError as exc:
            st.error(str(exc))
        finally:
            progress.empty()
    if report is None:
        st.info("Run the diagnostic to compare the saved strategy with changes to fees, slippage, execution timing, parameters and start date. No new market download is needed.")
        return
    if report.limits != limits:
        st.warning("Stress ranges changed. This is the previous diagnostic; click Break my strategy to update it.")
    table = report.table
    baseline = table.iloc[0]
    variants = table.iloc[1:]
    for col, label, value in zip(st.columns(4), ["Baseline return", "Completed variations", "Loss-making variations", "No-trade variations"],
        [fmt(baseline["Return %"], "%"), str((variants.Status == "Completed").sum()),
         str((variants.Outcome == "Loss").sum()), str((variants.Outcome == "No trades").sum())]):
        col.metric(label, value)
    if baseline.Outcome != "Profit":
        st.warning(f"Baseline outcome: {baseline.Outcome.lower()}. There is no positive baseline return to break; changes remain useful for comparison.")
    else:
        st.caption("Failure means negative total portfolio return after modeled costs, including open holdings. Counts are historical scenario results, not probabilities.")
    st.write("")
    section_title("Smallest tested failing changes")
    st.dataframe(report.findings, hide_index=True, width="stretch", key="failure_findings")
    st.caption("These are grid observations, not exact break-even boundaries. Each parameter is its own category; equal-size changes may have different results. Skipped and no-trade cases are not evidence of robustness.")
    section_title("Choose a scenario to investigate", "Click a table row or use the scenario picker, then click a trade marker below.")
    scope = f"failure_{token[:12]}_{sha256(json.dumps(report.limits, sort_keys=True).encode()).hexdigest()[:6]}"
    table_key, choice_key = f"{scope}_table", f"{scope}_choice"
    ids = table.Scenario.tolist()
    shown = table[["Scenario", "Category", "Change", "Outcome", "Return %", "Change vs baseline (pp)",
                   "Max drawdown %", "Closed trades", "Orders", "Status", "Reason"]]
    st.dataframe(shown, hide_index=True, width="stretch", height=300, key=table_key,
                 on_select=lambda: choose_scenario_from_table(table_key, choice_key, ids), selection_mode="single-row")
    failed = table[(table.Scenario != "baseline") & (table.Outcome == "Loss")]
    default_id = failed.Scenario.iloc[0] if not failed.empty else "baseline"
    chosen = st.selectbox("Scenario to inspect", ids, index=ids.index(default_id), key=choice_key,
                           format_func=lambda id_: f"{id_} · {report.runs[id_].scenario.change}")
    st.download_button("Download complete failure report", export_failure_report(report),
                        f"{saved['ticker']}_failure_report.zip", "application/zip", key="failure_download")
    run = report.runs[chosen]
    if run.error:
        st.warning(f"This scenario was skipped: {run.error}")
        return
    s = run.scenario
    html(f'<div class="evidence-banner"><span>{escape(s.family.upper())}</span><strong>{escape(s.change)}</strong>'
         f'<small>Fee {s.cost:g}% · Slippage {s.slippage:g}% · Signal-to-fill delay {s.delay} bar(s)</small></div>')
    if s.start_offset:
        st.info("This scenario starts later, restarts in cash and warms up indicators again. It covers a shorter period than the baseline.")
    plot(comparison_chart(report.runs["baseline"].result, run.result), f"{scope}_{chosen}_equity")
    st.caption(f"Selected period: {run.signals.index[0]:%d %b %Y} — {run.signals.index[-1]:%d %b %Y}. The dotted curve is the original baseline buy-and-hold reference.")
    evidence_view(run.signals, run.result, saved["strategy"], s.params, f"{scope}_{chosen}")
    with st.expander("Execution assumptions and interpretation"):
        st.write("Slippage raises buys and lowers sells relative to the open. It is a sensitivity assumption, not a calibrated spread or liquidity model, and may place modeled fills outside a daily candle. Fees apply to the slipped notional. Open holdings remain marked at the unmodified close.")
        st.write("A delay is a fixed shift of each original intent; later signals do not cancel an older intent. Fills occur on available valid bars, not calendar days. Intents beyond the last bar cannot fill. Each scenario maintains one long position and ignores ineligible intents.")
        st.write("Start-date tests change the evaluation period and indicator warm-up. Other tests use the same dates. These experiments do not combine shocks, optimize parameters, estimate success probabilities or validate unseen data.")
