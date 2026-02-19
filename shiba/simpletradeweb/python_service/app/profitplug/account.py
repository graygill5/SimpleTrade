from contextlib import closing
from datetime import datetime
from typing import Dict, Any, List, Optional
from .db import get_conn
from .market import last_price

class PaperAccount:
    def __init__(self, account_id: int):
        self.account_id = int(account_id)

    def _get_cash(self, conn) -> float:
        row = conn.execute("SELECT cash FROM accounts WHERE id=?", (self.account_id,)).fetchone()
        if not row:
            raise ValueError("Account not found")
        return float(row["cash"])

    def _set_cash(self, conn, cash: float):
        conn.execute("UPDATE accounts SET cash=? WHERE id=?", (float(cash), self.account_id))

    def equity(self) -> float:
        with closing(get_conn()) as conn:
            cash = self._get_cash(conn)
            pv = 0.0
            rows = conn.execute("SELECT symbol, shares FROM positions WHERE account_id=?", (self.account_id,)).fetchall()
            for r in rows:
                px = last_price(r["symbol"])
                if px is not None:
                    pv += int(r["shares"]) * float(px)
            return float(cash + pv)

    def portfolio(self) -> Dict[str, Any]:
        with closing(get_conn()) as conn:
            cash = self._get_cash(conn)
            positions = []
            pv = 0.0

            rows = conn.execute(
                "SELECT symbol, shares, avg_cost FROM positions WHERE account_id=? ORDER BY symbol",
                (self.account_id,)
            ).fetchall()

            for r in rows:
                sym = r["symbol"]
                sh = int(r["shares"])
                avg = float(r["avg_cost"])
                px = last_price(sym)
                mv = (px * sh) if px is not None else None
                upl = (mv - avg * sh) if (mv is not None) else None
                if mv is not None:
                    pv += mv

                positions.append({
                    "symbol": sym,
                    "shares": sh,
                    "avg_cost": avg,
                    "last_price": px,
                    "market_value": mv,
                    "unrealized_pl": upl
                })

            equity = cash + pv
            return {
                "account_id": self.account_id,
                "cash": cash,
                "positions_value": pv,
                "equity": equity,
                "positions": positions
            }

    def history(self, limit: int = 200) -> List[Dict[str, Any]]:
        with closing(get_conn()) as conn:
            rows = conn.execute(
                "SELECT id, ts, symbol, side, shares, price FROM trades WHERE account_id=? ORDER BY id DESC LIMIT ?",
                (self.account_id, int(limit))
            ).fetchall()
            return [dict(r) for r in rows]

    def buy(self, symbol: str, shares: int) -> Dict[str, Any]:
        sym = symbol.upper().strip()
        sh = int(shares)
        if sh <= 0:
            raise ValueError("shares must be > 0")

        px = last_price(sym)
        if px is None:
            raise ValueError("Could not fetch price for symbol")

        cost = float(px) * sh

        with closing(get_conn()) as conn, conn:
            cash = self._get_cash(conn)
            if cash < cost:
                raise ValueError("Insufficient cash")

            # upsert position with weighted avg cost
            row = conn.execute(
                "SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                (self.account_id, sym)
            ).fetchone()

            if row:
                old_sh = int(row["shares"])
                old_avg = float(row["avg_cost"])
                new_sh = old_sh + sh
                new_avg = ((old_sh * old_avg) + (sh * float(px))) / new_sh
                conn.execute(
                    "UPDATE positions SET shares=?, avg_cost=? WHERE account_id=? AND symbol=?",
                    (new_sh, new_avg, self.account_id, sym)
                )
            else:
                conn.execute(
                    "INSERT INTO positions(account_id, symbol, shares, avg_cost) VALUES(?,?,?,?)",
                    (self.account_id, sym, sh, float(px))
                )

            self._set_cash(conn, cash - cost)
            conn.execute(
                "INSERT INTO trades(account_id, ts, symbol, side, shares, price) VALUES(?,?,?,?,?,?)",
                (self.account_id, datetime.now().isoformat(), sym, "BUY", sh, float(px))
            )

        return {"symbol": sym, "shares": sh, "price": float(px), "cost": cost}

    def sell(self, symbol: str, shares: int) -> Dict[str, Any]:
        sym = symbol.upper().strip()
        sh = int(shares)
        if sh <= 0:
            raise ValueError("shares must be > 0")

        px = last_price(sym)
        if px is None:
            raise ValueError("Could not fetch price for symbol")

        with closing(get_conn()) as conn, conn:
            row = conn.execute(
                "SELECT shares, avg_cost FROM positions WHERE account_id=? AND symbol=?",
                (self.account_id, sym)
            ).fetchone()
            if not row:
                raise ValueError("No position to sell")

            have = int(row["shares"])
            avg = float(row["avg_cost"])
            if sh > have:
                raise ValueError("Not enough shares")

            proceeds = float(px) * sh

            # update position
            remaining = have - sh
            if remaining == 0:
                conn.execute("DELETE FROM positions WHERE account_id=? AND symbol=?", (self.account_id, sym))
            else:
                conn.execute(
                    "UPDATE positions SET shares=? WHERE account_id=? AND symbol=?",
                    (remaining, self.account_id, sym)
                )

            cash = self._get_cash(conn)
            self._set_cash(conn, cash + proceeds)

            conn.execute(
                "INSERT INTO trades(account_id, ts, symbol, side, shares, price) VALUES(?,?,?,?,?,?)",
                (self.account_id, datetime.now().isoformat(), sym, "SELL", sh, float(px))
            )

        realized = (float(px) - avg) * sh
        return {"symbol": sym, "shares": sh, "price": float(px), "proceeds": proceeds, "realized_pl_est": realized}

    def reset(self, starting_cash: float = 1_000_000.0) -> Dict[str, Any]:
        with closing(get_conn()) as conn, conn:
            conn.execute("DELETE FROM positions WHERE account_id=?", (self.account_id,))
            conn.execute("DELETE FROM trades WHERE account_id=?", (self.account_id,))
            self._set_cash(conn, float(starting_cash))
        return {"account_id": self.account_id, "cash": float(starting_cash)}

