"""Presentation helpers. These functions do not change signals or trade accounting."""
from base64 import b64encode
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

GREEN = "#13755d"
INK = "#192d2b"
PURPLE = "#9382c6"
RED = "#c45664"
GOLD = "#b28a44"
ASSETS = Path(__file__).resolve().parent / "assets"
CHART_CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


@st.cache_data
def stylesheet():
    css = (ASSETS / "theme.css").read_text(encoding="utf-8")
    font = ASSETS / "inter-latin.woff2"
    if font.is_file():
        encoded = b64encode(font.read_bytes()).decode("ascii")
        css = ("@font-face{font-family:QuantInter;src:url(data:font/woff2;base64," + encoded
               + ") format('woff2');font-weight:100 900;font-style:normal;font-display:swap;}" + css)
    return css


def install_theme():
    # Style-only HTML uses Streamlit's event container, leaving no blank layout row.
    st.html("<style>" + stylesheet() + "</style>")


def fmt(value, suffix="", decimals=2, signed=False):
    if pd.isna(value):
        return "N/A"
    if np.isinf(value):
        return "∞"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:,.{decimals}f}{suffix}"


def tone(value):
    return "positive" if value >= 0 else "negative"


def brand():
    """Render the existing wordmark in the full-width page header."""
    logo = b64encode((ASSETS / "quantlab-logo.svg").read_bytes()).decode("ascii")
    html(f'<header class="topbar"><div class="topbar-identity">'
         f'<img class="brand-wordmark" src="data:image/svg+xml;base64,{logo}" alt="QuantLab"/>'
         '<span class="header-section">Strategy research</span></div>'
         '<div class="topbar-meta"><span>Yahoo Finance · Daily market data</span>'
         '<span class="workspace-badge">PERSONAL WORKSPACE</span></div></header>')


def section_title(title, subtitle=None, eyebrow=None):
    label = f'<div class="eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p class="section-sub">{escape(subtitle)}</p>' if subtitle else ""
    html(f'{label}<h3 class="section-title">{escape(title)}</h3>{sub}')


def small_stat(label, value, note="", style=""):
    html(f'<div class="small-stat"><span>{escape(label)}</span>'
         f'<strong class="{style}">{escape(str(value))}</strong><small>{escape(note)}</small></div>')


def sparkline(values, color=GREEN):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return ""
    indices = np.linspace(0, len(values) - 1, min(len(values), 100), dtype=int)
    values = values[indices]
    spread = np.ptp(values)
    ys = 36 - (values - values.min()) / (spread if spread else 1) * 30
    xs = np.linspace(2, 158, len(values))
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<svg class="sparkline" aria-hidden="true" viewBox="0 0 160 40">'
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def style_figure(fig, height=320):
    fig.update_layout(
        template="plotly_white", height=height, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family="QuantInter, Inter, Arial, sans-serif", color="#7c8885", size=11),
        margin=dict(l=6, r=12, t=12, b=12), hovermode="x unified",
        hoverlabel=dict(bgcolor="#192d2b", bordercolor="#192d2b", font=dict(color="#fff", size=12)),
        legend=dict(orientation="h", x=0, y=1.16, font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        dragmode="pan", xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False, ticks="", nticks=7, tickformat="%b %y")
    fig.update_yaxes(gridcolor="#edf0ed", zeroline=False, side="right", tickfont=dict(size=11), nticks=5)
    return fig


def equity_chart(eq, initial_capital, as_return=False):
    strategy = (eq.Equity / initial_capital - 1) * 100 if as_return else eq.Equity
    benchmark = (eq["Buy & Hold"] / initial_capital - 1) * 100 if as_return else eq["Buy & Hold"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=benchmark, name="Buy & hold",
                             line=dict(color=PURPLE, width=1.8, dash="dot")))
    fig.add_trace(go.Scatter(x=eq.index, y=strategy, name="Strategy",
                             line=dict(color=GREEN, width=2.6)))
    fig.add_trace(go.Scatter(x=[eq.index[-1]], y=[strategy.iloc[-1]], mode="markers", showlegend=False,
                             hoverinfo="skip", marker=dict(color=GREEN, size=7, line=dict(color="white", width=2))))
    style_figure(fig, 290)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(tickformat=".1f" if as_return else "~s", ticksuffix="%" if as_return else "")
    return fig


