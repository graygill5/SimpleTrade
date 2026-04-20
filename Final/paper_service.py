"""
Paper trading: simulated cash, holdings, transactions, snapshots, viewers, leaderboard.
"""
from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

import market_service

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")

STARTING_CASH = 10_000.0
SYMBOL_RE = re.compile(r"^[A-Z0-9\^\-\.]{1,24}$")

def _money(x: Any) -> float:
    return round(float(x), 2)


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def user_exists(username: str) -> bool:
    u = (username or "").strip()
    if not u:
        return False
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=?", (u,))
    ok = cur.fetchone() is not None
    db.close()
    return ok


def ensure_paper_account(username: str) -> None:
    """Create paper account with starting cash if missing."""
    u = (username or "").strip()
    if not u:
        return
    db = connect()
    cur = db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO paper_accounts (username, cash) VALUES (?, ?)",
        (u, _money(STARTING_CASH)),
    )
    db.commit()
    db.close()


def backfill_paper_accounts_for_existing_users() -> None:
    """Give every user without a paper row the starting balance."""
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT username FROM users")
    for (uname,) in cur.fetchall():
        cur.execute(
            "INSERT OR IGNORE INTO paper_accounts (username, cash) VALUES (?, ?)",
            (uname, _money(STARTING_CASH)),
        )
    db.commit()
    db.close()


def get_cash(username: str) -> float:
    ensure_paper_account(username)
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT cash FROM paper_accounts WHERE username=?", (username,))
    row = cur.fetchone()
    db.close()
    return _money(row[0]) if row else _money(STARTING_CASH)


def _holdings_rows(username: str) -> list[tuple[str, float, float]]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT symbol, shares, avg_cost FROM paper_holdings WHERE username=? ORDER BY symbol",
        (username,),
    )
    rows = [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]
    db.close()
    return rows


