from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from contextlib import closing

from app.db import get_conn, init_db
from app.account import PaperAccount
from app.market_data import last_price, hist_close, rsi, sma
from app.news import fetch_macro_headlines, fetch_news
from app.ai_brief import summarize_with_openai


def get_account(account_name: str = "Main") -> PaperAccount:
    acc_id = init_db(starting_cash=1_000_000.0, account_name=account_name)
    return PaperAccount(acc_id)


def portfolio_json(acct: PaperAccount) -> Dict[str, Any]:
    with closing(get_conn()) as conn:
        cash = float(
            conn.execute("SELECT cash FROM accounts WHERE id=?", (acct.account_id,))
            .fetchone()["cash"]
        )

        positions = []
        for r in conn.execute(
            "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=? ORDER BY symbol",
            (acct.account_id,),
        ):
            sym = r["symbol"]
            sh = int(r["shares"])
            avg = float(r["avg_cost"])
            px = last_price(sym)

            mv = float(px) * sh if px is not None else None
            upnl = (float(px) - avg) * sh if px is not None else None

            positions.append(
                {
                    "symbol": sym,
                    "shares": sh,
                    "avg_cost": avg,
                    "price": None if px is None else float(px),
                    "market_value": mv,
                    "unrealized_pnl": upnl,
                }
            )

    equity = float(acct.equity())
    return {"cash": cash, "equity": equity, "positions": positions}


def history_json(acct: PaperAccount) -> Dict[str, Any]:
    with closing(get_conn()) as conn:
        df = pd.read_sql_query(
            "SELECT time, action, symbol, shares, price, total, realized_pnl "
            "FROM trades WHERE account_id=? ORDER BY time",
            conn,
            params=(acct.account_id,),
        )

    trades = []
    for _, row in df.iterrows():
        trades.append(
            {
                "time": str(row["time"]),
                "action": str(row["action"]),
                "symbol": str(row["symbol"]),
                "shares": int(row["shares"]),
                "price": float(row["price"]),
                "total": float(row["total"]),
                "realized_pnl": None if pd.isna(row["realized_pnl"]) else float(row["realized_pnl"]),
            }
        )
    return {"trades": trades}


def buy(acct: PaperAccount, symbol: str, shares: int) -> str:
    # uses your existing logic (prints are fine, but we return a message for the API)
    before = acct.equity()
    acct.buy(symbol, shares)
    after = acct.equity()
    return f"Bought {shares} {symbol.upper()} (equity {before:,.2f} → {after:,.2f})."


def sell(acct: PaperAccount, symbol: str, shares: int) -> str:
    before = acct.equity()
    acct.sell(symbol, shares)
    after = acct.equity()
    return f"Sold {shares} {symbol.upper()} (equity {before:,.2f} → {after:,.2f})."


def reset(acct: PaperAccount, starting_cash: float = 1_000_000.0) -> str:
    acct.reset(starting_cash=starting_cash)
    return f"Reset account to ${starting_cash:,.2f}."


def stock_snapshot(symbol: str, headlines: int = 5) -> Dict[str, Any]:
    sym = symbol.strip().upper()
    tk = yf.Ticker(sym)

    px = last_price(sym)
    hist = hist_close(sym, 250)

    if px is None and hist.empty:
        return {
            "symbol": sym,
            "name": None,
            "currency": None,
            "price": None,
            "day_change_pct": None,
            "low_52w": None,
            "high_52w": None,
            "market_cap": None,
            "pe": None,
            "eps": None,
            "beta": None,
            "sector": None,
            "rsi14": None,
            "sma20": None,
            "sma50": None,
            "sma200": None,
            "headlines": [],
        }

    day_chg = None
    if not hist.empty and len(hist) >= 2 and px is not None:
        prev = float(hist.iloc[-2])
        if prev != 0:
            day_chg = (float(px) - prev) / prev * 100.0

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
    currency = None
    mktcap = None

    try:
        info = tk.get_info()
        long_name = info.get("longName")
        pe = info.get("trailingPE") or info.get("forwardPE")
        eps = info.get("trailingEps")
        beta = info.get("beta")
        sector = info.get("sector")
    except Exception:
        pass

    try:
        finfo = tk.fast_info or {}
        mktcap = finfo.get("market_cap")
        currency = finfo.get("currency") or "USD"
    except Exception:
        pass

    news = fetch_news([sym], per_sym=headlines)

    def clean(x: Any) -> Optional[float]:
        if x is None:
            return None
        try:
            x = float(x)
            if np.isnan(x):
                return None
            return x
        except Exception:
            return None

    return {
        "symbol": sym,
        "name": long_name,
        "currency": currency,
        "price": clean(px),
        "day_change_pct": clean(day_chg),
        "low_52w": clean(lo52),
        "high_52w": clean(hi52),
        "market_cap": clean(mktcap),
        "pe": clean(pe),
        "eps": clean(eps),
        "beta": clean(beta),
        "sector": sector,
        "rsi14": clean(rsi14),
        "sma20": clean(s20),
        "sma50": clean(s50),
        "sma200": clean(s200),
        "headlines": news[:headlines],
    }


def analyze_market_json() -> Dict[str, Any]:
    symbols = ["SPY", "QQQ", "IWM", "TLT", "DX=F", "^VIX"]

    technicals: Dict[str, Any] = {}
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

        technicals[s] = {
            "price": round(p, 2),
            "rsi": None if np.isnan(rr) else round(float(rr), 1),
            "trend": trend,
            "cross": cross,
            "sma20": None if np.isnan(s20) else round(float(s20), 2),
            "sma50": None if np.isnan(s50) else round(float(s50), 2),
            "sma200": None if np.isnan(s200) else round(float(s200), 2),
        }

    equity_headlines = fetch_news(["SPY", "QQQ", "AAPL", "NVDA", "MSFT", "TLT"], per_sym=4)
    macro_headlines = fetch_macro_headlines()

    payload = {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M local"),
        "technicals": technicals,
        "equity_headlines": equity_headlines,
        "macro_headlines": macro_headlines,
    }

    try:
        ai_note = summarize_with_openai(payload)
    except Exception as e:
        ai_note = f"(AI summary unavailable: {e})"

    return {
        "technicals": technicals,
        "macro_headlines": macro_headlines,
        "equity_headlines": equity_headlines,
        "ai_note": ai_note,
    }

