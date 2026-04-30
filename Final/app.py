from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import os
import re
from urllib.parse import quote

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    redirect,
    send_file,
    session,
)

import sqlite3

import ai_service
import learning_service
import market_service
import paper_service
import social_service

app = Flask(__name__)
app.secret_key = "secret123"
# Session cookies: Lax works for same-site fetch + top-level navigation; set SESSION_COOKIE_SECURE=True behind HTTPS in production.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# In local dev, avoid stale JS/CSS after rapid edits/hot reloads.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_accounts (
            username TEXT PRIMARY KEY,
            cash REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_holdings (
            username TEXT NOT NULL,
            symbol TEXT NOT NULL,
            shares REAL NOT NULL,
            avg_cost REAL NOT NULL,
            PRIMARY KEY (username, symbol)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            kind TEXT NOT NULL,
            symbol TEXT,
            shares REAL,
            price REAL,
            amount REAL NOT NULL,
            cash_after REAL NOT NULL,
            note TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            invested REAL NOT NULL
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_paper_snapshots_user ON paper_snapshots(username)"
    )
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_viewers (
            owner_username TEXT NOT NULL,
            viewer_username TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (owner_username, viewer_username)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_completions (
            username TEXT NOT NULL,
            module_id TEXT NOT NULL,
            completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (username, module_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_daily_completions (
            username TEXT NOT NULL,
            module_id TEXT NOT NULL,
            completion_date TEXT NOT NULL,
            PRIMARY KEY (username, module_id, completion_date)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_learning_daily_user_date
        ON learning_daily_completions(username, completion_date)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_daily_bonus (
            username TEXT NOT NULL,
            bonus_date TEXT NOT NULL,
            PRIMARY KEY (username, bonus_date)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            username TEXT PRIMARY KEY,
            display_name TEXT,
            bio TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_user, to_user)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user_a TEXT NOT NULL,
            user_b TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_a, user_b)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_members (
            room_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (room_id, username)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room_id, id)"
    )

    for col_sql in (
        "ALTER TABLE chat_messages ADD COLUMN attachment_storage TEXT",
        "ALTER TABLE chat_messages ADD COLUMN attachment_mime TEXT",
        "ALTER TABLE chat_messages ADD COLUMN attachment_orig_name TEXT",
    ):
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    db.commit()
    db.close()

    try:
        paper_service.backfill_paper_accounts_for_existing_users()
    except Exception:
        pass
    try:
        social_service.ensure_global_room()
    except Exception:
        pass


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


@app.template_filter("fmt_money")
def fmt_money_filter(n):
    if n is None:
        return "—"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x:,.2f}"


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

    paper_service.ensure_paper_account(signup_username)

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


def _extract_possible_symbols(text: str) -> list[str]:
    raw = re.findall(r"\b[A-Za-z\^\.\-]{1,10}\b", (text or ""))
    skip = {
        "A",
        "AN",
        "AND",
        "ARE",
        "AS",
        "AT",
        "BE",
        "FOR",
        "FROM",
        "GET",
        "HAS",
        "HAVE",
        "HOW",
        "IN",
        "IS",
        "IT",
        "ME",
        "MY",
        "OF",
        "ON",
        "OR",
        "SHOW",
        "TELL",
        "THE",
        "TO",
        "US",
        "WHAT",
        "WITH",
        "YOU",
    }
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw:
        s = tok.strip().upper()
        if not s or s in skip:
            continue
        if not SYMBOL_RE.match(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 4:
            break
    return out


def _build_ai_chat_context(username: str, latest_user_text: str) -> str:
    lines: list[str] = [f"Current signed-in user: {username}"]

    try:
        st = paper_service.get_portfolio_state(username)
        lines.append("Portfolio snapshot:")
        lines.append(
            f"- Total value: {st.get('total_value')} | Cash: {st.get('cash')} | "
            f"Unrealized P/L: {st.get('unrealized_pl')} | Total P/L: {st.get('total_pl')}"
        )
        poss = st.get("positions") or []
        if poss:
            lines.append("- Top positions:")
            for p in poss[:6]:
                lines.append(
                    f"  - {p.get('symbol')}: shares={p.get('shares')}, last={p.get('last')}, "
                    f"market_value={p.get('market_value')}, unrealized_pl={p.get('unrealized_pl')}"
                )
        else:
            lines.append("- No open positions.")
    except Exception:
        lines.append("Portfolio snapshot unavailable.")

    try:
        wl_syms = _watchlist_symbols(username)[:8]
        if wl_syms:
            wl_quotes = market_service.fetch_quotes_for_symbols(wl_syms, with_mcap=False)
            if wl_quotes:
                lines.append("Watchlist quotes:")
                for q in wl_quotes:
                    lines.append(
                        f"- {q.get('symbol')}: price={q.get('price')}, change_pct={q.get('change_pct')}"
                    )
    except Exception:
        lines.append("Watchlist quote snapshot unavailable.")

    try:
        requested_syms = _extract_possible_symbols(latest_user_text)
        if requested_syms:
            lines.append("Requested ticker quotes:")
            for sym in requested_syms:
                q = market_service.fetch_quote(sym, with_mcap=True)
                if not q:
                    lines.append(f"- {sym}: unavailable")
                    continue
                lines.append(
                    f"- {q.get('symbol')}: name={q.get('name')}, price={q.get('price')}, "
                    f"change_pct={q.get('change_pct')}, volume={q.get('volume')}, "
                    f"market_cap={q.get('market_cap')}"
                )
    except Exception:
        lines.append("Requested ticker quote lookup unavailable.")

    try:
        news = market_service.fetch_market_news(8)
        if news:
            lines.append("Recent market headlines:")
            lines.append(market_service.format_market_news_for_ai(news, 8))
    except Exception:
        lines.append("Market headlines unavailable.")

    return "\n".join(lines)


# -------- DASHBOARD (MARKET OVERVIEW) --------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect("/?message=" + quote("Please sign in to open the dashboard."))

    welcome = request.args.get("welcome") == "1"
    wl_syms = _watchlist_symbols(user)
    # Parallelize independent Yahoo pulls only. fetch_movers + fetch_trending_by_volume share one
    # underlying universe (_mover_universe_rows); running those in parallel doubles Yahoo load and
    # races the cache → empty movers/trending and rate limits.
    indexes: list = []
    news: list = []
    watchlist: list = []
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_ix = pool.submit(market_service.fetch_indexes)
            fut_news = pool.submit(market_service.fetch_market_news, 16)
            fut_wl = pool.submit(market_service.fetch_quotes_for_symbols, wl_syms)
            try:
                indexes = fut_ix.result()
            except Exception:
                indexes = []
            try:
                news = fut_news.result()
            except Exception:
                news = []
            try:
                watchlist = fut_wl.result()
            except Exception:
                watchlist = []
    except Exception:
        indexes, news, watchlist = [], [], []

    try:
        gainers, losers = market_service.fetch_movers()
    except Exception:
        gainers, losers = [], []
    try:
        trending = market_service.fetch_trending_by_volume()
    except Exception:
        trending = []

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
    paper_service.ensure_paper_account(user)
    paper_service.seed_initial_snapshot(user)
    return render_template(
        "portfolio.html",
        username=user,
        portfolio_owner=user,
        read_only=False,
        info_message=request.args.get("message", "").strip(),
    )


@app.route("/portfolio/view/<path:owner_username>")
def portfolio_view_friend(owner_username):
    """Read-only portfolio for a friend (or yourself → /portfolio)."""
    viewer = current_user()
    if not viewer:
        return redirect("/?message=" + quote("Please sign in to view portfolios."))
    owner = (owner_username or "").strip()
    if not owner:
        return redirect("/portfolio")
    if owner == viewer:
        return redirect("/portfolio")
    if not paper_service.can_view_portfolio(viewer, owner):
        return redirect(
            "/portfolio?message="
            + quote("You can only view portfolios of users who are your friends.")
        )
    paper_service.ensure_paper_account(owner)
    return render_template(
        "portfolio.html",
        username=viewer,
        portfolio_owner=owner,
        read_only=True,
        info_message="",
    )


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
    return render_template(
        "learning.html",
        username=user,
        ai_learning_ready=ai_service.is_configured(),
        learning_bonus_usd=learning_service.DAILY_ALL_BONUS,
        learning_reward_usd=learning_service.REWARD_PER_MODULE,
        learning_module_count=learning_service.MODULE_COUNT,
    )


@app.route("/api/learning/state", methods=["GET"])
@login_required_json
def api_learning_state():
    me = current_user()
    assert me
    return jsonify(learning_service.get_state(me))


@app.route("/api/learning/module/<path:module_id>", methods=["GET"])
@login_required_json
def api_learning_module_detail(module_id: str):
    m = learning_service.get_module_for_client(module_id)
    if not m:
        return jsonify({"error": "Unknown module"}), 404
    return jsonify({"module": m})


@app.route("/api/learning/quiz", methods=["POST"])
@login_required_json
def api_learning_quiz_submit():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    mid = (body.get("module_id") or "").strip()
    quiz_id = (body.get("quiz_id") or "").strip()
    answers = body.get("answers")
    if not isinstance(answers, list):
        return jsonify({"error": "answers must be a list of choice indices"}), 400
    ok, msg, payload = learning_service.submit_quiz(me, mid, answers, quiz_id=quiz_id)
    if not ok:
        out = {"error": msg}
        if payload:
            out.update(payload)
        return jsonify(out), 400
    pf = paper_service.get_portfolio_state(me)
    out = dict(payload)
    out["message"] = msg
    out["portfolio"] = pf
    return jsonify(out)


@app.route("/api/learning/generate_quiz", methods=["POST"])
@login_required_json
def api_learning_generate_quiz():
    me = current_user()
    assert me
    if not ai_service.is_configured():
        return jsonify({"error": "OpenAI is not configured."}), 400
    body = request.get_json(silent=True) or {}
    mid = (body.get("module_id") or "").strip()
    ok, msg, payload = learning_service.generate_ai_quiz_for_user(
        me, mid, question_count=10
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify(payload)


@app.route("/api/learning/ai_summary", methods=["POST"])
@login_required_json
def api_learning_ai_summary():
    body = request.get_json(silent=True) or {}
    mid = (body.get("module_id") or "").strip()
    outline = learning_service.ai_outline_for_module(mid)
    if not outline:
        return jsonify({"error": "Unknown module"}), 404
    m = learning_service.get_module_for_client(mid)
    title = (m.get("title") if m else "") or mid
    text, err = ai_service.generate_learning_summary(title, outline)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"summary": text or ""})


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
    latest_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            latest_user_text = str(m.get("content") or "")
            break
    me = current_user()
    assert me
    ctx = _build_ai_chat_context(me, latest_user_text)
    text, err = ai_service.chat_reply(messages, context_text=ctx)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"reply": text})


