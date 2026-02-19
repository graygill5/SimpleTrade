from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from colorama import Fore, Style

from .db import get_conn
from .market_data import last_price


def pnl_emoji(price: Optional[float], avg_cost: float, tol: float = 0.002) -> str:
    if avg_cost == 0 or price is None:
        return "➖"
    chg = (price - avg_cost) / avg_cost
    if chg > tol:
        return "📈"
    if chg < -tol:
        return "📉"
    return "➖"


class PaperAccount:
    def __init__(self, account_id: int):
        self.account_id = int(account_id)

    def _get_cash(self, conn) -> float:
        return float(
            conn.execute("SELECT cash FROM accounts WHERE id=?", (self.account_id,))
            .fetchone()["cash"]
        )

    def _set_cash(self, conn, cash: float) -> None:
        conn.execute("UPDATE accounts SET cash=? WHERE id=?", (float(cash), self.account_id))

    def equity(self) -> float:
        with closing(get_conn()) as conn:
            cash = self._get_cash(conn)
            pv = 0.0
            for row in conn.execute(
                "SELECT symbol, shares FROM positions WHERE account_id=?",
                (self.account_id,),
            ):
                px = last_price(row["symbol"])
                if px is not None:
                    pv += float(row["shares"]) * float(px)
            return float(cash + pv)

    def buy(self, sym: str, shares: int) -> None:
        sym = sym.strip().upper()
        shares = int(shares)
        if shares <= 0:
            print("✖ Shares must be > 0.")
            return

        with closing(get_conn()) as conn, conn:
            price = last_price(sym)
            if price is None:
                print("✖ Couldn't fetch price.")
                return

            cost = float(price) * shares
            cash = self._get_cash(conn)
            if cost > cash + 1e-9:
                print("✖ Not enough cash.")
                return

            self._set_cash(conn, cash - cost)

            row = conn.execute(
                "SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                (self.account_id, sym),
            ).fetchone()

            if row:
                old_shares = int(row["shares"])
                old_avg = float(row["avg_cost"])
                new_shares = old_shares + shares
                new_avg = (old_shares * old_avg + cost) / new_shares
                conn.execute(
                    "UPDATE positions SET shares=?, avg_cost=? WHERE account_id=? AND symbol=?",
                    (new_shares, float(new_avg), self.account_id, sym),
                )
            else:
                conn.execute(
                    "INSERT INTO positions (account_id, symbol, shares, avg_cost) VALUES (?, ?, ?, ?)",
                    (self.account_id, sym, shares, float(price)),
                )

            conn.execute(
                """INSERT INTO trades(account_id,time,action,symbol,shares,price,total,realized_pnl)
                   VALUES(?,?,?,?,?,?,?,NULL)""",
                (self.account_id, datetime.now().isoformat(), "BUY", sym, shares, float(price), float(cost)),
            )

        print(f"✓ Bought {shares} {sym} @ ${price:.2f}")

    def sell(self, sym: str, shares: int) -> None:
        sym = sym.strip().upper()
        shares = int(shares)
        if shares <= 0:
            print("✖ Shares must be > 0.")
            return

        with closing(get_conn()) as conn, conn:
            pos = conn.execute(
                "SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                (self.account_id, sym),
            ).fetchone()

            if not pos or int(pos["shares"]) < shares:
                print("✖ Not enough shares.")
                return

            price = last_price(sym)
            if price is None:
                print("✖ Couldn't fetch price.")
                return

            avg_cost = float(pos["avg_cost"])
            revenue = float(price) * shares
            realized = (float(price) - avg_cost) * shares

            cash = self._get_cash(conn)
            self._set_cash(conn, cash + revenue)

            new_shares = int(pos["shares"]) - shares
            if new_shares == 0:
                conn.execute(
                    "DELETE FROM positions WHERE account_id=? AND symbol=?",
                    (self.account_id, sym),
                )
            else:
                conn.execute(
                    "UPDATE positions SET shares=? WHERE account_id=? AND symbol=?",
                    (new_shares, self.account_id, sym),
                )

            conn.execute(
                """INSERT INTO trades(account_id,time,action,symbol,shares,price,total,realized_pnl)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (self.account_id, datetime.now().isoformat(), "SELL", sym, shares, float(price), float(revenue), float(realized)),
            )

        print(f"✓ Sold {shares} {sym} @ ${price:.2f}  (Realized P/L: ${realized:.2f})")

    def portfolio(self) -> None:
        with closing(get_conn()) as conn:
            rows = []
            for r in conn.execute(
                "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=? ORDER BY symbol",
                (self.account_id,),
            ):
                sym = r["symbol"]
                px = last_price(sym)
                if px is None:
                    continue

                sh = int(r["shares"])
                avg = float(r["avg_cost"])
                mv = float(px) * sh
                u_pnl = (float(px) - avg) * sh
                emo = pnl_emoji(px, avg)
                rows.append([sym, emo, sh, avg, float(px), mv, u_pnl])

            df = pd.DataFrame(
                rows,
                columns=["Symbol", "Δ", "Shares", "Avg Cost", "Price", "Mkt Value", "Unrealized P/L"],
            )
            cash = self._get_cash(conn)

        eq = self.equity()
        print(f"\n--- {Fore.LIGHTBLUE_EX}Portfolio{Style.RESET_ALL} ---")
        if df.empty:
            print("(no positions)")
        else:
            print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
        print(f"Cash: ${cash:,.2f}   Equity: ${eq:,.2f}")

    def history(self) -> None:
        with closing(get_conn()) as conn:
            df = pd.read_sql_query(
                "SELECT time, action, symbol, shares, price, total, realized_pnl "
                "FROM trades WHERE account_id=? ORDER BY time",
                conn,
                params=(self.account_id,),
            )

        print("\n--- Trade History ---")
        if df.empty:
            print("(no trades)")
        else:
            print(df.to_string(index=False))

    def reset(self, starting_cash: float = 1_000_000.0) -> None:
        with closing(get_conn()) as conn, conn:
            conn.execute("DELETE FROM positions WHERE account_id=?", (self.account_id,))
            conn.execute("DELETE FROM trades WHERE account_id=?", (self.account_id,))
            conn.execute("UPDATE accounts SET cash=? WHERE id=?", (float(starting_cash), self.account_id))
        print("↺ Reset account.")

    def snapshot_on_exit(self) -> None:
        with closing(get_conn()) as conn, conn:
            pos = conn.execute(
                "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=?",
                (self.account_id,),
            ).fetchall()

            pos_json = json.dumps([dict(r) for r in pos])
            cash = self._get_cash(conn)
            equity = self.equity()

            conn.execute(
                """INSERT INTO snapshots(account_id,time,equity,cash,positions_json)
                   VALUES(?,?,?,?,?)""",
                (self.account_id, datetime.now().isoformat(), float(equity), float(cash), pos_json),
            )

