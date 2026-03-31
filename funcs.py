import sqlite3, os, json
from pathlib import Path
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np
from contextlib import closing
from colorama import Fore, Style
from openai import OpenAI
import os, time, math, json, textwrap, requests
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv
import feedparser

from textwrap import fill

OPENAI_MODEL = "gpt-4o-mini"

# Getting the database path and store in DIR (may want to change depending on user) 
DATA_DIR = Path.home() / "Projects/ProfitPlug/.DB"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "portfolio.db"

# get the db path
def get_db_path() -> Path:
    return DB_PATH

# ================================================================================
# stock price related functions
def last_price(symbol):
    try:
        px = yf.Ticker(symbol).history(period="1d", interval="1m")["Close"].dropna() # get the close price at the end of each minute
        if len(px) == 0:
            px = yf.Ticker(symbol).history(period="5d")["Close"].dropna() # if there is no daily data it grabs the most recent 5 days
        return float(px.iloc[-1]) if len(px) else None
    except Exception:
        return None

def hist_close(symbol, days=200):
    try:
        return yf.Ticker(symbol).history(period=f"{max(days,60)}d")["Close"].dropna() # get the close price of the last minimun 60 days
    except Exception:
        return pd.Series(dtype=float)

def rsi(series, n=14):
    if len(series) < n+1: return np.nan
    delta = series.diff() # change in price

    up = np.where(delta>0, delta, 0.0)
    down = np.where(delta<0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(n).mean() # calculate the mean of the rise
    roll_down = pd.Series(down, index=series.index).rolling(n).mean()

    rs = roll_up / (roll_down + 1e-9) # avoid dividing by 0
    return 100 - (100/(1+rs)).iloc[-1] # get as a percentage

def sma(series, n):
    if len(series) < n: return np.nan
    return series.rolling(n).mean().iloc[-1] # get the mean of the series and then grab the last one

def pnl_emoji(price: float, avg_cost: float, tol: float = 0.002) -> str:
    """
    Return an emoji for rise/dip based on % change vs avg_cost.
    tol = 0.2% band treated as 'flat' to avoid flicker.
    """
    if avg_cost == 0 or price is None:
        return "➖"
    chg = (price - avg_cost) / avg_cost
    if chg > tol:
        return "📈"
    if chg < -tol:
        return "📉"
    return "➖"


def fetch_rss_items(feeds: List[str], per_feed: int = 5) -> List[Dict[str, Any]]:
    """Grab a few recent items from public RSS feeds (no key needed)."""
    items = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for e in (f.entries or [])[:per_feed]:
                items.append({
                    "source": f.feed.get("title", url),
                    "title": (e.title or "").strip(),
                    "published": e.get("published", "") or e.get("updated", ""),
                    "link": e.get("link", ""),
                })
        except Exception:
            continue
    # rough sort by published text if present
    items = [it for it in items if it.get("title")]
    return items[: min(30, len(items))]

def fetch_macro_headlines() -> List[Dict[str, Any]]:
    """Macro-focused sources: CPI, jobs, Fed, BEA."""
    feeds = [
        "https://www.bls.gov/feeds/news_release/cpi.rss",       # CPI
        "https://www.bls.gov/feeds/news_release/empsit.rss",    # Employment Situation
        "https://www.federalreserve.gov/feeds/press_monetary.xml",  # FOMC
        "https://www.bea.gov/news/rss.xml",                     # BEA newsroom (PCE/Personal Income often here)
    ]
    return fetch_rss_items(feeds, per_feed=5)

def summarize_with_openai(payload: Dict[str, Any]) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system = (
        "You are a professional sell-side macro/quant analyst. "
        "Write a concise daily note with:\n"
        "1) Market overview (trend/risk tone)\n"
        "2) Inflation & rates lens from provided headlines\n"
        "3) Likely impacted sectors/tickers (brief rationale)\n"
        "4) What a typical long-only retail buyer *might* consider (general, non-advice)\n"
        "Keep it ~250-350 words. Be specific but measured. Include a short watchlist."
    )
    user = (
        "Facts:\n" +
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) +
        "\n\nConstraints: Do not give personalized advice. State uncertainties. Prefer scenarios/probabilities."
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
    )
    return resp.choices[0].message.content.strip()

