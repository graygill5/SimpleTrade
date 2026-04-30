"""
Learning modules: daily-reset progress, quizzes, paper-trading rewards.
Calendar day = server local date (YYYY-MM-DD). Does not touch market/Yahoo code.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import date, timedelta
from typing import Any

import ai_service
import paper_service as ps

DB_PATH = ps.DB_PATH

REWARD_PER_MODULE = 10_000.0
DAILY_ALL_BONUS = 50_000.0

# --------- Module catalog (quiz answers stay server-side only) ---------


def _q(text: str, choices: tuple[str, str, str, str], correct: int) -> dict[str, Any]:
    return {"question": text, "choices": list(choices), "correct": int(correct)}


_MODULES: list[dict[str, Any]] = [
    {
        "id": "stocks_equities",
        "title": "Stocks & equity basics",
        "tagline": "What owning a share really means.",
        "icon": "Module 1",
        "lessons": [
            "A **stock** (share) is a fraction of ownership in a company. Public companies split ownership into shares that trade on exchanges.",
            "**Common stock** usually brings voting rights and participation in dividends if the board declares them. Prices move with expectations about future profits and risk.",
            "**Liquidity** matters: large names often trade heavily; small caps can gap or widen spreads. Past performance does not guarantee future returns.",
            "Retail investors typically buy/sell through brokers; execution quality (speed, fills) interacts with **order types** you'll see in later modules.",
        ],
        "quiz": [
            _q(
                "Owning one share of common stock generally represents:",
                (
                    "A loan you must repay with interest",
                    "A fractional ownership claim on the company",
                    "A guaranteed coupon payment",
                    "Insurance against market losses",
                ),
                1,
            ),
            _q(
                "Stock prices move mainly because markets reassess:",
                (
                    "Only yesterday's closing price",
                    "Future prospects, risk, and supply/demand — not a single fixed formula",
                    "Government-fixed fair values",
                    "The company's street address",
                ),
                1,
            ),
            _q(
                "Dividends on common stock are:",
                (
                    "Mandatory every quarter for all stocks",
                    "Optional payouts declared by the board — not guaranteed",
                    "The same as bond interest",
                    "Always higher than inflation",
                ),
                1,
            ),
            _q(
                "Liquidity loosely refers to:",
                (
                    "How much water the company drinks",
                    "How easily shares can trade without moving price sharply",
                    "The CEO's salary",
                    "Annual revenue only",
                ),
                1,
            ),
        ],
    },
    {
        "id": "etfs_index_funds",
        "title": "ETFs & index funds",
        "tagline": "Bundles, tracking error, and costs.",
        "icon": "Module 2",
        "lessons": [
            "An **ETF** trades intraday like a stock and usually tracks an index or theme. **Index mutual funds** price once daily and often track similar benchmarks.",
            "**Expense ratios** and tracking differences matter — small fees compound. Some ETFs use derivatives; read the prospectus for niche products.",
            "ETFs can trade at premiums/discounts to NAV in stress; most liquid equity ETFs stay close to fair value intraday.",
        ],
        "quiz": [
            _q(
                "Compared to picking single stocks, a broad index ETF often:",
                (
                    "Eliminates all investment risk",
                    "Offers diversified exposure to a benchmark (still has market risk)",
                    "Guarantees beating active managers every year",
                    "Removes the need for any research",
                ),
                1,
            ),
            _q(
                "Expense ratio primarily reflects:",
                (
                    "Your broker commission only",
                    "Fund operating costs expressed as an annual percentage of assets",
                    "Federal income tax bracket",
                    "How many tweets mention the ticker",
                ),
                1,
            ),
            _q(
                "ETFs vs classic open-end mutual funds — a typical difference:",
                (
                    "ETFs never hold stocks",
                    "ETFs often trade continuously on exchange; many mutual funds price once per day",
                    "Mutual funds cannot track indexes",
                    "They are legally identical in every jurisdiction",
                ),
                1,
            ),
            _q(
                "Tracking error refers to:",
                (
                    "GPS accuracy of headquarters",
                    "How closely a fund follows its stated benchmark",
                    "Only tax reporting delays",
                    "CEO travel expenses",
                ),
                1,
            ),
        ],
    },
    {
        "id": "risk_and_return",
        "title": "Risk & return",
        "tagline": "Volatility, drawdowns, and realistic expectations.",
        "icon": "Module 3",
        "lessons": [
            "**Risk** includes losing principal; higher expected long-run returns usually pair with higher uncertainty.",
            "**Volatility** (swings up/down) is not the only risk — liquidity, concentration, and behavioral mistakes matter too.",
            "Diversification spreads idiosyncratic risk but **cannot eliminate** broad market risk.",
        ],
        "quiz": [
            _q(
                "Historically, assets with higher expected long-run returns often exhibit:",
                (
                    "Zero volatility",
                    "More return uncertainty / bigger swings",
                    "Government insurance of losses",
                    "Fixed monthly payouts like a CD",
                ),
                1,
            ),
            _q(
                "If you hold one stock, a major company-specific setback is mainly:",
                (
                    "Systematic market risk only",
                    "Concentration / idiosyncratic risk",
                    "Inflation risk only",
                    "Currency risk only",
                ),
                1,
            ),
            _q(
                "Diversification across many stocks primarily helps with:",
                (
                    "Removing market crashes entirely",
                    "Spreading company-specific shocks so no single name dominates outcomes",
                    "Guaranteeing profits",
                    "Avoiding all taxes",
                ),
                1,
            ),
            _q(
                "A deep portfolio drawdown means:",
                (
                    "Only a one-day glitch",
                    "A peak-to-trough decline in value — can take time to recover",
                    "Automatic liquidation",
                    "Tax-free withdrawal",
                ),
                1,
            ),
        ],
    },
    {
        "id": "diversification",
        "title": "Diversification",
        "tagline": "Spreading bets without di-worsifying.",
        "icon": "Module 4",
        "lessons": [
            "Owning many imperfectly correlated assets can **lower portfolio volatility** without necessarily sacrificing expected return — same market risk remains.",
            "Adding highly correlated bets doesn't diversify much; seek **different drivers** (sectors, styles, geographies where appropriate).",
            "Too many overlapping funds can **di-worsify** — duplicate exposures and fees.",
        ],
        "quiz": [
            _q(
                "Effective diversification aims to:",
                (
                    "Eliminate all losses forever",
                    "Reduce reliance on any single company's outcome while accepting market risk",
                    "Buy only one ETF forever",
                    "Match the CEO's portfolio",
                ),
                1,
            ),
            _q(
                "Two stocks in the same narrow industry often have returns that are:",
                (
                    "Perfectly uncorrelated always",
                    "Fairly correlated — diversified less than pairing different sectors",
                    "Impossible to compare",
                    "Always negatively correlated",
                ),
                1,
            ),
            _q(
                "\"Di-worsification\" humorously warns against:",
                (
                    "Owning index funds",
                    "Owning many funds that overlap and charge layered fees without new exposures",
                    "Reading annual reports",
                    "Using limit orders",
                ),
                1,
            ),
            _q(
                "Market risk (beta) after broad diversification:",
                (
                    "Disappears completely",
                    "Typically remains — you still ride the overall market",
                    "Becomes illegal",
                    "Equals your cash balance only",
                ),
                1,
            ),
        ],
    },
    {
        "id": "orders_execution",
        "title": "Orders & execution",
        "tagline": "Market vs limit — what you're asking the market to do.",
        "icon": "Module 5",
        "lessons": [
            "**Market orders** prioritize speed of fill; price can slip in fast tape.",
            "**Limit orders** cap buy price or floor sell price — may not fill if market never reaches your level.",
            "Extended hours can have wider spreads and lower liquidity — fills differ from regular session.",
        ],
        "quiz": [
            _q(
                "A market order generally:",
                (
                    "Guarantees your exact limit price",
                    "Prioritizes immediate execution subject to available liquidity",
                    "Only works for bonds",
                    "Cannot be placed in equities",
                ),
                1,
            ),
            _q(
                "A buy limit order executes when:",
                (
                    "The broker feels like it",
                    "The security trades at or below your limit (and your order is eligible)",
                    "The CEO tweets",
                    "Never — limits are cosmetic",
                ),
                1,
            ),
            _q(
                "During fast markets, slippage means:",
                (
                    "Guaranteed profit",
                    "Actual fill price may differ from the last quoted price you saw",
                    "Zero trading volume",
                    "Automatic cancellation",
                ),
                1,
            ),
            _q(
                "After-hours sessions often feature:",
                (
                    "Perfect liquidity always",
                    "Different liquidity/spreads vs regular hours — surprises possible",
                    "Banned retail trading",
                    "Fixed prices",
                ),
                1,
            ),
        ],
    },
    {
        "id": "bid_ask_spreads",
        "title": "Bid/ask & spreads",
        "tagline": "Where trades actually happen.",
        "icon": "Module 6",
        "lessons": [
            "**Bid** is what buyers pay; **ask** is what sellers demand. The gap is the **spread**.",
            "Wider spreads often mean thinner liquidity — your effective cost rises when you cross the spread.",
            "Mid-price quotes can mislead — **crossing** the spread pays the ask when buying.",
        ],
        "quiz": [
            _q(
                "You buy at the:",
                (
                    "Bid price typically",
                    "Ask (offer) price when lifting from the book",
                    "Average of GDP growth",
                    "Prior day's low only",
                ),
                1,
            ),
            _q(
                "A wide bid/ask spread often signals:",
                (
                    "Guaranteed arbitrage for retail",
                    "Weaker liquidity / higher implicit trading cost",
                    "Free commissions forever",
                    "Insider buying only",
                ),
                1,
            ),
            _q(
                "The mid-quote between bid and ask:",
                (
                    "Is always where your market order fills",
                    "May differ from your actual fill when you cross the spread",
                    "Is illegal to publish",
                    "Equals NAV for all stocks",
                ),
                1,
            ),
            _q(
                "Spread cost matters most when:",
                (
                    "You never trade",
                    "You trade frequently or in size relative to liquidity",
                    "You only read news",
                    "You hold cash only",
                ),
                1,
            ),
        ],
    },
    {
        "id": "market_news",
        "title": "Reading market news",
        "tagline": "Headlines move sentiment — verify and stay calm.",
        "icon": "Module 7",
        "lessons": [
            "News can be **noisy**, late, or sensational. Cross-check material facts; distinguish opinion from data.",
            "Short-term price jumps on headlines often **mean-revert** after detail emerges — avoid panic trades.",
            "Macro prints (jobs, CPI) hit broad indices; single-stock news hits that issuer hardest.",
        ],
        "quiz": [
            _q(
                "A sensational headline without confirmed sources should:",
                (
                    "Trigger instant max leverage trades",
                    "Prompt caution — verify before acting size",
                    "Always predict next week's price",
                    "Replace fundamental analysis entirely",
                ),
                1,
            ),
            _q(
                "Macroeconomic data releases often influence:",
                (
                    "Only one penny stock",
                    "Broad indices and interest-rate expectations",
                    "Sports scores",
                    "Weather only",
                ),
                1,
            ),
            _q(
                "Short-term price spikes on breaking news sometimes:",
                (
                    "Guarantee long-term trends",
                    "Fade as details emerge and liquidity returns",
                    "Prove technical analysis useless",
                    "Suspend exchange rules",
                ),
                1,
            ),
            _q(
                "Opinion columns vs filed financial statements:",
                (
                    "Are identical legally",
                    "Carry different standards — filings have formal reporting rules",
                    "Cannot mention stocks",
                    "Always predict earnings",
                ),
                1,
            ),
        ],
    },
    {
        "id": "portfolio_basics",
        "title": "Portfolio basics",
        "tagline": "Allocation, review, rebalance concepts.",
        "icon": "Module 8",
        "lessons": [
            "**Allocation** is how you split money across stocks/bonds/cash/etc. Match time horizon and tolerance — not generic advice here.",
            "**Rebalancing** trims winners and tops losers on a schedule to stay near policy weights — can feel wrong emotionally.",
            "Costs and taxes (in real accounts) interact with turnover — paper trading ignores tax but not the lesson.",
        ],
        "quiz": [
            _q(
                "A strategic asset allocation primarily reflects:",
                (
                    "Yesterday's meme ticker",
                    "Goals, time horizon, and risk tolerance — reviewed periodically",
                    "Guaranteed returns",
                    "Broker marketing only",
                ),
                1,
            ),
            _q(
                "Rebalancing on a schedule tends to:",
                (
                    "Always maximize short-run performance",
                    "Trade toward target weights — sometimes selling strength and buying laggards",
                    "Eliminate diversification",
                    "Avoid all fees",
                ),
                1,
            ),
            _q(
                "Paper trading cannot fully simulate:",
                (
                    "Order types",
                    "Taxes, slippage nuances, and emotional pressure of real capital",
                    "Ticker symbols",
                    "Charts",
                ),
                1,
            ),
            _q(
                "High turnover generally:",
                (
                    "Has zero cost impact",
                    "Raises explicit and implicit costs vs buy-and-hold indexes",
                    "Is required for diversification",
                    "Eliminates volatility",
                ),
                1,
            ),
        ],
    },
    {
        "id": "trading_psychology",
        "title": "Trading psychology",
        "tagline": "Plans, discipline, avoiding revenge trades.",
        "icon": "Module 9",
        "lessons": [
            "**FOMO** and **revenge trading** after losses often enlarge mistakes. Predefine risk per trade and walk away at limits.",
            "Keeping a simple **journal** (why in/out) beats relying on memory after emotions spike.",
            "Good process beats lucky streaks — streaks **regress**.",
        ],
        "quiz": [
            _q(
                "Revenge trading refers to:",
                (
                    "Closing winners quickly",
                    "Increasing risk impulsively after a loss to 'get even'",
                    "Using limit orders",
                    "Reading earnings reports",
                ),
                1,
            ),
            _q(
                "A written trading plan helps mainly by:",
                (
                    "Guaranteeing profits",
                    "Creating rules before emotions spike in the moment",
                    "Eliminating market risk",
                    "Replacing capital",
                ),
                1,
            ),
            _q(
                "FOMO-driven entries often:",
                (
                    "Always improve average prices",
                    "Chase after moves already occurred — worse risk/reward",
                    "Remove volatility",
                    "Are required for diversification",
                ),
                1,
            ),
            _q(
                "Journaling trades can reveal:",
                (
                    "Nothing useful",
                    "Patterns in your behavior and rule breaks over time",
                    "Future prices with certainty",
                    "Insider data",
                ),
                1,
            ),
        ],
    },
    {
        "id": "regulations_basics",
        "title": "Rules & account basics",
        "tagline": "High-level U.S. retail concepts — not legal advice.",
        "icon": "Module 10",
        "lessons": [
            "Regulators require **risk disclosures**; pattern-day-trader rules affect margin accounts under U.S. rules — details vary by broker and region.",
            "**Insider trading** laws restrict trading on material nonpublic information — entertainment ≠ research.",
            "This app is educational; consult professionals for your situation.",
        ],
        "quiz": [
            _q(
                "Material nonpublic information used to trade individual stocks can raise:",
                (
                    "No issues ever",
                    "Serious legal concerns under insider-trading regimes",
                    "Automatic profits",
                    "Tax credits only",
                ),
                1,
            ),
            _q(
                "Pattern Day Trader rules (U.S., margin context) broadly aim to:",
                (
                    "Ban all retail investing",
                    "Address risks of frequent day trading with leverage — specifics depend on rules & broker",
                    "Guarantee free trades",
                    "Apply only to bonds",
                ),
                1,
            ),
            _q(
                "Educational simulators like paper trading:",
                (
                    "Perfectly replicate taxes and all regulations",
                    "Help practice mechanics but omit many real-world frictions",
                    "Replace licensed advice",
                    "Provide investment advice tailored to you",
                ),
                1,
            ),
            _q(
                "Brokerage disclosures exist because:",
                (
                    "Marketing only",
                    "Investors must understand risks, fees, and conflicts — regulations require transparency",
                    "They replace contracts",
                    "They guarantee returns",
                ),
                1,
            ),
        ],
    },
]

MODULE_COUNT = len(_MODULES)
AI_QUIZ_TTL_SEC = 60 * 45
_AI_QUIZ_STORE: dict[str, dict[str, Any]] = {}


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def today_iso() -> str:
    return date.today().isoformat()


def all_module_ids() -> list[str]:
    return [m["id"] for m in _MODULES]


def _by_id(mid: str) -> dict[str, Any] | None:
    for m in _MODULES:
        if m["id"] == mid:
            return m
    return None


def get_module_for_client(module_id: str) -> dict[str, Any] | None:
    m = _by_id(module_id)
    if not m:
        return None
    return {
        "id": m["id"],
        "title": m["title"],
        "tagline": m["tagline"],
        "icon": m["icon"],
        "lessons": m["lessons"],
        "questions": [
            {"question": q["question"], "choices": q["choices"]} for q in m["quiz"]
        ],
    }


def list_modules_summary_for_user(username: str) -> list[dict[str, Any]]:
    d = today_iso()
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT module_id FROM learning_daily_completions
        WHERE username=? AND completion_date=?
        """,
        (username, d),
    )
    done = {row[0] for row in cur.fetchall()}
    db.close()
    out = []
    for m in _MODULES:
        mid = m["id"]
        out.append(
            {
                "id": mid,
                "title": m["title"],
                "tagline": m["tagline"],
                "icon": m["icon"],
                "completed_today": mid in done,
                "reward_usd": REWARD_PER_MODULE,
            }
        )
    return out


