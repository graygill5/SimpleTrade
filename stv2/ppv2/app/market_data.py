from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf


def last_price(symbol: str) -> Optional[float]:
    """
    Best-effort: minute data (1d) then daily data (5d).
    """
    sym = symbol.strip().upper()
    try:
        px = yf.Ticker(sym).history(period="1d", interval="1m")["Close"].dropna()
        if len(px) == 0:
            px = yf.Ticker(sym).history(period="5d")["Close"].dropna()
        return float(px.iloc[-1]) if len(px) else None
    except Exception:
        return None


def hist_close(symbol: str, days: int = 200) -> pd.Series:
    """
    Returns daily close series for at least 60 days (yfinance needs enough buffer sometimes).
    """
    sym = symbol.strip().upper()
    try:
        return yf.Ticker(sym).history(period=f"{max(days, 60)}d")["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)


def sma(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float("nan")
    return float(series.rolling(n).mean().iloc[-1])


def rsi(series: pd.Series, n: int = 14) -> float:
    if len(series) < n + 1:
        return float("nan")

    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(n).mean()
    roll_down = pd.Series(down, index=series.index).rolling(n).mean()

    rs = roll_up / (roll_down + 1e-9)
    return float((100 - (100 / (1 + rs))).iloc[-1])

