"""yfinanceを用いた株価・出来高取得、チャート生成、週足乖離率の計算。

「健全な乖離」か「過熱懸念」かといった定性判定はここでは行わず、
数値(乖離率・過去分布上の位置・トレンド傾き)の算出までに留める。
定性判定は gemini_client.classify_deviations_batch に委ねる。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

# チャート内の日本語ラベルが文字化けしないよう、CJK対応フォントを指定する
# (GitHub Actions側で `fonts-noto-cjk` パッケージのインストールが必要。README参照)
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "IPAexGothic", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

VOLUME_ALERT_RATIO = 2.0


@dataclass
class TickerSnapshot:
    code: str
    name: str
    yf_ticker: str
    close: float
    prev_close: float
    change_pct: float
    volume: int
    avg_volume_20d: float
    volume_ratio: float
    volume_alert: bool
    trend: str  # "上昇局面" / "下落局面" / "もみ合い" / "判定不可"
    ma25w: float | None
    ma75w: float | None
    dev25w_pct: float | None
    dev75w_pct: float | None
    dev25w_percentile: float | None
    ma25w_slope_pct: float | None
    daily_chart_path: Path | None = None
    weekly_chart_path: Path | None = None


def _trend_from_daily(df: pd.DataFrame) -> str:
    ma25 = df["Close"].rolling(25).mean()
    if len(ma25.dropna()) < 6:
        return "判定不可"
    latest_close = df["Close"].iloc[-1]
    latest_ma = ma25.iloc[-1]
    slope = ma25.iloc[-1] - ma25.iloc[-6]
    if latest_close > latest_ma and slope > 0:
        return "上昇局面"
    if latest_close < latest_ma and slope < 0:
        return "下落局面"
    return "もみ合い"


def fetch_snapshot(code: str, name: str, yf_ticker: str) -> TickerSnapshot:
    """株価・出来高・乖離率スナップショットを取得する(チャート画像は別途生成)。"""
    ticker = yf.Ticker(yf_ticker)
    daily = ticker.history(period="6mo", interval="1d")
    weekly = ticker.history(period="3y", interval="1wk")
    if daily.empty or len(daily) < 21:
        raise ValueError(f"{yf_ticker} の日足データを取得できませんでした")

    close = float(daily["Close"].iloc[-1])
    prev_close = float(daily["Close"].iloc[-2])
    change_pct = (close - prev_close) / prev_close * 100
    volume = int(daily["Volume"].iloc[-1])
    avg_volume_20d = float(daily["Volume"].iloc[-21:-1].mean())
    volume_ratio = volume / avg_volume_20d if avg_volume_20d else 0.0
    volume_alert = volume_ratio >= VOLUME_ALERT_RATIO
    trend = _trend_from_daily(daily)

    ma25w = ma75w = dev25w = dev75w = dev25w_pctl = ma25w_slope = None
    if not weekly.empty:
        wclose = weekly["Close"]
        ma25w_series = wclose.rolling(25).mean()
        ma75w_series = wclose.rolling(75).mean()
        if not pd.isna(ma25w_series.iloc[-1]):
            ma25w = float(ma25w_series.iloc[-1])
            dev25w_series = (wclose - ma25w_series) / ma25w_series * 100
            dev25w = float(dev25w_series.iloc[-1])
            hist = dev25w_series.dropna()
            if len(hist) > 10:
                dev25w_pctl = float((hist < dev25w).mean() * 100)
            if len(ma25w_series.dropna()) >= 8:
                ma25w_slope = float(ma25w_series.iloc[-1] - ma25w_series.iloc[-8])
        if not pd.isna(ma75w_series.iloc[-1]):
            ma75w = float(ma75w_series.iloc[-1])
            dev75w = float((wclose.iloc[-1] - ma75w) / ma75w * 100)

    return TickerSnapshot(
        code=code,
        name=name,
        yf_ticker=yf_ticker,
        close=close,
        prev_close=prev_close,
        change_pct=change_pct,
        volume=volume,
        avg_volume_20d=avg_volume_20d,
        volume_ratio=volume_ratio,
        volume_alert=volume_alert,
        trend=trend,
        ma25w=ma25w,
        ma75w=ma75w,
        dev25w_pct=dev25w,
        dev75w_pct=dev75w,
        dev25w_percentile=dev25w_pctl,
        ma25w_slope_pct=ma25w_slope,
    )


def render_charts(snapshot: TickerSnapshot, chart_dir: Path) -> None:
    """アラート対象銘柄のみ呼び出す想定(LINE無料メッセージ枠を圧迫しないため)。"""
    chart_dir.mkdir(parents=True, exist_ok=True)
    ticker = yf.Ticker(snapshot.yf_ticker)
    daily = ticker.history(period="6mo", interval="1d")
    weekly = ticker.history(period="3y", interval="1wk")
    snapshot.daily_chart_path = _render_daily_chart(snapshot, daily, chart_dir)
    if not weekly.empty:
        snapshot.weekly_chart_path = _render_weekly_chart(snapshot, weekly, chart_dir)


def _render_daily_chart(snapshot: TickerSnapshot, df: pd.DataFrame, chart_dir: Path) -> Path:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(7, 5), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    df["Close"].plot(ax=ax1, color="#1f77b4", label="終値")
    df["Close"].rolling(5).mean().plot(ax=ax1, color="#ff7f0e", linewidth=1, label="5日MA")
    df["Close"].rolling(25).mean().plot(ax=ax1, color="#2ca02c", linewidth=1, label="25日MA")
    ax1.set_title(f"{snapshot.name} ({snapshot.code}) 日足")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)
    ax2.bar(df.index, df["Volume"], color="#888888", width=0.8)
    ax2.set_ylabel("出来高", fontsize=8)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    path = chart_dir / f"{snapshot.code}_daily.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def _render_weekly_chart(snapshot: TickerSnapshot, df: pd.DataFrame, chart_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4))
    df["Close"].plot(ax=ax, color="#1f77b4", label="終値")
    df["Close"].rolling(25).mean().plot(ax=ax, color="#ff7f0e", linewidth=1, label="25週MA")
    df["Close"].rolling(75).mean().plot(ax=ax, color="#d62728", linewidth=1, label="75週MA")
    ax.set_title(f"{snapshot.name} ({snapshot.code}) 週足")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = chart_dir / f"{snapshot.code}_weekly.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path
