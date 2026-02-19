from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser
import yfinance as yf


def _safe_unix_to_iso(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def fetch_rss_items(feeds: List[str], per_feed: int = 5) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for e in (f.entries or [])[:per_feed]:
                items.append(
                    {
                        "source": f.feed.get("title", url),
                        "title": (getattr(e, "title", "") or "").strip(),
                        "published": getattr(e, "published", "") or getattr(e, "updated", ""),
                        "link": getattr(e, "link", ""),
                    }
                )
        except Exception:
            continue
    items = [it for it in items if it.get("title")]
    return items[: min(30, len(items))]


def fetch_macro_headlines() -> List[Dict[str, Any]]:
    feeds = [
        "https://www.bls.gov/feeds/news_release/cpi.rss",
        "https://www.bls.gov/feeds/news_release/empsit.rss",
        "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "https://www.bea.gov/news/rss.xml",
    ]
    return fetch_rss_items(feeds, per_feed=5)


def fetch_news(symbols: List[str], per_sym: int = 5) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen = set()

    # primary: yfinance
    for s in symbols:
        sym = s.strip().upper()
        try:
            for it in (yf.Ticker(sym).news or []):
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                key = (title, it.get("link"))
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "symbol": sym,
                        "title": title,
                        "publisher": (it.get("publisher") or "").strip(),
                        "time": _safe_unix_to_iso(it.get("providerPublishTime")),
                        "link": it.get("link", ""),
                    }
                )
        except Exception:
            continue

    # fallback: Yahoo Finance RSS
    if not items:
        for s in symbols:
            sym = s.strip().upper()
            try:
                rss = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
                feed = feedparser.parse(rss)
                for e in (feed.entries or [])[:per_sym]:
                    title = (getattr(e, "title", "") or "").strip()
                    if not title:
                        continue
                    key = (title, getattr(e, "link", ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(
                        {
                            "symbol": sym,
                            "title": title,
                            "publisher": feed.feed.get("title", "Yahoo Finance"),
                            "time": getattr(e, "published", ""),
                            "link": getattr(e, "link", ""),
                        }
                    )
            except Exception:
                continue

    # newest-ish first
    def _score(x: Dict[str, Any]) -> float:
        t = x.get("time") or ""
        try:
            return datetime.strptime(t, "%Y-%m-%d %H:%M").timestamp()
        except Exception:
            return 0.0

    items.sort(key=_score, reverse=True)
    return items[: max(1, per_sym * len(symbols))]

