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
    "You are SimpleTrade's in-app assistant for a paper-trading simulator. "
    "Be helpful, practical, and educational. You may provide concrete simulated trade ideas, "
    "position-sizing examples, and step-by-step plans for fake-money learning. "
    "Use the app context (portfolio, quotes, headlines) when available. "
    "Never claim certainty, never guarantee returns, and do not invent data. "
    + _EDU_DISCLAIMER
    + " Do not give blanket refusals for normal simulator questions; instead give safe, balanced guidance for learning."
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


_SYSTEM_LEARNING = (
    "You are a concise finance tutor for a paper-trading learning app. "
    + _EDU_DISCLAIMER
    + " Produce a tight summary (max 220 words): short paragraphs or bullets, plain English."
)


def generate_learning_summary(module_title: str, outline: str) -> tuple[str | None, str | None]:
    """Extra lesson recap from structured outline (does not replace required reading)."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_LEARNING},
                {
                    "role": "user",
                    "content": f"Module: {module_title}\n\nCore material to summarize:\n{outline[:12000]}",
                },
            ],
            temperature=0.35,
            max_tokens=550,
        )
        text = (r.choices[0].message.content or "").strip()
        return text, None
    except Exception as e:
        return None, str(e)


def generate_learning_quiz(
    module_title: str, outline: str, question_count: int = 10
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Generate a fresh multiple-choice quiz from module lesson content."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    n = max(4, min(int(question_count), 12))
    prompt = (
        f"Module title: {module_title}\n"
        f"Generate exactly {n} multiple-choice questions based only on the lesson outline below.\n\n"
        "Output STRICT JSON with this shape only:\n"
        '{ "questions": [ { "question": "...", "choices": ["...","...","...","..."], "correct_index": 0 } ] }\n\n'
        "Rules:\n"
        "- Exactly 4 choices per question.\n"
        "- Exactly one correct choice.\n"
        "- correct_index must be integer 0-3.\n"
        "- Questions should be clear and non-trivial.\n"
        "- Do not include markdown, comments, or extra keys.\n\n"
        f"Lesson outline:\n{outline[:14000]}"
    )
    try:
        r = c.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write valid JSON only. "
                        "No prose. No markdown. No code fences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=2400,
            response_format={"type": "json_object"},
        )
        text = (r.choices[0].message.content or "").strip()
        import json

        data = json.loads(text)
        items = data.get("questions")
        if not isinstance(items, list):
            return None, "AI quiz format was invalid."
        clean: list[dict[str, Any]] = []
        for q in items[:n]:
            if not isinstance(q, dict):
                continue
            question = str(q.get("question") or "").strip()
            choices = q.get("choices")
            correct_index = q.get("correct_index")
            if (
                not question
                or not isinstance(choices, list)
                or len(choices) != 4
                or not isinstance(correct_index, int)
                or correct_index < 0
                or correct_index > 3
            ):
                continue
            choice_text = [str(c0 or "").strip() for c0 in choices]
            if any(not c1 for c1 in choice_text):
                continue
            clean.append(
                {
                    "question": question,
                    "choices": choice_text,
                    "correct_index": correct_index,
                }
            )
        if len(clean) != n:
            return None, "AI quiz generation did not return enough valid questions."
        return clean, None
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


def chat_reply(
    messages: list[dict[str, Any]], context_text: str = ""
) -> tuple[str | None, str | None]:
    """messages: list of {role, content} for OpenAI chat."""
    c = _client()
    if not c:
        return None, "OpenAI is not configured. Set OPENAI_API_KEY in your environment."
    safe: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_CHAT}]
    ctx = (context_text or "").strip()
    if ctx:
        safe.append(
            {
                "role": "system",
                "content": (
                    "Use this live app context when relevant. "
                    "If data appears missing or stale, say so clearly and avoid guessing.\n\n"
                    + ctx[:14000]
                ),
            }
        )
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