def _safe_unix_to_iso(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""



def fetch_news(symbols, per_sym: int = 5):
    """yfinance news with Yahoo RSS fallback to avoid empty headlines."""
    items = []
    seen = set()

    # primary: yfinance
    for s in symbols:
        try:
            for it in (yf.Ticker(s).news or []):
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                key = (title, it.get("link"))
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "symbol": s,
                    "title": title,
                    "publisher": (it.get("publisher") or "").strip(),
                    "time": _safe_unix_to_iso(it.get("providerPublishTime")),
                    "link": it.get("link","")
                })
        except Exception:
            continue

    # fallback: Yahoo Finance RSS (guarantees some headlines for big names)
    if not items:
        for s in symbols:
            try:
                rss = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={s}&region=US&lang=en-US"
                feed = feedparser.parse(rss)
                for e in (feed.entries or [])[:per_sym]:
                    title = (getattr(e, "title", "") or "").strip()
                    if not title:
                        continue
                    key = (title, getattr(e, "link", ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append({
                        "symbol": s,
                        "title": title,
                        "publisher": feed.feed.get("title","Yahoo Finance"),
                        "time": getattr(e, "published", ""),
                        "link": getattr(e, "link", "")
                    })
            except Exception:
                continue

    # keep newest-ish first
    def _score(x):
        t = x.get("time") or ""
        try:
            return datetime.strptime(t, "%Y-%m-%d %H:%M").timestamp()
        except Exception:
            return 0
    items.sort(key=_score, reverse=True)
    return items[: max(1, per_sym*len(symbols))]


# ================================================================================
# database set up
DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  cash REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
  account_id INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  shares INTEGER NOT NULL,
  avg_cost REAL NOT NULL,
  PRIMARY KEY (account_id, symbol),
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  time TEXT NOT NULL,
  action TEXT NOT NULL,   -- BUY/SELL
  symbol TEXT NOT NULL,
  shares INTEGER NOT NULL,
  price REAL NOT NULL,
  total REAL NOT NULL,
  realized_pnl REAL,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  time TEXT NOT NULL,
  equity REAL NOT NULL,
  cash REAL NOT NULL,
  positions_json TEXT NOT NULL,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(starting_cash=100_000.0, account_name="Main"):
    with closing(get_conn()) as conn, conn:
        for stmt in DDL.strip().split(";\n\n"):
            if stmt.strip():
                conn.executescript(stmt + ";")
        # Ensure an account exists
        cur = conn.execute("SELECT id FROM accounts WHERE name=?", (account_name,))
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO accounts (name, cash, created_at) VALUES (?, ?, ?)",
                (account_name, float(starting_cash), datetime.now().isoformat())
            )
        # Return account id
        acc_id = conn.execute("SELECT id FROM accounts WHERE name=?", (account_name,)).fetchone()["id"]
        return acc_id

def create_account(account_name: str, starting_cash=1_000_000.0):
    name = (account_name or "").strip()
    if not name:
        print("✖ Account name cannot be empty.")
        return None

    with closing(get_conn()) as conn, conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE lower(name)=lower(?)",
            (name,)
        ).fetchone()

        if row is not None:
            print(f"✖ Account '{name}' already exists.")
            return None

        conn.execute(
            "INSERT INTO accounts (name, cash, created_at) VALUES (?, ?, ?)",
            (name, float(starting_cash), datetime.now().isoformat())
        )

        acc_id = conn.execute(
            "SELECT id FROM accounts WHERE lower(name)=lower(?)",
            (name,)
        ).fetchone()["id"]

    print(f"✓ Created account '{name}' with ${starting_cash:,.2f}")
    return acc_id


def list_accounts():
    with closing(get_conn()) as conn:
        rows = conn.execute("""
            SELECT
                a.id,
                a.name,
                a.cash,
                a.created_at,
                COUNT(p.symbol) AS positions
            FROM accounts a
            LEFT JOIN positions p ON a.id = p.account_id
            GROUP BY a.id, a.name, a.cash, a.created_at
            ORDER BY a.name
        """).fetchall()

    print("\n--- Accounts ---")
    if not rows:
        print("(no accounts)")
        return

    for r in rows:
        print(
            f"[{r['id']}] {r['name']} | "
            f"Cash: ${float(r['cash']):,.2f} | "
            f"Positions: {r['positions']} | "
            f"Created: {r['created_at'][:19]}"
        )


def get_account_id_by_name(account_name: str):
    name = (account_name or "").strip()
    if not name:
        return None

    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE lower(name)=lower(?)",
            (name,)
        ).fetchone()

    return None if row is None else row["id"]


def show_active_account(account_id: int):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT id, name, cash, created_at FROM accounts WHERE id=?",
            (account_id,)
        ).fetchone()

    if row is None:
        print("✖ Active account not found.")
        return

    print(
        f"\nActive Account: [{row['id']}] {row['name']} | "
        f"Cash: ${float(row['cash']):,.2f}"
    )


def delete_account(account_name: str):
    name = (account_name or "").strip()
    if not name:
        print("✖ Account name cannot be empty.")
        return False

    with closing(get_conn()) as conn, conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE lower(name)=lower(?)",
            (name,)
        ).fetchone()

        if row is None:
            print(f"✖ Account '{name}' not found.")
            return False

        conn.execute("DELETE FROM positions WHERE account_id=?", (row["id"],))
        conn.execute("DELETE FROM trades WHERE account_id=?", (row["id"],))
        conn.execute("DELETE FROM snapshots WHERE account_id=?", (row["id"],))
        conn.execute("DELETE FROM accounts WHERE id=?", (row["id"],))

    print(f"✓ Deleted account '{name}'.")
    return True