# -------- API: PAPER TRADING --------
def _paper_resolve_target(path_username: str | None) -> tuple[str | None, str | None]:
    """Return (target_username, error_message). error set if not allowed."""
    me = current_user()
    if not me:
        return None, "Unauthorized"
    if not path_username or path_username.strip() == "":
        return me, None
    target = path_username.strip()
    if target == me:
        return me, None
    if paper_service.can_view_portfolio(me, target):
        return target, None
    return None, "Forbidden"


@app.route("/api/paper/state", methods=["GET"])
@login_required_json
def api_paper_state():
    me = current_user()
    assert me
    paper_service.ensure_paper_account(me)
    st = paper_service.get_portfolio_state(me)
    snaps = paper_service.get_snapshots(me, 120)
    return jsonify(
        {
            "portfolio": st,
            "snapshots": snaps,
            "read_only": False,
            "owner": me,
            "learning_rewards": {
                "per_module_usd": learning_service.REWARD_PER_MODULE,
                "daily_all_bonus_usd": learning_service.DAILY_ALL_BONUS,
                "module_count": learning_service.MODULE_COUNT,
            },
        }
    )


@app.route("/api/paper/state/<path:username>", methods=["GET"])
@login_required_json
def api_paper_state_user(username):
    target, err = _paper_resolve_target(username)
    if err:
        code = 401 if err == "Unauthorized" else 403
        return jsonify({"error": err}), code
    assert target
    paper_service.ensure_paper_account(target)
    st = paper_service.get_portfolio_state(target)
    snaps = paper_service.get_snapshots(target, 120)
    me = current_user()
    return jsonify(
        {
            "portfolio": st,
            "snapshots": snaps,
            "read_only": me != target,
            "owner": target,
            "learning_rewards": {},
        }
    )