def get_state(username: str) -> dict[str, Any]:
    d = today_iso()
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT module_id FROM learning_daily_completions
        WHERE username=? AND completion_date=?
        """,
        (username, d),
    )
    done_today = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT 1 FROM learning_daily_bonus WHERE username=? AND bonus_date=?",
        (username, d),
    )
    bonus_gone = cur.fetchone() is not None
    db.close()

    n_mod = len(_MODULES)
    completed_count = len(done_today)
    all_done = completed_count >= n_mod and n_mod > 0

    return {
        "calendar_date": d,
        "reward_per_module_usd": REWARD_PER_MODULE,
        "daily_all_complete_bonus_usd": DAILY_ALL_BONUS,
        "module_count": n_mod,
        "completed_today_count": completed_count,
        "completed_module_ids_today": sorted(done_today),
        "bonus_claimed_today": bonus_gone,
        "all_modules_completed_today": all_done,
        "modules": list_modules_summary_for_user(username),
    }


def _grade(module_id: str, answers: list[int]) -> tuple[bool, str]:
    m = _by_id(module_id)
    if not m:
        return False, "Unknown module."
    qs = m["quiz"]
    if len(answers) != len(qs):
        return False, f"Expected {len(qs)} answers."
    for i, ans in enumerate(answers):
        try:
            a = int(ans)
        except (TypeError, ValueError):
            return False, "Answers must be integers (choice index)."
        if a < 0 or a > 3:
            return False, "Invalid choice index."
        if a != qs[i]["correct"]:
            return False, f"Question {i + 1} is incorrect. Review the lesson and try again."
    return True, "ok"


def _make_ai_quiz_key(username: str, module_id: str) -> str:
    return f"{username}::{module_id}"


def _cleanup_ai_quiz_store() -> None:
    now = time.time()
    stale = [
        k
        for k, v in _AI_QUIZ_STORE.items()
        if now - float(v.get("created_at_ts") or 0.0) > AI_QUIZ_TTL_SEC
    ]
    for k in stale:
        _AI_QUIZ_STORE.pop(k, None)


def generate_ai_quiz_for_user(
    username: str, module_id: str, question_count: int = 10
) -> tuple[bool, str, dict[str, Any]]:
    m = _by_id(module_id)
    if not m:
        return False, "Unknown module.", {}
    _cleanup_ai_quiz_store()
    quiz_rows, err = ai_service.generate_learning_quiz(
        m["title"], "\n".join(m["lessons"]), question_count=question_count
    )
    if err or not quiz_rows:
        return False, err or "Could not generate quiz.", {}

    quiz_id = uuid.uuid4().hex
    _AI_QUIZ_STORE[_make_ai_quiz_key(username, module_id)] = {
        "quiz_id": quiz_id,
        "created_at_ts": time.time(),
        "questions": quiz_rows,
    }
    return True, "ok", {
        "quiz_id": quiz_id,
        "questions": [
            {"question": q["question"], "choices": q["choices"]} for q in quiz_rows
        ],
    }


def _grade_ai_quiz(
    username: str, module_id: str, quiz_id: str, answers: list[int]
) -> tuple[bool, str, dict[str, Any]]:
    _cleanup_ai_quiz_store()
    rec = _AI_QUIZ_STORE.get(_make_ai_quiz_key(username, module_id))
    if not rec:
        return False, "Generate a new quiz for this module first.", {}
    if rec.get("quiz_id") != quiz_id:
        return False, "Quiz session expired. Generate a new quiz.", {}
    qs = rec.get("questions") or []
    if len(answers) != len(qs):
        return False, f"Expected {len(qs)} answers.", {}
    incorrect: list[int] = []
    correct_indices: list[int] = []
    for i, q in enumerate(qs):
        ci = int(q.get("correct_index", -1))
        correct_indices.append(ci)
        try:
            a = int(answers[i])
        except (TypeError, ValueError):
            return False, "Answers must be integers (choice index).", {}
        if a < 0 or a > 3:
            return False, "Invalid choice index.", {}
        if a != ci:
            incorrect.append(i)
    if incorrect:
        return False, "Some answers were incorrect. Review highlights and try again.", {
            "grade": {
                "all_correct": False,
                "incorrect_indexes": incorrect,
                "correct_indexes": correct_indices,
            }
        }
    return True, "ok", {
        "grade": {
            "all_correct": True,
            "incorrect_indexes": [],
            "correct_indexes": correct_indices,
        }
    }


def _bonus_taken(username: str, completion_date: str) -> bool:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM learning_daily_bonus WHERE username=? AND bonus_date=?",
        (username, completion_date),
    )
    ok = cur.fetchone() is not None
    db.close()
    return ok


def _grant_bonus_if_eligible(username: str, completion_date: str) -> float:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(DISTINCT module_id) FROM learning_daily_completions
        WHERE username=? AND completion_date=?
        """,
        (username, completion_date),
    )
    row = cur.fetchone()
    n = int(row[0]) if row else 0
    db.close()

    need = len(_MODULES)
    if n < need or need == 0:
        return 0.0
    if _bonus_taken(username, completion_date):
        return 0.0

    ok, _ = ps.credit_reward(
        username,
        DAILY_ALL_BONUS,
        f"Learning daily bonus — all {need} modules ({completion_date})",
    )
    if not ok:
        return 0.0

    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO learning_daily_bonus (username, bonus_date)
        VALUES (?, ?)
        """,
        (username, completion_date),
    )
    db.commit()
    db.close()
    return DAILY_ALL_BONUS


def submit_quiz(
    username: str, module_id: str, answers: list[Any], quiz_id: str = ""
) -> tuple[bool, str, dict[str, Any]]:
    """Returns ok, message, payload with rewards and updated learning state."""
    mid = (module_id or "").strip()
    d = today_iso()

    if quiz_id.strip():
        okg, msg, grade_payload = _grade_ai_quiz(
            username, mid, quiz_id.strip(), list(answers)
        )
    else:
        okg, msg = _grade(mid, list(answers))
        grade_payload = {}
    if not okg:
        return False, msg, grade_payload

    amt = ps._money(REWARD_PER_MODULE)
    ps.ensure_paper_account(username)
    db = connect()
    cur = db.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            INSERT INTO learning_daily_completions (username, module_id, completion_date)
            VALUES (?, ?, ?)
            """,
            (username, mid, d),
        )
        cur.execute("SELECT cash FROM paper_accounts WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            db.rollback()
            db.close()
            return False, "No paper account.", {}
        cash = ps._money(float(row[0]))
        new_cash = ps._money(cash + amt)
        cur.execute(
            "UPDATE paper_accounts SET cash=? WHERE username=?",
            (new_cash, username),
        )
        cur.execute(
            """
            INSERT INTO paper_transactions
            (username, kind, symbol, shares, price, amount, cash_after, note)
            VALUES (?, 'reward', NULL, NULL, NULL, ?, ?, ?)
            """,
            (username, amt, new_cash, f"Learning module passed: {mid} ({d})"),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        db.close()
        st = get_state(username)
        return True, "You already completed this module today — no extra reward.", {
            "module_reward_usd": 0.0,
            "bonus_reward_usd": 0.0,
            "state": st,
        }
    except Exception:
        db.rollback()
        db.close()
        return False, "Could not save progress or credit account.", {}
    db.close()

    st0 = ps.get_portfolio_state(username)
    ps.record_snapshot(username, st0)
    ps.invalidate_leaderboard_cache()

    bonus_extra = _grant_bonus_if_eligible(username, d)
    st = get_state(username)

    parts = [f"+${REWARD_PER_MODULE:,.0f} paper cash for this module."]
    if bonus_extra > 0:
        parts.append(f"+${bonus_extra:,.0f} daily completion bonus!")

    return True, " ".join(parts), {
        "module_reward_usd": REWARD_PER_MODULE,
        "bonus_reward_usd": bonus_extra,
        "state": st,
        **grade_payload,
    }


def ai_outline_for_module(module_id: str) -> str:
    """Short bullet outline passed to AI for supplemental summary."""
    m = _by_id(module_id)
    if not m:
        return ""
    lines = [m["title"], m["tagline"]]
    lines.extend(m["lessons"][:3])
    return "\n".join(lines)


def completion_stats(username: str) -> dict[str, int]:
    """Completion counts for profile surfaces."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM learning_completions WHERE username=?",
        (username,),
    )
    total_row = cur.fetchone()
    cur.execute(
        """
        SELECT COUNT(DISTINCT module_id) FROM learning_daily_completions
        WHERE username=? AND completion_date>=?
        """,
        (username, week_start.isoformat()),
    )
    week_row = cur.fetchone()
    db.close()
    return {
        "total_completed": int(total_row[0]) if total_row else 0,
        "completed_this_week": int(week_row[0]) if week_row else 0,
    }
