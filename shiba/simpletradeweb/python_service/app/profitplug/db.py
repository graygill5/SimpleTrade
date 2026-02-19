import os
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import closing

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "portfolio.db"

def get_db_path() -> Path:
    env = os.getenv("PROFITPLUG_DB_PATH")
    if env:
        p = Path(env).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return DEFAULT_DB_PATH

def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db(starting_cash: float = 1_000_000.0, account_name: str = "Main") -> int:
    with closing(get_conn()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            cash REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS positions(
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            shares INTEGER NOT NULL,
            avg_cost REAL NOT NULL,
            PRIMARY KEY(account_id, symbol),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
        """)

        # create or fetch account
        row = conn.execute("SELECT id FROM accounts WHERE name=?", (account_name,)).fetchone()
        if row:
            return int(row["id"])

        conn.execute(
            "INSERT INTO accounts(name, cash, created_at) VALUES(?,?,?)",
            (account_name, float(starting_cash), datetime.now().isoformat())
        )
        acc_id = conn.execute("SELECT id FROM accounts WHERE name=?", (account_name,)).fetchone()["id"]
        return int(acc_id)

def list_accounts():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT id, name, cash, created_at FROM accounts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