@app.route("/api/paper/transactions", methods=["GET"])
@login_required_json
def api_paper_transactions():
    me = current_user()
    assert me
    rows = paper_service.list_transactions(me, 100)
    return jsonify({"transactions": rows})


@app.route("/api/paper/transactions/<path:username>", methods=["GET"])
@login_required_json
def api_paper_transactions_user(username):
    target, err = _paper_resolve_target(username)
    if err:
        code = 401 if err == "Unauthorized" else 403
        return jsonify({"error": err}), code
    assert target
    rows = paper_service.list_transactions(target, 100)
    return jsonify({"transactions": rows})


@app.route("/api/paper/buy", methods=["POST"])
@login_required_json
def api_paper_buy():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    sym = (body.get("symbol") or "").strip()
    try:
        shares = float(body.get("shares"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid shares"}), 400
    ok, msg, st = paper_service.buy(me, sym, shares)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "portfolio": st})


@app.route("/api/paper/sell", methods=["POST"])
@login_required_json
def api_paper_sell():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    sym = (body.get("symbol") or "").strip()
    try:
        shares = float(body.get("shares"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid shares"}), 400
    ok, msg, st = paper_service.sell(me, sym, shares)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "portfolio": st})


@app.route("/api/paper/leaderboard", methods=["GET"])
@login_required_json
def api_paper_leaderboard():
    rows = paper_service.leaderboard(30)
    return jsonify({"leaderboard": rows})


