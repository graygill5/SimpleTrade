from __future__ import annotations

import json
import os
from typing import Any, Dict

from openai import OpenAI

from .config import openai_model


def summarize_with_openai(payload: Dict[str, Any]) -> str:
    """
    Returns a concise market note based on the payload.
    Requires OPENAI_API_KEY in env.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (AI summary disabled).")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a professional sell-side macro/quant analyst. "
        "Write a concise daily note with:\n"
        "1) Market overview (trend/risk tone)\n"
        "2) Inflation & rates lens from provided headlines\n"
        "3) Likely impacted sectors/tickers (brief rationale)\n"
        "4) What a typical long-only retail buyer might consider (general, non-advice)\n"
        "Keep it ~250-350 words. Include a short watchlist. "
        "Do not provide personalized advice; state uncertainties."
    )

    user = (
        "Facts:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n\nConstraints: No personalized advice. Prefer scenarios/probabilities."
    )

    resp = client.chat.completions.create(
        model=openai_model(),
        temperature=0.3,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content.strip()
	
