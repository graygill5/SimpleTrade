from functools import wraps
import os
import re
from urllib.parse import quote

from flask import Flask, jsonify, render_template, request, redirect, session

import sqlite3

import ai_service
import market_service

app = Flask(__name__)
app.secret_key = "secret123"
# Session cookies: Lax works for same-site fetch + top-level navigation; set SESSION_COOKIE_SECURE=True behind HTTPS in production.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Allow common US tickers: digits (e.g. chips), ^ for indexes, hyphen/dot class shares
SYMBOL_RE = re.compile(r"^[A-Z0-9\^\-\.]{1,24}$")


def get_db():
    return sqlite3.connect("app.db")


def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            username TEXT NOT NULL,
            symbol TEXT NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (username, symbol)
        )
    """)

    db.commit()
    db.close()


init_db()


@app.template_filter("fmt_cap")
def fmt_cap_filter(n):
    if n is None:
        return "—"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    ax = abs(x)
    if ax >= 1e12:
        return f"{x/1e12:.2f}T"
    if ax >= 1e9:
        return f"{x/1e9:.2f}B"
    if ax >= 1e6:
        return f"{x/1e6:.2f}M"
    if ax >= 1e3:
        return f"{x/1e3:.2f}K"
    return f"{x:,.0f}"


@app.template_filter("fmt_vol")
def fmt_vol_filter(n):
    if n is None:
        return "—"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    ax = abs(x)
    if ax >= 1e9:
        return f"{x/1e9:.2f}B"
    if ax >= 1e6:
        return f"{x/1e6:.2f}M"
    if ax >= 1e3:
        return f"{x/1e3:.2f}K"
    return f"{x:,.0f}"


@app.template_filter("fmt_price")
def fmt_price_filter(n):
    if n is None:
        return "—"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.2f}"
    return f"{x:.4f}"


def login_required_json(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return inner


def current_user() -> str | None:
    return session.get("user")


# -------- LOGIN --------
@app.route("/login")
def login_alias():
    """Some users expect /login; the real page is at /."""
    return redirect("/")


@app.route("/", methods=["GET", "POST"])
def login():
    tab = request.args.get("tab", "login")
    if tab not in ("login", "signup"):
        tab = "login"
    message = request.args.get("message", "")
    error = ""
    login_username = ""
    signup_username = ""

    if request.method == "POST":
        login_username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if login_username == "" or password == "":
            error = "Please enter both username and password."
            return render_template(
                "login.html",
                error=error,
                message=message,
                active_tab="login",
                login_username=login_username,
                signup_username=signup_username,
            )

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT id, username, password FROM users WHERE username=?",
            (login_username,),
        )
        row = cur.fetchone()
        db.close()

        if row is None:
            error = "No account found with that username."
        elif row[2] != password:
            error = "Incorrect password. Try again or create a new account."
        else:
            session["user"] = login_username
            return redirect("/dashboard?welcome=1")

        return render_template(
            "login.html",
            error=error,
            message=message,
            active_tab="login",
            login_username=login_username,
            signup_username=signup_username,
        )

    return render_template(
        "login.html",
        error=error,
        message=message,
        active_tab=tab,
        login_username=login_username,
        signup_username=signup_username,
    )


# -------- SIGNUP --------
@app.route("/signup", methods=["POST"])
def signup():
    signup_username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if signup_username == "" or password == "":
        return render_template(
            "login.html",
            error="Username and password cannot be empty.",
            message="",
            active_tab="signup",
            login_username="",
            signup_username=signup_username,
        )

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT id FROM users WHERE username=?", (signup_username,))
    existing_user = cur.fetchone()

    if existing_user:
        db.close()
        return render_template(
            "login.html",
            error="That username is already taken. Pick another or sign in.",
            message="",
            active_tab="signup",
            login_username="",
            signup_username=signup_username,
        )

    cur.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (signup_username, password),
    )
    db.commit()
    db.close()

    safe = quote(signup_username, safe="")
    return redirect(f"/account-created?u={safe}")


# -------- ACCOUNT CREATED --------
@app.route("/account-created")
def account_created():
    username = request.args.get("u", "").strip()
    return render_template("account_created.html", username=username)


def _watchlist_symbols(username: str) -> list[str]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT symbol FROM watchlist WHERE username=? ORDER BY added_at DESC",
        (username,),
    )
    rows = cur.fetchall()
    db.close()
    return [r[0] for r in rows]


def _watchlist_add(username: str, symbol: str) -> tuple[bool, str]:
    sym = symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        return False, "Invalid symbol format."
    q = market_service.fetch_quote(sym)
    if not q or q.get("price") is None:
        return False, "Symbol not found or quote unavailable."
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO watchlist (username, symbol) VALUES (?, ?)",
            (username, sym),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return False, "That symbol is already on your watchlist."
    db.close()
    return True, sym


def _watchlist_remove(username: str, symbol: str) -> bool:
    sym = symbol.strip().upper()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM watchlist WHERE username=? AND symbol=?",
        (username, sym),
    )
    db.commit()
    n = cur.rowcount
    db.close()
    return n > 0


# -------- DASHBOARD (MARKET OVERVIEW) --------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect("/?message=" + quote("Please sign in to open the dashboard."))

    welcome = request.args.get("welcome") == "1"
    indexes = market_service.fetch_indexes()
    gainers, losers = market_service.fetch_movers()
    trending = market_service.fetch_trending_by_volume()
    news = market_service.fetch_market_news(16)
    wl_syms = _watchlist_symbols(user)
    watchlist = market_service.fetch_quotes_for_symbols(wl_syms)

    return render_template(
        "dashboard.html",
        username=user,
        welcome=welcome,
        indexes=indexes,
        gainers=gainers,
        losers=losers,
        trending=trending,
        news=news,
        watchlist=watchlist,
        ai_ready=ai_service.is_configured(),
    )


@app.route("/portfolio")
def portfolio():
    user = current_user()
    if not user:
        return redirect("/?message=" + quote("Please sign in to open Portfolio."))
    return render_template("portfolio.html", username=user)


@app.route("/chats")
def chats():
    user = current_user()
    if not user:
        return redirect("/?message=" + quote("Please sign in to open Chats."))
    return render_template("chats.html", username=user)


@app.route("/learning")
def learning_modules():
    user = current_user()
    if not user:
        return redirect("/?message=" + quote("Please sign in to open Learning modules."))
    return render_template("learning.html", username=user)


# -------- API: SEARCH & QUOTE --------
@app.route("/api/search")
@login_required_json
def api_search():
    q = request.args.get("q", "").strip().upper()
    if not q:
        return jsonify({"results": []})

    results: list[dict] = []
    seen: set[str] = set()

    exact = market_service.fetch_quote(q, with_mcap=False)
    if exact and exact.get("symbol"):
        s = exact["symbol"]
        seen.add(s)
        results.append(
            {
                "symbol": s,
                "name": exact.get("name"),
                "price": exact.get("price"),
                "change_pct": exact.get("change_pct"),
            }
        )

    matches = [s for s in market_service.MOVERS_UNIVERSE if s.startswith(q)]
    if len(q) >= 2:
        for s in market_service.MOVERS_UNIVERSE:
            if s not in matches and q in s:
                matches.append(s)

    for s in matches:
        if s in seen:
            continue
        qd = market_service.fetch_quote(s, with_mcap=False)
        if qd:
            seen.add(s)
            results.append(
                {
                    "symbol": s,
                    "name": qd.get("name"),
                    "price": qd.get("price"),
                    "change_pct": qd.get("change_pct"),
                }
            )
        if len(results) >= 12:
            break

    return jsonify({"results": results[:12]})


@app.route("/api/quote/<path:symbol>")
@login_required_json
def api_quote(symbol):
    sym = symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        return jsonify({"error": "Invalid symbol"}), 400
    q = market_service.fetch_quote(sym)
    if not q:
        return jsonify({"error": "Quote unavailable"}), 404
    return jsonify(q)


@app.route("/api/chart/<path:symbol>")
@login_required_json
def api_chart(symbol):
    sym = symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        return jsonify({"error": "Invalid symbol"}), 400
    range_key = (request.args.get("range") or "1m").strip().lower()
    if range_key not in market_service.CHART_RANGE_CONFIG:
        return jsonify({"error": "Invalid range"}), 400
    data = market_service.fetch_chart_series(sym, range_key)
    if not data:
        return jsonify({"error": "Chart data unavailable"}), 404
    return jsonify(data)


# -------- API: MARKET NEWS (same feed as dashboard + AI context) --------
@app.route("/api/news")
@login_required_json
def api_news():
    raw = (request.args.get("limit") or "16").strip()
    try:
        limit = int(raw)
    except ValueError:
        limit = 16
    limit = max(1, min(limit, 50))
    items = market_service.fetch_market_news(limit)
    return jsonify(
        {
            "items": items,
            "limit": limit,
            "sources": ["SPY", "QQQ", "^GSPC"],
        }
    )


# -------- API: WATCHLIST --------
@app.route("/api/watchlist", methods=["GET"])
@login_required_json
def api_watchlist_get():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    syms = _watchlist_symbols(user)
    quotes = market_service.fetch_quotes_for_symbols(syms)
    return jsonify({"symbols": syms, "quotes": quotes})


@app.route("/api/watchlist", methods=["POST"])
@login_required_json
def api_watchlist_post():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip()
    ok, msg = _watchlist_add(user, symbol)
    if not ok:
        return jsonify({"error": msg}), 400
    q = market_service.fetch_quote(msg)
    return jsonify({"ok": True, "symbol": msg, "quote": q})


@app.route("/api/watchlist/<path:symbol>", methods=["DELETE"])
@login_required_json
def api_watchlist_delete(symbol):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if _watchlist_remove(user, symbol):
        return jsonify({"ok": True})
    return jsonify({"error": "Not in watchlist"}), 404


# -------- API: AI --------
@app.route("/api/ai/market-summary", methods=["POST"])
@login_required_json
def api_ai_market_summary():
    extra = ""
    body = request.get_json(silent=True) or {}
    if body.get("notes"):
        extra = "\nUser notes: " + str(body.get("notes"))[:2000]
    ctx = market_service.build_ai_context_snapshot() + extra
    text, err = ai_service.generate_market_summary(ctx)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"text": text})


@app.route("/api/ai/outlook", methods=["POST"])
@login_required_json
def api_ai_outlook():
    extra = ""
    body = request.get_json(silent=True) or {}
    if body.get("notes"):
        extra = "\nUser notes: " + str(body.get("notes"))[:2000]
    ctx = market_service.build_ai_context_snapshot() + extra
    text, err = ai_service.generate_educational_outlook(ctx)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"text": text})


@app.route("/api/ai/ticker-overview", methods=["POST"])
@login_required_json
def api_ai_ticker_overview():
    body = request.get_json(silent=True) or {}
    symbol = (body.get("symbol") or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        return jsonify({"error": "Invalid symbol"}), 400
    ctx, err, news = market_service.build_ticker_overview_context(symbol)
    if err or not ctx:
        return jsonify({"error": err or "Unavailable"}), 400
    text, err_ai = ai_service.generate_ticker_overview(ctx)
    news_ui = news[:10]
    out: dict = {"news": news_ui, "symbol": symbol}
    if err_ai:
        out["text"] = None
        out["ai_error"] = err_ai
    else:
        out["text"] = text
    return jsonify(out)


@app.route("/api/ai/chat", methods=["POST"])
@login_required_json
def api_ai_chat():
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    if not isinstance(messages, list):
        return jsonify({"error": "messages must be a list"}), 400
    text, err = ai_service.chat_reply(messages)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"reply": text})


# -------- LOGOUT --------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/?message=You have been signed out securely.")


# -------- RUN --------
if __name__ == "__main__":
    # Default 5001: on macOS, port 5000 is often used by AirPlay Receiver — traffic to :5000 can get HTTP 403
    # from Apple's service instead of Flask. Override with PORT=5000 if you know it's free.
    # 0.0.0.0: reachable at http://127.0.0.1:PORT and http://localhost:PORT on this machine.
    # Set FLASK_RUN_HOST=127.0.0.1 if you only want loopback. Use http:// not https:// (dev has no TLS).
    port = int(os.environ.get("PORT", "5001"))
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    print(
        f"\n  SimpleTrade — open ONE of these in your browser (not https):\n"
        f"    http://127.0.0.1:{port}/\n"
        f"    http://localhost:{port}/\n"
        f"  (Stick to the same host after you sign in so cookies work.)\n",
        flush=True,
    )
    app.run(debug=True, host=host, port=port)
