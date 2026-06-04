"""Thin Groq SDK wrapper for generation and intent classification calls."""

from __future__ import annotations

from pathlib import Path

from groq import Groq

from mf_assistant.config import settings

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _read_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _client() -> Groq:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
    return Groq(api_key=settings.groq_api_key)


def generate(context: str, question: str) -> str:
    """Generate a grounded factual answer from retrieved context.

    Returns the raw model text (≤ 3 sentences, no URLs — enforced later by validators).
    """
    system_prompt = _read_prompt("system.txt").format(
        context=context, question=question
    )
    resp = _client().chat.completions.create(
        model=settings.groq_generation_model,
        messages=[{"role": "user", "content": system_prompt}],
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
    return resp.choices[0].message.content.strip()


def classify_intent(question: str) -> str:
    """Return FACTUAL, ADVISORY, or OUT_OF_SCOPE for the given question.

    Uses the cheaper/faster 8B model. Falls back to FACTUAL on any error
    so the pipeline can still attempt retrieval.
    """
    prompt = _read_prompt("classifier.txt").format(question=question)
    try:
        resp = _client().chat.completions.create(
            model=settings.groq_classifier_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            timeout=settings.llm_timeout_seconds,
        )
        label = resp.choices[0].message.content.strip().upper()
        if label in {"FACTUAL", "ADVISORY", "PERFORMANCE", "OUT_OF_SCOPE"}:
            return label
        # Model returned something unexpected — treat as factual and let retrieval decide
        return "FACTUAL"
    except Exception:
        return "FACTUAL"