@app.route("/api/paper/viewers", methods=["GET"])
@login_required_json
def api_paper_viewers_get():
    me = current_user()
    assert me
    return jsonify({"viewers": paper_service.list_viewers(me)})


@app.route("/api/paper/viewers", methods=["POST"])
@login_required_json
def api_paper_viewers_post():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    v = (body.get("username") or "").strip()
    ok, msg = paper_service.add_viewer(me, v)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "viewers": paper_service.list_viewers(me)})


@app.route("/api/paper/viewers/<path:viewer_username>", methods=["DELETE"])
@login_required_json
def api_paper_viewers_delete(viewer_username):
    me = current_user()
    assert me
    if paper_service.remove_viewer(me, viewer_username):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@app.route("/api/paper/claim_module", methods=["POST"])
@login_required_json
def api_paper_claim_module():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    mid = (body.get("module_id") or "").strip()
    ok, msg = paper_service.claim_module_reward(me, mid)
    if not ok:
        return jsonify({"error": msg}), 400
    st = paper_service.get_portfolio_state(me)
    return jsonify({"ok": True, "message": msg, "portfolio": st})


# -------- API: CHAT & SOCIAL --------
@app.route("/api/social/bootstrap", methods=["GET"])
@login_required_json
def api_social_bootstrap():
    me = current_user()
    assert me
    social_service.ensure_profile(me)
    return jsonify(
        {
            "profile": social_service.get_profile(me),
            "rooms": social_service.list_user_rooms(me),
            "friends": social_service.list_friends(me),
            "incoming_requests": social_service.list_incoming_requests(me),
            "outgoing_requests": social_service.list_outgoing_requests(me),
        }
    )


@app.route("/api/social/profile", methods=["PUT"])
@login_required_json
def api_social_profile_put():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    prof = social_service.update_profile(
        me,
        body.get("display_name"),
        body.get("bio"),
    )
    return jsonify({"profile": prof})


