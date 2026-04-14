"""
Yahoo Finance helpers via yfinance. Best-effort; failures return empty structures.

Bulk yf.download() for many tickers triggers YFRateLimitError; we use sequential
Ticker.history() with small delays and long cache TTL for the movers universe.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    YFRateLimitError = type("YFRateLimitError", (Exception,), {})  # type: ignore[misc,assignment]

for _log in ("yfinance", "urllib3"):
    logging.getLogger(_log).setLevel(logging.WARNING)

# Major US indexes + fear gauge (^NDX = Nasdaq-100, ^NYA = NYSE Composite)
INDEX_SYMBOLS = ["^GSPC", "^DJI", "^IXIC", "^NDX", "^RUT", "^NYA", "^VIX"]

# Liquid names for movers / trending (curated; not exhaustive)
MOVERS_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "HD", "CVX", "MRK", "ABBV",
    "PEP", "KO", "COST", "AVGO", "BAC", "PFE", "TMO", "DIS", "CSCO", "ACN",
    "ADBE", "CRM", "NFLX", "AMD", "INTC", "QCOM", "TXN", "AMAT", "IBM", "GE",
    "CAT", "HON", "UPS", "LOW", "SBUX", "BKNG", "DE", "GILD", "ISRG", "MDT",
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK",
]

_CACHE: dict[str, tuple[float, Any, float]] = {}
# Default cache for news, single-ticker fetches
_TTL_DEFAULT = 120.0
# Index tape: sequential Yahoo calls; cache longer to avoid repeat bursts
_TTL_INDEX = 300.0
_INDEX_FETCH_DELAY = 0.22
# marketCap from ticker.info (cached; fast_info often omits market_cap)
_TTL_MCAP_INFO = 3600.0
# Movers universe does many Yahoo calls; keep results longer to avoid rate limits
_TTL_MOVERS = 600.0
# Pause between sequential history calls (bulk download hammers Yahoo)
_MOVER_FETCH_DELAY = 0.2


def _cache_get(key: str) -> Any | None:
    ent = _CACHE.get(key)
    if not ent:
        return None
    ts, val, ttl = ent
    if time.time() - ts > ttl:
        del _CACHE[key]
        return None
    return val


def _cache_set(key: str, val: Any, ttl: float | None = None) -> None:
    t = ttl if ttl is not None else _TTL_DEFAULT
    _CACHE[key] = (time.time(), val, t)


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _market_cap_from_fast_info(fi: Any) -> float | None:
    """fast_info keys vary by yfinance/Yahoo version."""
    if not fi:
        return None
    for key in ("market_cap", "marketCap", "mcap"):
        try:
            v = fi.get(key) if hasattr(fi, "get") else None
        except Exception:
            v = None
        if v is not None:
            x = _safe_float(v)
            if x is not None:
                return x
    return None


def _fill_market_cap_from_info(sym: str, out: dict[str, Any]) -> None:
    """Yahoo often omits market cap in fast_info; use full info (cached)."""
    if out.get("market_cap") is not None:
        return
    ck = f"mcap_info_{sym}"
    hit = _cache_get(ck)
    if hit is not None:
        if hit == "__none__":
            return
        out["market_cap"] = _safe_float(hit)
        return
    try:
        inf = yf.Ticker(sym).info
        cap = inf.get("marketCap")
        if cap is None:
            cap = inf.get("enterpriseValue")
        v = _safe_float(cap) if cap is not None else None
        if v is not None:
            out["market_cap"] = v
            _cache_set(ck, v, ttl=_TTL_MCAP_INFO)
        else:
            _cache_set(ck, "__none__", ttl=900.0)
    except Exception:
        _cache_set(ck, "__none__", ttl=300.0)


def _index_row_from_history(sym: str, labels: dict[str, str]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": sym,
        "name": labels.get(sym, sym),
        "price": None,
        "change_pct": None,
    }
    try:
        hist = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return row
        close = hist["Close"].dropna()
        if len(close) >= 2:
            last = _safe_float(close.iloc[-1])
            prev = _safe_float(close.iloc[-2])
            if last is not None and prev and prev != 0:
                row["price"] = last
                row["change_pct"] = (last - prev) / prev * 100.0
        elif len(close) == 1:
            row["price"] = _safe_float(close.iloc[-1])
    except YFRateLimitError:
        pass
    except Exception:
        pass
    return row


def fetch_indexes() -> list[dict[str, Any]]:
    """One history() call per index with pacing — bulk yf.download() hits YFRateLimitError."""
    ck = "indexes"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    labels = {
        "^GSPC": "S&P 500",
        "^DJI": "Dow Jones",
        "^IXIC": "Nasdaq Comp",
        "^NDX": "Nasdaq-100",
        "^RUT": "Russell 2000",
        "^NYA": "NYSE Comp",
        "^VIX": "VIX",
    }
    out: list[dict[str, Any]] = []
    for i, sym in enumerate(INDEX_SYMBOLS):
        if i > 0:
            time.sleep(_INDEX_FETCH_DELAY + random.uniform(0, 0.06))
        out.append(_index_row_from_history(sym, labels))

    _cache_set(ck, out, ttl=_TTL_INDEX)
    return out


def _row_from_ticker_history(sym: str) -> dict[str, Any] | None:
    """One symbol via history() only — avoids bulk download + extra fast_info calls (rate limits)."""
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="10d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        close = hist["Close"].dropna()
        vol = hist["Volume"].dropna() if "Volume" in hist.columns else pd.Series(dtype=float)
        if close.empty:
            return None
        last = _safe_float(close.iloc[-1])
        prev = _safe_float(close.iloc[-2]) if len(close) >= 2 else None
        chg = None
        if last is not None and prev is not None and prev != 0:
            chg = (last - prev) / prev * 100.0
        vol_last = _safe_float(vol.iloc[-1]) if not vol.empty else None
        return {
            "symbol": sym,
            "name": sym,
            "price": last,
            "change_pct": chg,
            "volume": vol_last,
        }
    except YFRateLimitError:
        return None
    except Exception:
        return None


def _rows_from_history(symbols: list[str]) -> list[dict[str, Any]]:
    """Sequential history pulls with pacing — bulk yf.download() triggers YFRateLimitError."""
    rows: list[dict[str, Any]] = []
    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(_MOVER_FETCH_DELAY + random.uniform(0, 0.06))
        row = _row_from_ticker_history(sym)
        if row:
            rows.append(row)
    return rows


def _mover_universe_rows() -> list[dict[str, Any]]:
    ck = "mover_rows_raw"
    hit = _cache_get(ck)
    if hit is not None:
        return hit
    rows = _rows_from_history(MOVERS_UNIVERSE)
    _cache_set(ck, rows, ttl=_TTL_MOVERS)
    return rows


def fetch_movers() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ck = "movers"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    rows = _mover_universe_rows()
    valid = [r for r in rows if r.get("change_pct") is not None]
    sorted_up = sorted(valid, key=lambda x: x["change_pct"], reverse=True)[:10]
    sorted_dn = sorted(valid, key=lambda x: x["change_pct"])[:10]
    pair = (sorted_up, sorted_dn)
    _cache_set(ck, pair)
    return pair


def fetch_trending_by_volume() -> list[dict[str, Any]]:
    ck = "trending"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    rows = _mover_universe_rows()
    with_vol = [r for r in rows if r.get("volume")]
    trending = sorted(with_vol, key=lambda x: x["volume"] or 0, reverse=True)[:12]
    _cache_set(ck, trending)
    return trending


def _published_unix_iso(raw: Any) -> tuple[int | None, str | None]:
    """Yahoo may send Unix seconds, milliseconds, or ISO-8601 strings (nested news API)."""
    if raw is None:
        return None, None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp())
            iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return ts, iso
        except ValueError:
            pass
    try:
        ts = int(float(raw))
        if ts > 1_000_000_000_000:  # ms
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return ts, iso
    except (OSError, ValueError, OverflowError, TypeError):
        return None, None


def _flatten_yahoo_news_item(n: dict[str, Any]) -> dict[str, Any] | None:
    """Map yfinance news rows to flat title/publisher/link/time (legacy flat or nested `content`)."""
    content = n.get("content")
    c = content if isinstance(content, dict) else None
    if c:
        title = (c.get("title") or "").strip()
        pub_block = c.get("provider")
        publisher = ""
        if isinstance(pub_block, dict):
            publisher = (pub_block.get("displayName") or "").strip()
        link = ""
        for ukey in ("canonicalUrl", "clickThroughUrl"):
            u = c.get(ukey)
            if isinstance(u, dict) and u.get("url"):
                link = (str(u.get("url") or "")).strip()
                break
        pt = c.get("providerPublishTime")
        if pt is None:
            pt = c.get("pubDate") or c.get("displayTime")
    else:
        title = (n.get("title") or "").strip()
        publisher = (n.get("publisher") or "").strip()
        link = (n.get("link") or "").strip()
        pt = n.get("providerPublishTime")

    if not title:
        return None
    return {
        "title": title,
        "publisher": publisher,
        "link": link,
        "providerPublishTime": pt,
    }


def _normalize_market_news_item(
    raw: dict[str, Any], *, source: str
) -> dict[str, Any]:
    title = (raw.get("title") or "").strip()
    publisher = (raw.get("publisher") or "").strip()
    link = (raw.get("link") or "").strip()
    pub_u, pub_iso = _published_unix_iso(raw.get("providerPublishTime"))
    return {
        "title": title,
        "publisher": publisher,
        "link": link,
        "published": pub_u,
        "published_at": pub_iso,
        "source": source,
    }


def fetch_market_news(limit: int = 18) -> list[dict[str, Any]]:
    """Merged Yahoo Finance headlines from broad market tickers (cached)."""
    lim = max(1, min(int(limit), 50))
    # v2: Yahoo nested `content.*` shape (bust stale empty caches from v1)
    ck = f"news_v2_{lim}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for sym in ("SPY", "QQQ", "^GSPC"):
        try:
            t = yf.Ticker(sym)
            items = getattr(t, "news", None) or []
            for n in items:
                if not isinstance(n, dict):
                    continue
                flat = _flatten_yahoo_news_item(n)
                if not flat:
                    continue
                title = (flat.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                merged.append(_normalize_market_news_item(flat, source=sym))
                if len(merged) >= lim:
                    break
        except Exception:
            continue
        if len(merged) >= lim:
            break

    if merged:
        _cache_set(ck, merged)
    return merged


def format_market_news_for_ai(items: list[dict[str, Any]], limit: int = 14) -> str:
    """Plain-text block of headlines for LLM prompts (titles + publisher when present)."""
    lines: list[str] = []
    for n in items[:limit]:
        title = (n.get("title") or "").strip()
        if not title:
            continue
        pub = (n.get("publisher") or "").strip()
        src = (n.get("source") or "").strip()
        tail = []
        if pub:
            tail.append(pub)
        if src:
            tail.append(f"via {src}")
        suffix = f" — {'; '.join(tail)}" if tail else ""
        lines.append(f"- {title}{suffix}")
    return "\n".join(lines)


def _fetch_quote_history_only(sym: str, *, with_mcap: bool = True) -> dict[str, Any] | None:
    """When fast_info fails completely, still try daily bars."""
    out: dict[str, Any] = {
        "symbol": sym,
        "name": sym,
        "price": None,
        "change_pct": None,
        "volume": None,
        "market_cap": None,
        "currency": "USD",
    }
    _enrich_quote_from_history(sym, out)
    if out.get("price") is None:
        return None
    if with_mcap:
        _fill_market_cap_from_info(sym, out)
    return out


def _enrich_quote_from_history(sym: str, out: dict[str, Any]) -> None:
    """When fast_info omits last price (common with Yahoo), fill from daily history."""
    if out.get("price") is not None and out.get("change_pct") is not None:
        return
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="10d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return
        close = hist["Close"].dropna()
        if close.empty:
            return
        last = _safe_float(close.iloc[-1])
        prev = _safe_float(close.iloc[-2]) if len(close) >= 2 else None
        if out.get("price") is None and last is not None:
            out["price"] = last
        if out.get("change_pct") is None and last is not None and prev is not None and prev != 0:
            out["change_pct"] = (last - prev) / prev * 100.0
        if out.get("volume") is None and "Volume" in hist.columns:
            vol = hist["Volume"].dropna()
            if not vol.empty:
                out["volume"] = _safe_float(vol.iloc[-1])
    except Exception:
        pass


def fetch_quote(symbol: str, *, with_mcap: bool = True) -> dict[str, Any] | None:
    """Quote from Yahoo. Set with_mcap=False for search/autocomplete to avoid extra ticker.info calls (rate limits)."""
    sym = symbol.strip().upper().replace(" ", "")
    if not sym:
        return None
    try:
        t = yf.Ticker(sym)
        fi = t.fast_info
        price = fi.get("last_price") or fi.get("regular_market_price")
        prev = fi.get("previous_close")
        chg_pct = fi.get("regular_market_change_percent")
        if chg_pct is None and price is not None and prev:
            chg_pct = (float(price) - float(prev)) / float(prev) * 100.0
        cap = _market_cap_from_fast_info(fi)
        name = fi.get("shortName") or fi.get("longName") or sym
        vol = fi.get("regular_market_volume") or fi.get("last_volume")
        out: dict[str, Any] = {
            "symbol": sym,
            "name": str(name)[:64],
            "price": _safe_float(price),
            "change_pct": _safe_float(chg_pct),
            "volume": _safe_float(vol),
            "market_cap": cap,
            "currency": fi.get("currency") or "USD",
        }
        _enrich_quote_from_history(sym, out)
        if with_mcap:
            _fill_market_cap_from_info(sym, out)
        return out
    except Exception:
        return _fetch_quote_history_only(sym, with_mcap=with_mcap)


# Price chart ranges: UI key -> (yfinance period, interval)
CHART_RANGE_CONFIG: dict[str, tuple[str, str]] = {
    "1d": ("1d", "5m"),
    "1w": ("5d", "1h"),
    "1m": ("1mo", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
    "10y": ("10y", "1mo"),
}

# Fallback if primary interval returns empty (Yahoo quirks)
CHART_RANGE_FALLBACK: dict[str, tuple[str, str]] = {
    "1d": ("1d", "15m"),
    "1w": ("5d", "1d"),
    "1m": ("3mo", "1d"),
    "1y": ("2y", "1wk"),
    "5y": ("5y", "1mo"),
    "10y": ("max", "3mo"),
}


def fetch_chart_series(symbol: str, range_key: str) -> dict[str, Any] | None:
    """OHLC series for Chart.js: labels + closes. None if unavailable."""
    sym = symbol.strip().upper().replace(" ", "")
    if not sym or range_key not in CHART_RANGE_CONFIG:
        return None

    ck = f"chart_{sym}_{range_key}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    period, interval = CHART_RANGE_CONFIG[range_key]
    alt = CHART_RANGE_FALLBACK.get(range_key)

    def _pull(p: str, iv: str) -> pd.DataFrame | None:
        try:
            t = yf.Ticker(sym)
            df = t.history(period=p, interval=iv, auto_adjust=True)
            if df is None or df.empty or "Close" not in df.columns:
                return None
            return df
        except Exception:
            return None

    hist = _pull(period, interval)
    if hist is None and alt:
        hist = _pull(alt[0], alt[1])
    if hist is None:
        return None

    s = hist["Close"].dropna()
    if s.empty:
        return None

    labels: list[str] = []
    closes: list[float | None] = []
    for ts, val in s.items():
        ts_pd = pd.Timestamp(ts)
        if range_key == "1d":
            labels.append(ts_pd.strftime("%H:%M"))
        elif range_key == "1w":
            labels.append(ts_pd.strftime("%m/%d %H:%M"))
        else:
            labels.append(ts_pd.strftime("%Y-%m-%d"))
        closes.append(_safe_float(val))

    out: dict[str, Any] = {
        "symbol": sym,
        "range": range_key,
        "labels": labels,
        "closes": closes,
    }
    _cache_set(ck, out, ttl=45.0)
    return out


def fetch_quotes_for_symbols(symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in symbols:
        q = fetch_quote(s)
        if q:
            out.append(q)
    return out


def fetch_ticker_news(symbol: str, limit: int = 14) -> list[dict[str, Any]]:
    """Recent Yahoo Finance news items for a single symbol (best-effort)."""
    sym = symbol.strip().upper().replace(" ", "")
    if not sym:
        return []
    ck = f"tnews_v2_{sym}_{limit}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    out: list[dict[str, Any]] = []
    try:
        t = yf.Ticker(sym)
        items = getattr(t, "news", None) or []
        for n in items[:limit]:
            if not isinstance(n, dict):
                continue
            flat = _flatten_yahoo_news_item(n)
            if not flat:
                continue
            pub_u, pub_iso = _published_unix_iso(flat.get("providerPublishTime"))
            out.append(
                {
                    "title": flat.get("title") or "",
                    "publisher": flat.get("publisher") or "",
                    "link": flat.get("link") or "",
                    "published": pub_u,
                    "published_at": pub_iso,
                }
            )
    except Exception:
        pass

    _cache_set(ck, out)
    return out


def _ticker_sector_industry(sym: str) -> str:
    try:
        inf = yf.Ticker(sym).info
        sec = (inf.get("sector") or "").strip()
        ind = (inf.get("industry") or "").strip()
        parts = [p for p in (sec, ind) if p]
        return " — ".join(parts) if parts else ""
    except Exception:
        return ""


def build_ticker_overview_context(
    symbol: str,
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """Text bundle for LLM plus headline list for UI: quote, optional sector, news."""
    q = fetch_quote(symbol)
    if not q:
        return None, "Quote unavailable for that symbol.", []
    sym = q["symbol"]
    news = fetch_ticker_news(sym, 14)
    lines: list[str] = [
        f"Ticker: {sym} — {q.get('name')}",
        f"Approx last price: {q.get('price')}; approx day change %: {q.get('change_pct')}",
        f"Approx volume: {q.get('volume')}; approx market cap: {q.get('market_cap')}",
    ]
    si = _ticker_sector_industry(sym)
    if si:
        lines.append(f"Sector / industry (may be incomplete): {si}")
    lines.append("Recent Yahoo Finance headlines (may be delayed):")
    if not news:
        lines.append("(No headlines returned for this symbol.)")
    else:
        for item in news:
            pub = item.get("publisher") or ""
            lines.append(f"- {item.get('title')} [{pub}]")
    return "\n".join(lines), None, news


def build_ai_context_snapshot() -> str:
    """Compact text for LLM context from current Yahoo snapshots."""
    lines: list[str] = []
    try:
        for idx in fetch_indexes():
            nm = idx.get("name") or idx.get("symbol")
            lines.append(
                f"Index {nm} ({idx.get('symbol')}): last {idx.get('price')}, "
                f"change approx {idx.get('change_pct')} %"
            )
        up, dn = fetch_movers()
        lines.append("Top gainers (sample universe):")
        for r in up[:6]:
            sym = r.get("symbol")
            cp = r.get("change_pct")
            lines.append(f"  {sym} {cp:.2f} %" if cp is not None else f"  {sym}")
        lines.append("Top losers (sample universe):")
        for r in dn[:6]:
            sym = r.get("symbol")
            cp = r.get("change_pct")
            lines.append(f"  {sym} {cp:.2f} %" if cp is not None else f"  {sym}")
        news_items = fetch_market_news(16)
        lines.append("Recent market headlines (Yahoo Finance; may be delayed):")
        if news_items:
            lines.append(format_market_news_for_ai(news_items, 14))
        else:
            lines.append("(No headlines returned.)")
    except Exception:
        lines.append("(Partial market data unavailable.)")
    return "\n".join(lines)
