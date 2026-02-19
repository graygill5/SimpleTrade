from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Optional

from .config import db_path

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
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


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db(starting_cash: float = 100_000.0, account_name: str = "Main") -> int:
    """
    Creates schema if missing and ensures an account exists.
    Returns account id.
    """
    with closing(get_conn()) as conn, conn:
        conn.executescript(DDL)

        row = conn.execute(
            "SELECT id FROM accounts WHERE name=?",
            (account_name,),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO accounts (name, cash, created_at) VALUES (?, ?, ?)",
                (account_name, float(starting_cash), datetime.now().isoformat()),
            )

        acc_id = conn.execute(
            "SELECT id FROM accounts WHERE name=?",
            (account_name,),
        ).fetchone()["id"]

        return int(acc_id)

