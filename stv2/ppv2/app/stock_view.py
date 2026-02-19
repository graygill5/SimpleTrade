from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import yfinance as yf
from colorama import Fore, Style

from .market_data import hist_close, last_price, rsi, sma
from .news import fetch_news


def _fmt_num(x: Any) -> str:
    try:
        x = float(x)
    except Exception:
        return "-"
    absx = abs(x)
    if absx >= 1e12:
        return f"{x/1e12:.2f}T"
    if absx >= 1e9:
        return f"{x/1e9:.2f}B"
    if absx >= 1e6:
        return f"{x/1e6:.2f}M"
    if absx >= 1e3:
        return f"{x/1e3:.2f}K"
    return f"{x:.2f}"


def _safe(val: Any, default: str = "-") -> Any:
    return default if val in (None, "", float("nan")) else val


def show(stock: str, headlines: int = 3) -> None:
    sym = stock.strip().upper()
    tk = yf.Ticker(sym)

    px = last_price(sym)
    hist = hist_close(sym, 250)

    if px is None and hist.empty:
        print(f"✖ No price data for '{sym}'. Try Yahoo symbols (ex: DX=F, ^VIX).")
        return

    day_chg = None
    if not hist.empty and len(hist) >= 2:
        prev = float(hist.iloc[-2])
        if prev != 0 and px is not None:
            day_chg = (px - prev) / prev * 100.0

    lo52 = float(hist.min()) if not hist.empty else None
    hi52 = float(hist.max()) if not hist.empty else None

    rsi14 = rsi(hist, 14)
    s20 = sma(hist, 20)
    s50 = sma(hist, 50)
    s200 = sma(hist, 200)

    long_name = None
    pe = None
    eps = None
    beta = None
    sector = None

    try:
        i2 = tk.get_info()
        long_name = i2.get("longName")
        pe = i2.get("trailingPE") or i2.get("forwardPE")
        eps = i2.get("trailingEps")
        beta = i2.get("beta")
        sector = i2.get("sector")
    except Exception:
        pass

    try:
        finfo = tk.fast_info or {}
    except Exception:
        finfo = {}

    mktcap = finfo.get("market_cap")
    currency = finfo.get("currency") or "USD"

    news = fetch_news([sym], per_sym=headlines)

    name_display = long_name or sym
    print(f"\n--- {Fore.LIGHTBLUE_EX}{name_display}{Style.RESET_ALL} ({sym}) ---")
    if px is not None:
        price_line = f"Price: {currency} {px:.2f}"
        if day_chg is not None:
            arrow = "▲" if day_chg >= 0 else "▼"
            price_line += f"   {arrow} {day_chg:.2f}%"
        print(price_line)
    else:
        print("Price: -")

    if lo52 is not None and hi52 is not None:
        print(f"52w:  {lo52:.2f}  –  {hi52:.2f}")

    print("\nFundamentals:")
    print(f"  Market Cap: {_fmt_num(mktcap)}")
    pe_txt = _safe(f"{pe:.2f}" if isinstance(pe, (int, float)) else pe)
    eps_txt = _safe(f"{eps:.2f}" if isinstance(eps, (int, float)) else eps)
    beta_txt = _safe(f"{beta:.2f}" if isinstance(beta, (int, float)) else beta)
    print(f"  P/E: {pe_txt}   EPS (ttm): {eps_txt}")
    print(f"  Beta: {beta_txt}   Sector: {_safe(sector)}")

    print("\nTechnical:")
    def _fmt(v: float) -> str:
        return "-" if (v is None or (isinstance(v, float) and np.isnan(v))) else f"{v:.2f}"

    print(f"  RSI(14): {_fmt(rsi14)}   SMA20: {_fmt(s20)}   SMA50: {_fmt(s50)}   SMA200: {_fmt(s200)}")

    print("\nHeadlines:")
    if not news:
        print("  (none)")
    else:
        for n in news[:headlines]:
            title = (n.get("title") or "").strip()
            pub = (n.get("publisher") or "").strip()
            when = n.get("time") or ""
            extra = (f" — {pub}" if pub else "") + (f" ({when})" if when else "")
            if title:
                print(f"  • {title}{extra}")