def price_chart(data, orders, params, chart_type="Candlestick"):
    oscillator = "RSI" if "RSI" in data else "Momentum" if "Momentum" in data else None
    fig = make_subplots(rows=2 if oscillator else 1, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3] if oscillator else [1], vertical_spacing=0.10)
    if chart_type == "Candlestick":
        fig.add_trace(go.Candlestick(x=data.index, open=data.Open, high=data.High, low=data.Low, close=data.Close,
                                     name="Adjusted OHLC", increasing_line_color=GREEN, decreasing_line_color=RED,
                                     increasing_fillcolor=GREEN, decreasing_fillcolor=RED), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=data.index, y=data.Close, name="Adjusted close",
                                 line=dict(color=INK, width=1.8)), row=1, col=1)
    for col, label, color in [("Short_MA", "Short SMA", GREEN), ("Long_MA", "Long SMA", GOLD)]:
        if col in data:
            fig.add_trace(go.Scatter(x=data.index, y=data[col], name=label,
                                     line=dict(color=color, width=1.7)), row=1, col=1)
    for side, color, symbol in [("BUY", GREEN, "triangle-up"), ("SELL", RED, "triangle-down")]:
        selected = orders.loc[orders.Side == side]
        order_ids = selected["Order ID"] if "Order ID" in selected else selected.index + 1
        fig.add_trace(go.Scatter(
            x=selected.Date, y=selected.Price, mode="markers", name=f"{side} fill",
            customdata=np.asarray(order_ids).reshape(-1, 1),
            marker=dict(color=color, size=11, symbol=symbol, line=dict(color="#fff", width=1.5)),
            hovertemplate=f"{side} · order #%{{customdata[0]}}<br>%{{x|%d %b %Y}}<br>Fill %{{y:,.2f}}<extra></extra>"), row=1, col=1)
    if oscillator:
        fig.add_trace(go.Scatter(x=data.index, y=data[oscillator], name=oscillator,
                                 line=dict(color=PURPLE, width=1.8)), row=2, col=1)
        thresholds = ([params["lower"], params["upper"]] if oscillator == "RSI" else
                      [params["exit_threshold"], params["entry_threshold"]])
        for threshold in thresholds:
            fig.add_hline(y=threshold, line_dash="dot", line_color="#b3aaa0", row=2, col=1)
        if oscillator == "RSI":
            fig.add_hrect(y0=thresholds[0], y1=thresholds[1], line_width=0,
                          fillcolor="rgba(147,130,198,0.06)", row=2, col=1)
            fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.update_yaxes(title_text=oscillator, row=2, col=1)
    style_figure(fig, 490 if oscillator else 345)
    fig.update_layout(margin=dict(t=40), legend=dict(y=1.11))
    return fig


def drawdown_chart(eq):
    fig = go.Figure(go.Scatter(x=eq.index, y=eq.Drawdown * 100, name="Drawdown", fill="tozeroy",
                               line=dict(color=RED, width=1.5), fillcolor="rgba(196,86,100,0.08)"))
    style_figure(fig, 215)
    fig.update_yaxes(ticksuffix="%")
    return fig


def monthly_return_chart(eq, initial_capital):
    month_end = eq.Equity.resample("ME").last()
    returns = month_end.pct_change(fill_method=None) * 100
    returns.iloc[0] = (month_end.iloc[0] / initial_capital - 1) * 100
    returns = returns.tail(18)
    fig = go.Figure(go.Bar(x=returns.index, y=returns, name="Monthly return", marker_color=[
        GREEN if value >= 0 else "#d39199" for value in returns], marker_line_width=0,
        hovertemplate="%{x|%b %Y}<br>%{y:+.2f}%<extra></extra>"))
    style_figure(fig, 215)
    fig.update_layout(bargap=0.48)
    fig.update_yaxes(ticksuffix="%")
    return fig


def plot(fig, key):
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG, theme=None, key=key)