def _compute_totals(
    username: str, quotes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    cash = get_cash(username)
    hrows = _holdings_rows(username)
    holdings_mkt = 0.0
    cost_basis = 0.0
    unrealized = 0.0
    positions: list[dict[str, Any]] = []
    for sym, shares, avg in hrows:
        sh = _money(shares)
        ac = _money(avg)
        basis = _money(sh * ac)
        cost_basis += basis
        q_key = (sym or "").strip().upper()
        q = quotes.get(q_key) or {}
        px = q.get("price")
        last = _money(px) if px is not None else ac
        mkt = _money(sh * last)
        holdings_mkt += mkt
        u_pl = _money(mkt - basis)
        unrealized += u_pl
        day_pct = q.get("change_pct")
        positions.append(
            {
                "symbol": sym,
                "name": q.get("name") or sym,
                "shares": sh,
                "avg_cost": ac,
                "last": last,
                "market_value": mkt,
                "cost_basis": basis,
                "unrealized_pl": u_pl,
                "unrealized_pct": _money((u_pl / basis) * 100.0) if basis > 0 else 0.0,
                "change_pct": day_pct,
            }
        )
    total = _money(cash + holdings_mkt)
    total_pl = _money(total - STARTING_CASH)
    return {
        "cash": cash,
        "holdings_market_value": _money(holdings_mkt),
        "cost_basis": _money(cost_basis),
        "total_value": total,
        "unrealized_pl": _money(unrealized),
        "total_pl": total_pl,
        "total_pl_pct": _money((total_pl / STARTING_CASH) * 100.0)
        if STARTING_CASH > 0
        else 0.0,
        "positions": positions,
    }


def fetch_quotes_map(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Quote map keyed by symbol — uses parallel Yahoo fetches (not sequential per ticker)."""
    syms = list(dict.fromkeys(s for s in symbols if s))
    if not syms:
        return {}
    rows = market_service.fetch_quotes_for_symbols(syms)
    out: dict[str, dict[str, Any]] = {}
    for q in rows:
        if q and q.get("symbol"):
            out[str(q["symbol"]).upper()] = q
    return out


def get_portfolio_state(username: str) -> dict[str, Any]:
    ensure_paper_account(username)
    syms = [r[0] for r in _holdings_rows(username)]
    quotes = fetch_quotes_map(syms)
    core = _compute_totals(username, quotes)
    core["starting_cash"] = STARTING_CASH
    core["username"] = username
    return core


def record_snapshot(username: str, totals: dict[str, Any]) -> None:
    db = connect()
    cur = db.cursor()
    invested = _money(totals["holdings_market_value"])
    cur.execute(
        """
        INSERT INTO paper_snapshots (username, total_value, cash, invested)
        VALUES (?, ?, ?, ?)
        """,
        (
            username,
            totals["total_value"],
            totals["cash"],
            invested,
        ),
    )
    db.commit()
    db.close()


def get_snapshots(username: str, limit: int = 120) -> list[dict[str, Any]]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT created_at, total_value, cash, invested
        FROM paper_snapshots
        WHERE username=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (username, max(10, min(limit, 500))),
    )
    rows = cur.fetchall()
    db.close()
    out = [
        {
            "t": r[0],
            "total_value": _money(r[1]),
            "cash": _money(r[2]),
            "invested": _money(r[3]),
        }
        for r in reversed(rows)
    ]
    return out


def _log_transaction(
    username: str,
    kind: str,
    *,
    symbol: str | None,
    shares: float | None,
    price: float | None,
    amount: float,
    cash_after: float,
    note: str | None = None,
) -> None:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO paper_transactions
        (username, kind, symbol, shares, price, amount, cash_after, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            kind,
            symbol,
            _money(shares) if shares is not None else None,
            _money(price) if price is not None else None,
            _money(amount),
            _money(cash_after),
            note,
        ),
    )
    db.commit()
    db.close()


def buy(
    username: str, symbol: str, shares: float
) -> tuple[bool, str, dict[str, Any] | None]:
    sym = symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        return False, "Invalid symbol.", None
    sh = _money(shares)
    if sh <= 0:
        return False, "Share amount must be positive.", None

    q = market_service.fetch_quote(sym)
    if not q or q.get("price") is None:
        return False, "Quote unavailable for that symbol.", None
    sym = q.get("symbol") or sym
    px = _money(q["price"])
    cost = _money(sh * px)

    ensure_paper_account(username)
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT cash FROM paper_accounts WHERE username=?", (username,))
    row = cur.fetchone()
    if not row:
        db.close()
        return False, "No paper account.", None
    cash = _money(row[0])
    if cash < cost:
        db.close()
        return False, "Insufficient cash for this order.", None

    new_cash = _money(cash - cost)
    cur.execute(
        "SELECT shares, avg_cost FROM paper_holdings WHERE username=? AND symbol=?",
        (username, sym),
    )
    h = cur.fetchone()
    if h:
        old_sh = float(h[0])
        old_avg = float(h[1])
        new_sh = _money(old_sh + sh)
        new_avg = _money((old_sh * old_avg + sh * px) / new_sh) if new_sh > 0 else old_avg
        cur.execute(
            """
            UPDATE paper_holdings SET shares=?, avg_cost=?
            WHERE username=? AND symbol=?
            """,
            (new_sh, new_avg, username, sym),
        )
    else:
        cur.execute(
            """
            INSERT INTO paper_holdings (username, symbol, shares, avg_cost)
            VALUES (?, ?, ?, ?)
            """,
            (username, sym, sh, px),
        )

    cur.execute(
        "UPDATE paper_accounts SET cash=? WHERE username=?",
        (new_cash, username),
    )
    db.commit()
    db.close()

    _log_transaction(
        username,
        "buy",
        symbol=sym,
        shares=sh,
        price=px,
        amount=-cost,
        cash_after=new_cash,
        note=None,
    )
    st = get_portfolio_state(username)
    record_snapshot(username, st)
    return True, "", st


def sell(
    username: str, symbol: str, shares: float
) -> tuple[bool, str, dict[str, Any] | None]:
    sym = symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        return False, "Invalid symbol.", None
    sh = _money(shares)
    if sh <= 0:
        return False, "Share amount must be positive.", None

    q = market_service.fetch_quote(sym)
    if not q or q.get("price") is None:
        return False, "Quote unavailable for that symbol.", None
    sym = q.get("symbol") or sym
    px = _money(q["price"])

    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT shares, avg_cost FROM paper_holdings WHERE username=? AND symbol=?",
        (username, sym),
    )
    h = cur.fetchone()
    if not h:
        db.close()
        return False, "You do not hold that symbol.", None
    held = _money(float(h[0]))
    avg = _money(float(h[1]))
    if sh > held + 1e-6:
        db.close()
        return False, "Cannot sell more shares than you hold.", None

    proceeds = _money(sh * px)
    cur.execute("SELECT cash FROM paper_accounts WHERE username=?", (username,))
    cash = _money(float(cur.fetchone()[0]))
    new_cash = _money(cash + proceeds)
    new_held = _money(held - sh)

    if new_held <= 0.0001:
        cur.execute(
            "DELETE FROM paper_holdings WHERE username=? AND symbol=?",
            (username, sym),
        )
    else:
        cur.execute(
            "UPDATE paper_holdings SET shares=? WHERE username=? AND symbol=?",
            (new_held, username, sym),
        )

    cur.execute(
        "UPDATE paper_accounts SET cash=? WHERE username=?",
        (new_cash, username),
    )
    db.commit()
    db.close()

    realized = _money((px - avg) * sh)
    _log_transaction(
        username,
        "sell",
        symbol=sym,
        shares=sh,
        price=px,
        amount=proceeds,
        cash_after=new_cash,
        note=f"Realized P/L ~ ${realized:,.2f}",
    )
    st = get_portfolio_state(username)
    record_snapshot(username, st)
    return True, "", st


def credit_reward(username: str, amount: float, note: str) -> tuple[bool, str]:
    amt = _money(amount)
    if amt <= 0:
        return False, "Amount must be positive."
    ensure_paper_account(username)
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT cash FROM paper_accounts WHERE username=?", (username,))
    row = cur.fetchone()
    if not row:
        db.close()
        return False, "No paper account."
    cash = _money(float(row[0]))
    new_cash = _money(cash + amt)
    cur.execute(
        "UPDATE paper_accounts SET cash=? WHERE username=?",
        (new_cash, username),
    )
    db.commit()
    db.close()
    _log_transaction(
        username,
        "reward",
        symbol=None,
        shares=None,
        price=None,
        amount=amt,
        cash_after=new_cash,
        note=note,
    )
    st = get_portfolio_state(username)
    record_snapshot(username, st)
    return True, "ok"


def claim_module_reward(username: str, module_id: str) -> tuple[bool, str]:
    """Legacy endpoint — rewards are granted via Learning page quizzes (daily reset)."""
    _ = module_id
    return (
        False,
        "Complete modules on the Learning page: pass today's quiz to earn paper cash.",
    )


def list_transactions(username: str, limit: int = 100) -> list[dict[str, Any]]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, created_at, kind, symbol, shares, price, amount, cash_after, note
        FROM paper_transactions
        WHERE username=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (username, max(1, min(limit, 500))),
    )
    rows = cur.fetchall()
    db.close()
    return [
        {
            "id": r[0],
            "created_at": r[1],
            "kind": r[2],
            "symbol": r[3],
            "shares": _money(r[4]) if r[4] is not None else None,
            "price": _money(r[5]) if r[5] is not None else None,
            "amount": _money(r[6]),
            "cash_after": _money(r[7]),
            "note": r[8],
        }
        for r in rows
    ]


def add_viewer(owner: str, viewer: str) -> tuple[bool, str]:
    o = owner.strip()
    v = viewer.strip()
    if not o or not v:
        return False, "Usernames required."
    if o == v:
        return False, "You cannot add yourself."
    if not user_exists(v):
        return False, "That user does not exist."
    db = connect()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO portfolio_viewers (owner_username, viewer_username) VALUES (?, ?)",
            (o, v),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return False, "Already on your list."
    db.close()
    return True, "Viewer added."


def remove_viewer(owner: str, viewer: str) -> bool:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM portfolio_viewers WHERE owner_username=? AND viewer_username=?",
        (owner, viewer),
    )
    n = cur.rowcount
    db.commit()
    db.close()
    return n > 0


def list_viewers(owner: str) -> list[str]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT viewer_username FROM portfolio_viewers WHERE owner_username=? ORDER BY viewer_username",
        (owner,),
    )
    out = [r[0] for r in cur.fetchall()]
    db.close()
    return out


def can_view_portfolio(viewer: str, owner: str) -> bool:
    if viewer == owner:
        return True
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT 1 FROM portfolio_viewers
        WHERE owner_username=? AND viewer_username=?
        """,
        (owner, viewer),
    )
    ok = cur.fetchone() is not None
    db.close()
    return ok


def leaderboard(limit: int = 25) -> list[dict[str, Any]]:
    """Rank users by total portfolio value (cash + holdings at last prices)."""
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT username, cash FROM paper_accounts")
    accounts = cur.fetchall()
    cur.execute("SELECT username, symbol, shares FROM paper_holdings")
    hold_rows = cur.fetchall()
    db.close()

    by_user: dict[str, dict[str, float]] = {}
    for u, c in accounts:
        by_user[u] = {"cash": float(c), "symbols": []}
    for u, sym, sh in hold_rows:
        if u not in by_user:
            by_user[u] = {"cash": STARTING_CASH, "symbols": []}
        by_user[u]["symbols"].append((sym, float(sh)))

    all_syms = sorted({sym for _, sym, _ in hold_rows})
    quotes = fetch_quotes_map(all_syms)

    ranked: list[tuple[str, float]] = []
    for u, acct in by_user.items():
        cash = _money(acct["cash"])
        mkt = 0.0
        for sym, shares in acct["symbols"]:
            q_key = (sym or "").strip().upper()
            q = quotes.get(q_key)
            px = q.get("price") if q else None
            if px is None:
                px = 0.0
            mkt += _money(float(shares) * float(px))
        tv = _money(cash + mkt)
        ranked.append((u, tv))

    ranked.sort(key=lambda x: x[1], reverse=True)
    lim = max(1, min(limit, 100))
    out = []
    for i, (uname, tv) in enumerate(ranked[:lim], start=1):
        out.append({"rank": i, "username": uname, "total_value": tv})
    return out


def seed_initial_snapshot(username: str) -> None:
    """First snapshot so performance chart has a starting point."""
    ensure_paper_account(username)
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM paper_snapshots WHERE username=?",
        (username,),
    )
    n = cur.fetchone()[0]
    db.close()
    if n > 0:
        return
    st = get_portfolio_state(username)
    record_snapshot(username, st)