@app.route("/api/social/profile/<path:username>", methods=["GET"])
@login_required_json
def api_social_profile_get(username):
    me = current_user()
    assert me
    target = (username or "").strip()
    if not target:
        return jsonify({"error": "Invalid"}), 400
    if not social_service.user_exists(target):
        return jsonify({"error": "User not found"}), 404
    return jsonify(
        {
            "profile": social_service.get_profile(target),
            "learning": learning_service.completion_stats(target),
            "is_friend": social_service.are_friends(me, target),
            "can_view_portfolio": paper_service.can_view_portfolio(me, target),
        }
    )


@app.route("/api/social/friends/request", methods=["POST"])
@login_required_json
def api_social_friend_request():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    to_u = (body.get("to_username") or "").strip()
    ok, msg = social_service.send_friend_request(me, to_u)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True})


@app.route("/api/social/friends/respond", methods=["POST"])
@login_required_json
def api_social_friend_respond():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    from_u = (body.get("from_username") or "").strip()
    accept = bool(body.get("accept"))
    ok, msg = social_service.respond_friend_request(me, from_u, accept)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True})


@app.route("/api/social/dm", methods=["POST"])
@login_required_json
def api_social_dm():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    other = (body.get("with_username") or "").strip()
    rid, msg = social_service.get_or_create_dm_room(me, other)
    if rid is None:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "room_id": rid})


@app.route("/api/social/groups", methods=["POST"])
@login_required_json
def api_social_group_create():
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    raw_members = body.get("member_usernames") or body.get("members") or []
    if not isinstance(raw_members, list):
        raw_members = []
    member_usernames = [str(x).strip() for x in raw_members if str(x).strip()]
    rid, msg = social_service.create_group_with_members(me, name, member_usernames)
    if rid is None:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "room_id": rid})


@app.route("/api/social/groups/<int:room_id>/invite", methods=["POST"])
@login_required_json
def api_social_group_invite(room_id):
    me = current_user()
    assert me
    body = request.get_json(silent=True) or {}
    invitee = (body.get("username") or "").strip()
    ok, msg = social_service.add_group_member(room_id, me, invitee)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True})


@app.route("/api/social/room/<int:room_id>/messages", methods=["GET"])
@login_required_json
def api_social_messages_get(room_id):
    me = current_user()
    assert me
    raw_after = (request.args.get("after_id") or "").strip()
    after_id: int | None = int(raw_after) if raw_after.isdigit() else None
    msgs, err = social_service.list_messages(room_id, me, after_id=after_id, limit=100)
    if err:
        return jsonify({"error": err}), 403
    return jsonify({"messages": msgs})


@app.route("/api/social/room/<int:room_id>/messages", methods=["POST"])
@login_required_json
def api_social_messages_post(room_id):
    me = current_user()
    assert me
    storage_key = None
    mime = None
    orig_name = None
    text = ""

    ct = (request.content_type or "").lower()
    if "multipart/form-data" in ct:
        text = (request.form.get("body") or "").strip()
        up = request.files.get("file")
        if up and up.filename:
            raw = up.read()
            mime = (up.mimetype or "").split(";")[0].strip().lower()
            orig_name = (up.filename or "file")[:200]
            key, err = social_service.save_chat_attachment(
                raw, mime, up.filename or ""
            )
            if err:
                return jsonify({"error": err}), 400
            storage_key = key
    else:
        body = request.get_json(silent=True) or {}
        text = (body.get("body") or "").strip()

    ok, msg, mid = social_service.post_message(
        me,
        room_id,
        text,
        attachment_storage=storage_key,
        attachment_mime=mime,
        attachment_orig_name=orig_name,
    )
    if not ok:
        code = 403 if "cannot" in msg.lower() else 400
        return jsonify({"error": msg}), code
    return jsonify({"ok": True, "id": mid})


@app.route("/api/social/media/<int:message_id>")
def api_social_media(message_id):
    """Serve chat attachment only if logged in and allowed in that room."""
    me = current_user()
    if not me:
        abort(401)
    data = social_service.get_message_attachment(message_id)
    if not data:
        abort(404)
    room_id, mime, path, download_name = data
    if not social_service.can_access_room(me, room_id):
        abort(403)
    try:
        return send_file(
            path,
            mimetype=mime or "application/octet-stream",
            as_attachment=False,
            download_name=download_name or None,
        )
    except OSError:
        abort(404)


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
