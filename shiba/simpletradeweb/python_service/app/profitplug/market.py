import math
import time
import requests
import feedparser
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import os

load_dotenv()

def last_price(symbol: str) -> Optional[float]:
    try:
        t = yf.Ticker(symbol)
        px = t.history(period="1d", interval="1m")["Close"].dropna()
        if len(px) == 0:
            px = t.history(period="5d")["Close"].dropna()
        return float(px.iloc[-1]) if len(px) else None
    except Exception:
        return None

def hist_close(symbol: str, days: int = 200) -> Optional[pd.Series]:
    try:
        df = yf.Ticker(symbol).history(period=f"{days}d")
        if "Close" not in df.columns: 
            return None
        s = df["Close"].dropna()
        return s if len(s) else None
    except Exception:
        return None

def sma(series: pd.Series, window: int) -> Optional[float]:
    try:
        if series is None or len(series) < window:
            return None
        return float(series.rolling(window).mean().iloc[-1])
    except Exception:
        return None

def rsi(series: pd.Series, window: int = 14) -> Optional[float]:
    try:
        if series is None or len(series) < window + 1:
            return None
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss
        val = 100 - (100 / (1 + rs))
        out = float(val.iloc[-1])
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None

def fetch_news(symbols: List[str], per_sym: int = 3) -> List[Dict[str, Any]]:
    # Simple RSS approach: Yahoo Finance RSS queries
    items: List[Dict[str, Any]] = []
    for sym in symbols:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
            feed = feedparser.parse(url)
            for e in feed.entries[:per_sym]:
                when = ""
                if hasattr(e, "published"):
                    when = e.published
                items.append({
                    "symbol": sym,
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "time": when,
                    "publisher": "Yahoo Finance RSS"
                })
        except Exception:
            continue
    return items

def show_symbol(symbol: str, headlines: int = 5) -> Dict[str, Any]:
    sym = symbol.upper()
    t = yf.Ticker(sym)

    px = last_price(sym)
    s = hist_close(sym, 260)
    rsi14 = rsi(s, 14) if s is not None else None
    s20 = sma(s, 20) if s is not None else None
    s50 = sma(s, 50) if s is not None else None
    s200 = sma(s, 200) if s is not None else None

    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    fundamentals = {
        "longName": info.get("longName") or info.get("shortName"),
        "currency": info.get("currency"),
        "marketCap": info.get("marketCap"),
        "trailingPE": info.get("trailingPE"),
        "epsTrailingTwelveMonths": info.get("epsTrailingTwelveMonths"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
        "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "nextEarningsDate": info.get("earningsTimestamp")  # unix sometimes
    }

    news = fetch_news([sym], per_sym=headlines)

    return {
        "symbol": sym,
        "price": px,
        "technicals": {
            "rsi14": rsi14,
            "sma20": s20,
            "sma50": s50,
            "sma200": s200
        },
        "fundamentals": fundamentals,
        "headlines": news
    }

def analyze_market(tickers: List[str]) -> Dict[str, Any]:
    snapshot = []
    for sym in tickers:
        px = last_price(sym)
        snapshot.append({"symbol": sym, "price": px})
    news = fetch_news(tickers[:3], per_sym=3)
    return {"snapshot": snapshot, "headlines": news}

def ai_take(market_payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"enabled": False, "text": "OPENAI_API_KEY not set. Add it to python_service/.env to enable AI market notes."}

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    prompt = (
        "You are a trading education assistant. Given this market snapshot and headlines, "
        "write a short, student-friendly daily note.\n\n"
        "Include:\n"
        "- What moved today (or what looks notable)\n"
        "- One risk reminder\n"
        "- One simple exercise to try in a simulator\n\n"
        f"DATA:\n{market_payload}"
    )

    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )
    text = r.choices[0].message.content
    return {"enabled": True, "model": model, "text": text}

