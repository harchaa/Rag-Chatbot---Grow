"""End-to-end RAG pipeline.

Query-time flow (matches Architecture.md §3):
  ① PII guard
  ② Intent classifier  →  advisory/OOS → refusal
  ③ Dense retrieve
  ④ Rerank → best chunk
  ⑤ Answerability gate (score < threshold → "not in sources")
  ⑥ Groq LLM generation (grounded, facts-only)
  ⑦ Validate + attach single citation + footer

Returns a RAGResult with every field the UI needs to render a response.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mf_assistant.config import settings
from mf_assistant.guardrails.pii import contains_pii, pii_response
from mf_assistant.guardrails.classifier import classify
from mf_assistant.guardrails.refusals import refusal_response
from mf_assistant.guardrails.validators import validate_and_format
from mf_assistant.retrieval.retriever import retrieve
from mf_assistant.retrieval.reranker import rerank
from mf_assistant.llm.groq_client import generate

NOT_IN_SOURCES = (
    "I don't have that information in my current sources. "
    "Please refer to the official HDFC Mutual Fund website or AMFI for details."
)


@dataclass
class RAGResult:
    answer: str
    citation_url: str = ""
    fetched_at: str = ""
    was_refused: bool = False
    refusal_reason: str = ""         # "advisory" | "out_of_scope" | "pii" | "not_in_sources"
    debug: dict = field(default_factory=dict)


def ask(question: str, *, debug: bool = False) -> RAGResult:
    """Run the full pipeline and return a RAGResult."""
    q = question.strip()

    # ① PII guard
    if contains_pii(q):
        return RAGResult(
            answer=pii_response(),
            was_refused=True,
            refusal_reason="pii",
        )

    # ② Intent classification
    intent = classify(q)
    if intent != "FACTUAL":
        resp = refusal_response(intent)
        return RAGResult(
            answer=resp["message"],
            citation_url=resp["edu_link"],
            was_refused=True,
            refusal_reason=intent.lower(),
        )

    # ③ Dense retrieval
    candidates = retrieve(q)

    # ④ Rerank
    if settings.use_reranker and candidates:
        ranked = rerank(q, candidates, top_n=settings.rerank_top_n)
    else:
        ranked = candidates

    best = ranked[0] if ranked else None

    # ⑤ Answerability gate
    if best is None:
        return RAGResult(
            answer=NOT_IN_SOURCES,
            was_refused=True,
            refusal_reason="not_in_sources",
        )

    # Use rerank_score if available, else convert cosine distance to similarity
    if "rerank_score" in best:
        score = best["rerank_score"]
        answerable = score >= settings.score_threshold
    else:
        # Chroma cosine distance: 0 = identical. Convert to similarity for the gate.
        score = 1.0 - (best.get("distance", 2.0) / 2.0)
        answerable = score >= settings.score_threshold

    if not answerable:
        return RAGResult(
            answer=NOT_IN_SOURCES,
            was_refused=True,
            refusal_reason="not_in_sources",
            debug={"best_score": score} if debug else {},
        )

    # ⑥ Generate
    context = best["text"]
    raw_answer = generate(context, q)

    # ⑦ Validate, attach citation + footer
    meta = best["metadata"]
    citation_url = meta.get("source_url", "")
    fetched_at = meta.get("fetched_at", "")
    formatted = validate_and_format(raw_answer, citation_url, fetched_at)

    dbg = {}
    if debug:
        dbg = {
            "intent": intent,
            "best_chunk_id": best.get("chunk_id"),
            "best_score": score,
            "section": meta.get("section"),
        }

    return RAGResult(
        answer=formatted["answer"],
        citation_url=formatted["citation_url"],
        fetched_at=formatted["fetched_at"],
        was_refused=False,
        debug=dbg,
    )