# ================================================================================
# account engine
class PaperAccount:
    def __init__(self, account_id: int):
        self.account_id = account_id #initialize a user with database id


    # get user cash
    def _get_cash(self, conn):
        return float(conn.execute("SELECT cash FROM accounts WHERE id=?", (self.account_id,)).fetchone()["cash"])


    # set user cash 
    def _set_cash(self, conn, cash: float):
        conn.execute("UPDATE accounts SET cash=? WHERE id=?", (float(cash), self.account_id))


    def equity(self):
        with closing(get_conn()) as conn:
            cash = self._get_cash(conn)
            pv = 0.0
            for row in conn.execute("SELECT symbol, shares FROM positions WHERE account_id=?", (self.account_id,)):
                px = last_price(row["symbol"])
                if px: pv += row["shares"] * px
            return cash + pv


    def buy(self, sym, shares):
        sym = sym.upper()
        with closing(get_conn()) as conn, conn:
            price = last_price(sym)
            if price is None:
                print("✖ Couldn't fetch price."); return
            cost = price * shares
            cash = self._get_cash(conn)
            if cost > cash + 1e-9:
                print("✖ Not enough cash."); return
            # update cash
            self._set_cash(conn, cash - cost)
            # upsert position
            row = conn.execute("SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                               (self.account_id, sym)).fetchone()
            if row:
                new_shares = row["shares"] + shares
                new_cost = (row["shares"]*row["avg_cost"] + cost) / new_shares
                conn.execute("UPDATE positions SET shares=?, avg_cost=? WHERE account_id=? AND symbol=?",
                             (new_shares, new_cost, self.account_id, sym))
            else:
                conn.execute("INSERT INTO positions (account_id, symbol, shares, avg_cost) VALUES (?, ?, ?, ?)",
                             (self.account_id, sym, shares, price))
            # log trade
            conn.execute("""INSERT INTO trades(account_id,time,action,symbol,shares,price,total,realized_pnl)
                            VALUES(?,?,?,?,?,?,?,NULL)""",
                         (self.account_id, datetime.now().isoformat(), "BUY", sym, shares, price, cost))
        print(f"✓ Bought {shares} {sym} @ ${price:.2f}")


    def sell(self, sym, shares):
        sym = sym.upper()
        with closing(get_conn()) as conn, conn:
            pos = conn.execute("SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                               (self.account_id, sym)).fetchone()
            if not pos or pos["shares"] < shares:
                print("✖ Not enough shares."); return
            price = last_price(sym)
            if price is None:
                print("✖ Couldn't fetch price."); return
            revenue = price * shares
            realized = (price - pos["avg_cost"]) * shares
            # update cash
            cash = self._get_cash(conn)
            self._set_cash(conn, cash + revenue)
            # update position
            new_shares = pos["shares"] - shares
            if new_shares == 0:
                conn.execute("DELETE FROM positions WHERE account_id=? AND symbol=?", (self.account_id, sym))
            else:
                conn.execute("UPDATE positions SET shares=? WHERE account_id=? AND symbol=?",
                             (new_shares, self.account_id, sym))
            # log trade
            conn.execute("""INSERT INTO trades(account_id,time,action,symbol,shares,price,total,realized_pnl)
                            VALUES(?,?,?,?,?,?,?,?)""",
                         (self.account_id, datetime.now().isoformat(), "SELL", sym, shares, price, revenue, realized))
        print(f"✓ Sold {shares} {sym} @ ${price:.2f}  (Realized P/L: ${realized:.2f})")


    def portfolio(self):
        with closing(get_conn()) as conn:
            rows = []
            for r in conn.execute(
                "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=? ORDER BY symbol",
                (self.account_id,)
            ):
                px = last_price(r["symbol"])
                if px is None:
                    continue
                mv = px * r["shares"]
                u_pnl = (px - r["avg_cost"]) * r["shares"]
                emo = pnl_emoji(px, r["avg_cost"])
                rows.append([r["symbol"], emo, r["shares"], r["avg_cost"], px, mv, u_pnl])

            df = pd.DataFrame(
                rows,
                columns=["Symbol", "Δ", "Shares", "Avg Cost", "Price", "Mkt Value", "Unrealized P/L"]
            )
            cash = self._get_cash(conn)

        eq = self.equity()
        print(f"\n--- {Fore.LIGHTBLUE_EX}Portfolio{Style.RESET_ALL} ---")
        if df.empty:
            print("(no positions)")
        else:
            print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
        print(f"Cash: ${cash:,.2f}   Equity: ${eq:,.2f}")


    def history(self):
        with closing(get_conn()) as conn:
            df = pd.read_sql_query(
                "SELECT time, action, symbol, shares, price, total, realized_pnl FROM trades "
                "WHERE account_id=? ORDER BY time", conn, params=(self.account_id,))
        print("\n--- Trade History ---")
        if df.empty: print("(no trades)")
        else: print(df.to_string(index=False))

    def reset(self, starting_cash=1_000_000.0):
        with closing(get_conn()) as conn, conn:
            conn.execute("DELETE FROM positions WHERE account_id=?", (self.account_id,))
            conn.execute("DELETE FROM trades WHERE account_id=?", (self.account_id,))
            conn.execute("UPDATE accounts SET cash=? WHERE id=?", (float(starting_cash), self.account_id))
        print("↺ Reset account.")

    def snapshot_on_exit(self):
        # Save an equity snapshot for performance tracking
        with closing(get_conn()) as conn, conn:
            # capture current positions as JSON
            pos = conn.execute(
                "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=?", (self.account_id,)
            ).fetchall()
            pos_json = json.dumps([dict(r) for r in pos])
            cash = self._get_cash(conn)
            equity = self.equity()  # includes live prices
            conn.execute("""INSERT INTO snapshots(account_id,time,equity,cash,positions_json)
                            VALUES(?,?,?,?,?)""",
                         (self.account_id, datetime.now().isoformat(), float(equity), float(cash), pos_json))

# ----------------- “AI” market snapshot -----------------
def analyze_market():
    # 1) Technical snapshot
    symbols = ["SPY","QQQ","IWM","TLT","DX=F","^VIX"]
    info = {}
    for s in symbols:
        h = hist_close(s, 200)
        if h.empty:
            continue
        p = float(h.iloc[-1]); s20 = sma(h,20); s50 = sma(h,50); s200 = sma(h,200); r = rsi(h,14)
        trend = ("UP" if (not np.isnan(s50) and p > s50) else ("DOWN" if not np.isnan(s50) else "—"))
        cross = "bullish" if (not np.isnan(s20) and not np.isnan(s50) and s20 > s50) else ("bearish" if (not np.isnan(s20) and not np.isnan(s50) and s20 < s50) else "flat")
        info[s] = {
            "price": round(p,2),
            "rsi": None if np.isnan(r) else round(float(r),1),
            "trend": trend,
            "cross": cross,
            "sma20": None if np.isnan(s20) else round(float(s20),2),
            "sma50": None if np.isnan(s50) else round(float(s50),2),
            "sma200": None if np.isnan(s200) else round(float(s200),2),
        }

    # 2) Micro headlines via yfinance
    equity_news = fetch_news(["SPY","QQQ","AAPL","NVDA","MSFT","TLT"], per_sym=4)

    # 3) Macro headlines via public RSS (no key)
    macro_news = fetch_macro_headlines()

    # 4) Build payload and ask OpenAI for the note
    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "technicals": info,
        "equity_headlines": equity_news,
        "macro_headlines": macro_news
    }

    try:
        note = summarize_with_openai(payload)
    except Exception as e:
        note = f"(AI summary unavailable: {e})"

    # 5) Print snapshot + AI note
    def line(sym,name):
        d = info.get(sym)
        if not d:
            return f"{name}: (no data)"
        rsi_txt = "" if d["rsi"] is None else f" | RSI {d['rsi']:.0f}"
        return f"{name}: {d['trend']} | 20/50 {d['cross']}{rsi_txt} | Px {d['price']:.2f}"

    print("\n=== Market Snapshot ===")
    print(line("SPY","S&P 500")); print(line("QQQ","Nasdaq 100")); print(line("IWM","Russell 2000"))
    print(line("TLT","Long Bonds")); print(line("DXY","US Dollar")); print(line("^VIX","VIX"))

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

def get_next_earnings(sym: str) -> str:
    """Best-effort next earnings date using multiple yfinance paths."""
    tk = yf.Ticker(sym)
    # 1) Preferred: get_earnings_dates (new API)
    try:
        ed = tk.get_earnings_dates(limit=8)  # DataFrame with DatetimeIndex
        if ed is not None and not ed.empty:
            today = pd.Timestamp.today().normalize()
            future = ed[ed.index.normalize() >= today]
            if not future.empty:
                return future.index[0].strftime("%Y-%m-%d")
            # otherwise last known past date
            return ed.index[-1].strftime("%Y-%m-%d") + " (last)"
    except Exception:
        pass

    # 2) Older calendar path
    try:
        cal = tk.get_calendar()
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"].iloc[0]
                return str(val)
            if "Earnings Date" in cal.columns:
                val = cal["Earnings Date"].iloc[0]
                return str(val)
    except Exception:
        pass

    # 3) Nothing found
    return "-"


def info(topic: str | None = None):
    """
    Print concise explanations for common market concepts your app uses.
    Usage:
      info list        -> show available topics
      info all         -> print everything
      info rsi         -> one topic (case-insensitive, aliases allowed)
      info "moving average"
    """

    TOPICS = {
        "index": """
An index is a basket that tracks a part of the market (not directly tradable).
Examples: S&P 500 (^GSPC), Nasdaq-100 (^NDX), Russell 2000 (^RUT).
You can get exposure via ETFs like SPY (tracks S&P500) or QQQ (tracks Nasdaq-100).
Indexes are used to benchmark performance and gauge “risk-on/off” tone.
""",
        "etf": """
An ETF (Exchange-Traded Fund) holds a portfolio (stocks/bonds/commodities) and trades like a stock.
Pros: diversified, intraday liquidity, usually low fees. Cons: tracking error, expense ratios.
Examples: SPY (S&P 500), QQQ (Nasdaq-100), TLT (20+yr Treasuries), UUP (US Dollar).
Avoid long-term holding of leveraged/inverse ETFs unless you understand compounding/decay.
""",
        "rsi": """
RSI (Relative Strength Index) is a momentum oscillator 0–100.
Rules of thumb: >70 = overbought, <30 = oversold. 40–60 = neutral.
Trend regimes shift bands (strong uptrends often bottom near 40–50 RSI; downtrends top near 50–60).
Use RSI with context (trend, support/resistance). On daily charts, 14-period is common.
""",
        "sma_ema": """
Moving Averages: SMA is a simple average; EMA weights recent prices more.
Common windows: 20 (short), 50 (medium), 200 (long). Price above 50/200 = uptrend bias; below = downtrend bias.
Use MAs to identify trend, dynamic support/resistance, and for crossover signals.
""",
        "crossovers": """
Crossovers:
• Golden Cross: 50-day MA crossing above 200-day MA (long-term bullish).
• Death Cross: 50-day crossing below 200-day (bearish).
Shorter crosses (20/50) catch turns sooner but produce more whipsaws. Confirm with volume, RSI, or price structure.
""",
        "vix": """
VIX measures implied volatility of S&P 500 options (“fear gauge”).
Low VIX (<15–18) = calm; high VIX (>25) = stress. Risk assets often struggle when VIX spikes.
You can’t buy VIX directly; ETPs exist but have roll/decay risks.
""",
        "tlt": """
TLT is an ETF of 20+ year US Treasuries (long duration). When yields rise, TLT usually falls, and vice versa.
TLT is sensitive to inflation expectations and Fed path. Useful risk-off hedge in some regimes; not guaranteed.
""",
        "dxy": """
DXY is the US Dollar Index (USD vs a basket). On Yahoo use 'DX=F' (Dollar Index futures) or ETF 'UUP'.
A stronger dollar can pressure US multinationals’ earnings and many commodities (often priced in USD).
""",
        "macro_events": """
Key macro:
• CPI/PCE inflation prints → move rates, TLT, growth vs value.
• Jobs/Unemployment → growth outlook, Fed path.
• FOMC (Fed) decisions/guidance → rates, equities’ multiples, USD.
• ISM/PMI → manufacturing/services health.
Stronger inflation = higher rates → duration (TLT) down, USD up typically; weaker inflation = opposite.
""",
        "pe_eps": """
P/E and EPS:
• EPS (Earnings Per Share) is company profit per share (ttm = last 12 months).
• P/E = Price / EPS. Higher P/E = paying more for each $ of earnings (often growthy), lower P/E = cheaper (maybe riskier or slower growth).
Compare P/E to peers, history, and rates (higher rates compress P/E).
""",
        "beta_vol": """
Beta & Volatility:
• Beta ~ sensitivity to market moves (>1 more volatile than market, <1 less).
• Volatility is the size of typical price swings. Higher vol → wider stops/position sizing.
""",
        "market_cap": """
Market cap = share price × shares outstanding.
Buckets (rough): Micro < $300M, Small $300M–$2B, Mid $2B–$10B, Large $10B–$200B, Mega > $200B.
Size impacts liquidity, stability, and risk profile.
""",
        "earnings": """
Earnings:
Companies report quarterly. Markets react to results vs expectations and guidance.
Catalysts: EPS/Revenue beats/misses, margin commentary, buybacks, outlook.
Volatility around earnings is normal; sizing and risk controls matter.
""",
        "support_resistance": """
Support/Resistance:
Support = price area where demand often steps in; Resistance = where supply often sells.
Look for prior swing highs/lows, moving averages, gaps, anchored VWAPs. Use multiple timeframes for confluence.
""",
        "position_sizing": """
Position sizing (general info, not advice):
Small increments (e.g., 1–5% of portfolio) help manage risk.
Volatile names often deserve smaller sizes. Avoid doubling down blindly; plan adds/cuts in advance.
""",
        "stops": """
Stops (general info, not advice):
Common approaches: % stop (e.g., -5%), structure stop (below support), ATR-based (e.g., 1.5–2× ATR).
Always consider your max loss per trade and portfolio drawdown tolerance.
""",
        "risk_on_off": """
Risk ON vs OFF (quick read):
• Risk ON: SPY/QQQ above 50/200 MAs, VIX tame (<~18), credit spreads narrowing.
• Risk OFF: Opposite conditions; defensive sectors and long duration may outperform.
Treat as a spectrum; signals can conflict.
""",
        "tickers": """
Useful Yahoo symbols in this app:
• SPY (S&P 500 ETF), QQQ (Nasdaq-100 ETF), IWM (Russell 2000 ETF)
• TLT (20+yr Treasuries ETF), ^VIX (VIX index), DX=F (Dollar Index futures)
Indices to know: ^GSPC (S&P 500), ^NDX (Nasdaq-100), ^RUT (Russell 2000).
""",
        "rules_of_thumb": """
Rules of thumb (not advice):
• RSI: >70 overheated, <30 washed out; in trends, use 40/60 bands.
• Trend bias: price above 50/200-day → bullish tilt; below → bearish tilt.
• Crossovers: golden/death crosses warn of regime shifts; confirm elsewhere.
• Macro days (CPI/FOMC/payrolls): expect wider ranges; use smaller size or wait.
"""
    }

    ALIASES = {
        "indices": "index",
        "what is an index": "index",
        "etfs": "etf",
        "ma": "sma_ema",
        "sma": "sma_ema",
        "ema": "sma_ema",
        "moving average": "sma_ema",
        "golden cross": "crossovers",
        "death cross": "crossovers",
        "usd": "dxy",
        "dxy": "dxy",
        "dollar": "dxy",
        "macro": "macro_events",
        "pe": "pe_eps",
        "eps": "pe_eps",
        "beta": "beta_vol",
        "volatility": "beta_vol",
        "mkt cap": "market_cap",
        "market cap": "market_cap",
        "sr": "support_resistance",
        "support": "support_resistance",
        "resistance": "support_resistance",
        "sizing": "position_sizing",
        "stops": "stops",
        "stop loss": "stops",
        "risk": "risk_on_off",
        "tickers": "tickers",
        "rules": "rules_of_thumb",
    }

    # --- add more concepts ---
    TOPICS.update({
        "bullish_bearish": """
    Bullish vs Bearish (quick criteria):
    • Bullish tilt: Price above 50/200-day MAs, higher-highs/higher-lows, breadth improving (% of stocks above 50dma rising),
    VIX subdued (<~18), credit spreads narrowing; cyclicals/growth leading.
    • Bearish tilt: Price below 50/200-day MAs, lower-highs/lower-lows, deteriorating breadth, VIX rising,
    credit spreads widening; defensives/value/long-duration leading.
    Notes: Regimes can flip quickly around catalysts (CPI/FOMC/earnings). Treat signals as a *cluster*, not a single trigger.
    """,
        "breakouts_pullbacks": """
    Breakouts & Pullbacks:
    • Breakout: Price pushes through a well-watched resistance (prior high/MA/level) on expanding volume. Risk: false break/whipsaw.
    • Pullback: Brief drop within an uptrend toward support (prior breakout area, rising 20/50dma), then buyers step in.
    Tips (general info, not advice): Look for confluence (trend + volume + RSI regime). Define invalidation (where you're wrong).
    Avoid chasing far-from-support moves; wait for retests when possible.
    """,
        "trend_structure": """
    Trend Structure (HH/HL vs LH/LL):
    • Uptrend: Higher Highs (HH) and Higher Lows (HL). Dips often bought near rising MAs or prior swing highs.
    • Downtrend: Lower Highs (LH) and Lower Lows (LL). Rallies often sold near falling MAs or prior swing lows.
    Confirm on multiple timeframes (daily/weekly). A single lower low doesn’t always kill an uptrend—watch the sequence.
    """
    })

    ALIASES.update({
        "bullish": "bullish_bearish",
        "bearish": "bullish_bearish",
        "bias": "bullish_bearish",
        "breakout": "breakouts_pullbacks",
        "breakdowns": "breakouts_pullbacks",
        "pullback": "breakouts_pullbacks",
        "trend": "trend_structure",
        "structure": "trend_structure",
        "hhhl": "trend_structure",
        "lhll": "trend_structure",
    })


    def _wrap(txt: str, width: int = 110) -> str:
        return "\n".join(fill(line, width=width) if line.strip() else "" for line in txt.strip("\n").splitlines())

    # Normalize input
    key = (topic or "").strip().lower()

    if key in ("", "list", "topics", "help"):
        print(f"\n--- {Fore.LIGHTBLUE_EX}Info Topics{Style.RESET_ALL} ---")
        cols = sorted(TOPICS.keys())
        print(", ".join(cols))
        print("\nTip: info rsi | info 'moving average' | info macro | info all")
        return

    if key == "all":
        print(f"\n--- {Fore.LIGHTBLUE_EX}Market Concepts Cheat Sheet{Style.RESET_ALL} ---")
        for k in TOPICS:
            print(f"\n{Fore.LIGHTYELLOW_EX}{k}{Style.RESET_ALL}")
            print(_wrap(TOPICS[k]))
        print("\n(General information only; not investment advice.)")
        return

    # Resolve alias → canonical key, or best-effort partial match
    key = ALIASES.get(key, key)
    if key not in TOPICS:
        # partial match
        matches = [k for k in TOPICS if key in k]
        if matches:
            key = matches[0]
        else:
            print(f"✖ Unknown topic '{topic}'. Try: info list")
            return

    print(f"\n--- {Fore.LIGHTBLUE_EX}{key}{Style.RESET_ALL} ---")
    print(_wrap(TOPICS[key]))
    print("\n(General information only; not investment advice.)")

def _fmt_num(x):
    try:
        x = float(x)
    except Exception:
        return "-"
    absx = abs(x)
    if absx >= 1e12: return f"{x/1e12:.2f}T"
    if absx >= 1e9:  return f"{x/1e9:.2f}B"
    if absx >= 1e6:  return f"{x/1e6:.2f}M"
    if absx >= 1e3:  return f"{x/1e3:.2f}K"
    return f"{x:.2f}"

def _safe(val, default="-"):
    return default if val in (None, "", float("nan")) else val

def ai_connections_lookup(symbol: str, info: dict) -> dict:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    company_name = info.get("longName") or symbol
    sector = info.get("sector") or "Unknown"
    industry = info.get("industry") or "Unknown"
    country = info.get("country") or "Unknown"
    summary = info.get("longBusinessSummary") or ""

    system = (
        "You are a financial research assistant. "
        "Return likely business relationship data for a public company. "
        "Focus on broad real-world business relationships, not made-up specifics. "
        "Return only valid JSON with this exact schema: "
        "{"
        "\"suppliers\": [\"...\"], "
        "\"customers\": [\"...\"], "
        "\"peers\": [\"...\"], "
        "\"notes\": \"...\""
        "} "
        "Rules: "
        "1) Keep each list short, around 3 to 6 items. "
        "2) Use major known supplier groups, customer channels, or peers. "
        "3) If exact named customers are unclear, use categories like "
        "\"consumers\", \"enterprise customers\", \"wireless carriers\", or \"retail partners\". "
        "4) Do not include explanations outside the JSON."
    )

    user = (
        f"Ticker: {symbol}\n"
        f"Company: {company_name}\n"
        f"Sector: {sector}\n"
        f"Industry: {industry}\n"
        f"Country: {country}\n"
        f"Business summary: {summary}\n\n"
        "Give likely suppliers, customers, and peers for this company."
    )

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    raw = resp.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {
            "suppliers": [],
            "customers": [],
            "peers": [],
            "notes": "AI response could not be parsed."
        }

    for key in ("suppliers", "customers", "peers"):
        if key not in data or not isinstance(data[key], list):
            data[key] = []

    if "notes" not in data or not isinstance(data["notes"], str):
        data["notes"] = ""

    return data



    sym = stock.strip().upper()
    tk = yf.Ticker(sym)

    try:
        info = tk.get_info()
    except Exception:
        info = {}

    if not info:
        print(f"✖ Could not retrieve company data for '{sym}'.")
        return

    long_name = info.get("longName") or sym
    sector = info.get("sector") or "-"
    industry = info.get("industry") or "-"
    country = info.get("country") or "-"
    exchange = info.get("exchange") or "-"
    website = info.get("website") or "-"
    summary = info.get("longBusinessSummary") or ""

    def normalize_list(val):
        if val is None:
            return []
        if isinstance(val, list):
            out = []
            for x in val:
                if isinstance(x, dict):
                    name = x.get("name") or x.get("symbol") or str(x)
                    out.append(str(name))
                else:
                    out.append(str(x))
            return [x.strip() for x in out if str(x).strip()]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return [str(val).strip()]

    suppliers = []
    customers = []
    peers = []

    for key in ["suppliers", "majorSuppliers", "supplyChainSuppliers"]:
        if key in info:
            suppliers.extend(normalize_list(info.get(key)))

    for key in ["customers", "majorCustomers", "supplyChainCustomers"]:
        if key in info:
            customers.extend(normalize_list(info.get(key)))

    for key in ["peerGroup", "peers", "relatedCompanies"]:
        if key in info:
            peers.extend(normalize_list(info.get(key)))

    def unique_keep_order(items):
        seen = set()
        out = []
        for item in items:
            low = item.lower()
            if low not in seen:
                seen.add(low)
                out.append(item)
        return out

    suppliers = unique_keep_order(suppliers)
    customers = unique_keep_order(customers)
    peers = unique_keep_order(peers)

    ai_note = ""
    used_ai = False

    if not suppliers and not customers and not peers:
        try:
            ai_data = ai_connections_lookup(sym, info)
            suppliers = unique_keep_order(ai_data.get("suppliers", []))
            customers = unique_keep_order(ai_data.get("customers", []))
            peers = unique_keep_order(ai_data.get("peers", []))
            ai_note = ai_data.get("notes", "")
            used_ai = True
        except Exception as e:
            ai_note = f"AI lookup unavailable: {e}"

    print(f"\n--- {Fore.LIGHTBLUE_EX}Connections{Style.RESET_ALL} for {long_name} ({sym}) ---")
    print(f"Sector: {sector}")
    print(f"Industry: {industry}")
    print(f"Country: {country}")
    print(f"Exchange: {exchange}")
    print(f"Website: {website}")

    if summary:
        print("\nBusiness Summary:")
        print(fill(summary, width=110))

    print("\nSuppliers:")
    if suppliers:
        for s in suppliers:
            print(f"  • {s}")
    else:
        print("  (No supplier data available)")

    print("\nCustomers:")
    if customers:
        for c in customers:
            print(f"  • {c}")
    else:
        print("  (No customer data available)")

    print("\nPeers:")
    if peers:
        for p in peers:
            print(f"  • {p}")
    else:
        print("  (No peer data available)")

    if ai_note:
        print("\nNotes:")
        print(fill(ai_note, width=110))

    if used_ai:
        print("\nSource: OpenAI generated relationship summary from company context.")
    else:
        print("\nSource: Direct market data fields.")

def connections(stock: str):
    sym = stock.strip().upper()
    tk = yf.Ticker(sym)

    try:
        info = tk.get_info()
    except Exception:
        info = {}

    if not info:
        print(f"✖ Could not retrieve company data for '{sym}'.")
        return

    long_name = info.get("longName") or sym

    def normalize_list(val):
        if val is None:
            return []
        if isinstance(val, list):
            out = []
            for x in val:
                if isinstance(x, dict):
                    name = x.get("name") or x.get("symbol") or str(x)
                    out.append(str(name))
                else:
                    out.append(str(x))
            return [x.strip() for x in out if str(x).strip()]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return [str(val).strip()]

    suppliers = []
    customers = []
    peers = []

    for key in ["suppliers", "majorSuppliers", "supplyChainSuppliers"]:
        if key in info:
            suppliers.extend(normalize_list(info.get(key)))

    for key in ["customers", "majorCustomers", "supplyChainCustomers"]:
        if key in info:
            customers.extend(normalize_list(info.get(key)))

    for key in ["peerGroup", "peers", "relatedCompanies"]:
        if key in info:
            peers.extend(normalize_list(info.get(key)))

    def unique_keep_order(items):
        seen = set()
        out = []
        for item in items:
            low = item.lower()
            if low not in seen:
                seen.add(low)
                out.append(item)
        return out

    suppliers = unique_keep_order(suppliers)
    customers = unique_keep_order(customers)
    peers = unique_keep_order(peers)

    ai_note = ""
    used_ai = False

    if not suppliers and not customers and not peers:
        try:
            ai_data = ai_connections_lookup(sym, info)
            suppliers = unique_keep_order(ai_data.get("suppliers", []))
            customers = unique_keep_order(ai_data.get("customers", []))
            peers = unique_keep_order(ai_data.get("peers", []))
            ai_note = ai_data.get("notes", "")
            used_ai = True
        except Exception as e:
            ai_note = f"AI lookup unavailable: {e}"

    print(f"\n=== CONNECTIONS: {long_name} ({sym}) ===")

    print("\nSUPPLIERS")
    if suppliers:
        for s in suppliers:
            print(f"- {s}")
    else:
        print("- No supplier data available")

    print("\nCUSTOMERS")
    if customers:
        for c in customers:
            print(f"- {c}")
    else:
        print("- No customer data available")

    print("\nPEERS")
    if peers:
        for p in peers:
            print(f"- {p}")
    else:
        print("- No peer data available")

    if ai_note:
        print("\nNOTES")
        print(fill(ai_note, width=110))

    if used_ai:
        print("\n[AI generated relationship summary]")
    else:
        print("\n[Direct source relationship data]")


def show(stock: str, headlines: int = 3):
    """
    Print a compact snapshot for a ticker:
      - Price, daily change, 52w range
      - Market cap, P/E, EPS (ttm), Beta
      - RSI(14), SMA 20/50/200
      - Next earnings date (if any)
      - Recent headlines
    """
    sym = stock.strip().upper()
    tk = yf.Ticker(sym)

    # --- core price / hist ---
    px = last_price(sym)
    hist = hist_close(sym, 250)

    if px is None and hist.empty:
        print(f"✖ No price data for '{sym}'. If this is an index, try its Yahoo symbol (e.g., 'DX=F' for US Dollar).")
        return

    # day change (use last two closes if available)
    day_chg = None
    if not hist.empty and len(hist) >= 2:
        prev = float(hist.iloc[-2])
        if prev != 0:
            day_chg = (px - prev) / prev * 100.0

    # 52w range
    lo52 = float(hist.min()) if not hist.empty else None
    hi52 = float(hist.max()) if not hist.empty else None

    # TA
    rsi14 = rsi(hist, 14)
    s20 = sma(hist, 20)
    s50 = sma(hist, 50)
    s200 = sma(hist, 200)

    # --- fundamentals / metadata ---
    try:
        info = tk.fast_info or {}
    except Exception:
        info = {}

    # fall back to .info (slower / may be deprecated) for some fields
    long_name = None
    pe = None
    eps = None
    beta = None
    sector = None
    try:
        i2 = tk.get_info()  # yfinance >= 0.2.40 provides .get_info()
        long_name = i2.get("longName")
        pe = i2.get("trailingPE") or i2.get("forwardPE")
        eps = i2.get("trailingEps")
        beta = i2.get("beta")
        sector = i2.get("sector")
    except Exception:
        pass

    mktcap = getattr(tk, "fast_info", {}).get("market_cap") if info else None
    currency = (info.get("currency") if info else None) or "USD"

    # next earnings
    next_earn = get_next_earnings(sym)

    # headlines
    news = fetch_news([sym], per_sym=headlines)

    # --- print ---
    name_display = long_name or sym
    print(f"\n--- {Fore.LIGHTBLUE_EX}{name_display}{Style.RESET_ALL} ({sym}) ---")
    price_line = f"Price: {currency} {px:.2f}" if px is not None else "Price: -"
    if day_chg is not None:
        arrow = "▲" if day_chg >= 0 else "▼"
        price_line += f"   {arrow} {day_chg:.2f}%"
    print(price_line)

    if lo52 is not None and hi52 is not None:
        print(f"52w:  {lo52:.2f}  –  {hi52:.2f}")

    print("\nFundamentals:")
    print(f"  Market Cap: {_fmt_num(mktcap)}")
    print(f"  P/E: {_safe(f'{pe:.2f}' if isinstance(pe,(int,float)) else pe)}   EPS (ttm): {_safe(f'{eps:.2f}' if isinstance(eps,(int,float)) else eps)}")
    print(f"  Beta: {_safe(f'{beta:.2f}' if isinstance(beta,(int,float)) else beta)}   Sector: {_safe(sector)}")

    print("\nTechnical:")
    def _fmt(v): 
        return "-" if (v is None or (isinstance(v,float) and np.isnan(v))) else f"{v:.2f}"
    print(f"  RSI(14): {_fmt(rsi14)}   SMA20: {_fmt(s20)}   SMA50: {_fmt(s50)}   SMA200: {_fmt(s200)}")

    print(f"\nNext earnings: {next_earn}")

    print("\nHeadlines:")
    if not news:
        print("  (none)")
    else:
        for n in news[:headlines]:
            title = n.get("title","").strip()
            pub = n.get("publisher","").strip()
            when = n.get("time","")
            if title:
                extra = (f" — {pub}" if pub else "") + (f" ({when})" if when else "")
                print(f"  • {title}{extra}")



# ================================================================================
# Help function
HELP = f"""
Commands:
  {Fore.LIGHTGREEN_EX}buy{Style.RESET_ALL}  TICKER SHARES       -> buy  (AAPL) 5
  {Fore.LIGHTRED_EX}sell{Style.RESET_ALL} TICKER SHARES       -> sell (MSFT) 2
  \033[38;5;208mshow\033[0m TICKER              -> get information pertaining to a Stock/Index
  connections TICKER       -> show suppliers, customers, and peers

  {Fore.LIGHTBLUE_EX}portfolio{Style.RESET_ALL}                -> show positions, P/L, cash, equity
  {Fore.LIGHTYELLOW_EX}history{Style.RESET_ALL}                  -> show trade history

  {Fore.LIGHTMAGENTA_EX}analyze{Style.RESET_ALL}                  -> market snapshot + AI take
  {Fore.LIGHTCYAN_EX}info{Style.RESET_ALL}                     -> get terms and number signifigance

  accounts                 -> list all trading accounts
  whoami                   -> show current active account
  create_account NAME      -> create a new trading account
  switch_account NAME      -> switch to another trading account
  delete_account NAME      -> delete a non-active account
  reset                    -> wipe state back to $1M
  help                     -> show this help
  clear                    -> clears terminal to clean up
  quit                     -> save snapshot and exit
"""