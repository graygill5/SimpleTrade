"""
OpenAI helpers for market summaries, educational outlook, and chat.
Requires OPENAI_API_KEY in environment (.env supported via python-dotenv in app).
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_EDU_DISCLAIMER = (
    "Outputs are educational commentary only, not investment advice, "
    "not a recommendation, and not a forecast of returns. "
    "Markets involve risk; users should consult a qualified professional."
)

_SYSTEM_MARKET = (
    "You are a concise financial educator writing for a student trading simulator. "
    + _EDU_DISCLAIMER
    + " Summarize clearly in plain English. No more than 180 words."
)

_SYSTEM_OUTLOOK = (
    "You are a financial educator. Offer a short, balanced discussion of possible "
    "drivers and risks based only on the facts provided—no certainty, no price targets. "
    + _EDU_DISCLAIMER
    + " Max 160 words."
)

_SYSTEM_CHAT = (
    "You are SimpleTrade's in-app assistant: helpful, accurate, and cautious. "
    "Explain concepts, UI help, and general market education. "
    + _EDU_DISCLAIMER
    + " If asked for personalized investment advice, refuse and suggest speaking to a professional."
)

_SYSTEM_TICKER_OVERVIEW = (
    "You are a financial educator writing for a student paper-trading app. "
    "Using ONLY the facts and headlines provided in the user message, write a short overview that: "
    "(1) briefly describes what this ticker represents (company/ETF/index as applicable); "
    "(2) summarizes themes from the recent headlines without claiming you verified them beyond the feed; "
    "(3) notes general risks or uncertainties. "
    + _EDU_DISCLAIMER
    + " If the context lacks headlines, say so briefly. Do not invent numbers or events. "
    "Max 240 words. Use short paragraphs or bullets."
)


def _client():
    try:
        from openai import OpenAI
    except ImportError:
        return None
    key = os.getenv("OPENAI_API_KEY")
    if not key or not key.strip():
        return None
    return OpenAI(api_key=key)


def is_configured() -> bool:
    return _client() is not None


def generate_market_summary(context_text: str) -> tuple[str | None, str | None]:
    """Returns (text, error_message)."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_MARKET},
                {
                    "role": "user",
                    "content": "Using the following snapshot and headlines, write a brief market summary.\n\n"
                    + context_text[:12000],
                },
            ],
            temperature=0.4,
            max_tokens=500,
        )
        text = (r.choices[0].message.content or "").strip()
        return text, None
    except Exception as e:
        return None, str(e)


def generate_educational_outlook(context_text: str) -> tuple[str | None, str | None]:
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_OUTLOOK},
                {
                    "role": "user",
                    "content": "Provide a balanced educational outlook based on this context only:\n\n"
                    + context_text[:12000],
                },
            ],
            temperature=0.5,
            max_tokens=450,
        )
        text = (r.choices[0].message.content or "").strip()
        return text, None
    except Exception as e:
        return None, str(e)


def generate_ticker_overview(context_text: str) -> tuple[str | None, str | None]:
    """Educational overview for a single symbol from Yahoo snapshot + headlines."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_TICKER_OVERVIEW},
                {
                    "role": "user",
                    "content": "Context from Yahoo Finance (may be delayed or incomplete):\n\n"
                    + context_text[:14000],
                },
            ],
            temperature=0.35,
            max_tokens=600,
        )
        text = (r.choices[0].message.content or "").strip()
        return text, None
    except Exception as e:
        return None, str(e)


def chat_reply(messages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """messages: list of {role, content} for OpenAI chat."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    safe: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_CHAT}]
    for m in messages[-24:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        safe.append({"role": role, "content": content[:8000]})
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=safe,
            temperature=0.5,
            max_tokens=900,
        )
        text = (r.choices[0].message.content or "").strip()
        return text, None
    except Exception as e:
        return None, str(e)
