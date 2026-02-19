from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import numpy as np

from .ai_brief import summarize_with_openai
from .market_data import hist_close, rsi, sma
from .news import fetch_macro_headlines, fetch_news


def analyze_market() -> None:
    """
    Prints a market snapshot + optional AI brief.
    """

    # Use Yahoo symbols consistently:
    # Dollar Index futures = DX=F  (not "DXY")
    symbols = ["SPY", "QQQ", "IWM", "TLT", "DX=F", "^VIX"]

    info: Dict[str, Dict[str, Any]] = {}
    for s in symbols:
        h = hist_close(s, 200)
        if h.empty:
            continue

        p = float(h.iloc[-1])
        s20 = sma(h, 20)
        s50 = sma(h, 50)
        s200 = sma(h, 200)
        rr = rsi(h, 14)

        trend = "—"
        if not np.isnan(s50):
            trend = "UP" if p > s50 else "DOWN"

        cross = "flat"
        if not np.isnan(s20) and not np.isnan(s50):
            cross = "bullish" if s20 > s50 else "bearish" if s20 < s50 else "flat"

        info[s] = {
            "price": round(p, 2),
            "rsi": None if np.isnan(rr) else round(float(rr), 1),
            "trend": trend,
            "cross": cross,
            "sma20": None if np.isnan(s20) else round(float(s20), 2),
            "sma50": None if np.isnan(s50) else round(float(s50), 2),
            "sma200": None if np.isnan(s200) else round(float(s200), 2),
        }

    equity_news = fetch_news(["SPY", "QQQ", "AAPL", "NVDA", "MSFT", "TLT"], per_sym=4)
    macro_news = fetch_macro_headlines()

    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "technicals": info,
        "equity_headlines": equity_news,
        "macro_headlines": macro_news,
    }

    try:
        note = summarize_with_openai(payload)
    except Exception as e:
        note = f"(AI summary unavailable: {e})"

    def line(sym: str, name: str) -> str:
        d = info.get(sym)
        if not d:
            return f"{name}: (no data)"
        rsi_txt = "" if d["rsi"] is None else f" | RSI {d['rsi']:.0f}"
        return f"{name}: {d['trend']} | 20/50 {d['cross']}{rsi_txt} | Px {d['price']:.2f}"

    print("\n=== Market Snapshot ===")
    print(line("SPY", "S&P 500"))
    print(line("QQQ", "Nasdaq 100"))
    print(line("IWM", "Russell 2000"))
    print(line("TLT", "Long Bonds"))
    print(line("DX=F", "US Dollar"))
    print(line("^VIX", "VIX"))

    print("\n— Macro headlines —")
    if not macro_news:
        print("(none)")
    else:
        for n in macro_news[:8]:
            print(f"• {n['title']} — {n['source']} ({n['published']})")

    print("\n— Equity headlines —")
    if not equity_news:
        print("(none)")
    else:
        for n in equity_news[:8]:
            print(f"• [{n['symbol']}] {n['title']} — {n['publisher']} ({n['time']})")

    print("\n— AI Take —")
    print(note)
    print("\n(General information only; not investment advice.)")

