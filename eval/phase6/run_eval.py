"""Phase 6 evaluation — run the full pipeline against the factual and refusal sets.

Usage:
    python eval/phase6/run_eval.py              # full eval (calls Groq)
    python eval/phase6/run_eval.py --retrieval  # retrieval-only, no LLM (faster)

Metrics reported:
    Factual set:
        citation_hit_rate   citation_url contains expected_source
        fact_accuracy       expected_fact substring in answer (case-insensitive)
        not_refused_rate    pipeline did not refuse a factual question
        format_compliance   answer ≤ 3 sentences + has fetched_at + has citation_url

    Refusal set:
        refusal_accuracy    was_refused == True
        reason_accuracy     refusal_reason matches expected_reason

Success thresholds (exits 1 if any threshold is missed):
    citation_hit_rate   ≥ 0.75
    fact_accuracy       ≥ 0.75
    refusal_accuracy    ≥ 0.90
    format_compliance   ≥ 0.95
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

EVAL_DIR = Path(__file__).parent
FACTUAL_FILE  = EVAL_DIR / "factual_questions.yaml"
ADVISORY_FILE = EVAL_DIR / "advisory_questions.yaml"

# ── Thresholds ────────────────────────────────────────────────────────────────
THRESHOLDS = {
    "citation_hit_rate":  0.75,
    "fact_accuracy":      0.75,
    "refusal_accuracy":   0.90,
    "format_compliance":  0.95,
}

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _sentence_count(text: str) -> int:
    parts = _SENTENCE_RE.split(text.strip())
    return len([s for s in parts if s.strip()])


def _format_ok(result) -> bool:
    return (
        _sentence_count(result.answer) <= 3
        and bool(result.fetched_at)
        and bool(result.citation_url)
    )


def _pass(ok: bool) -> str:
    return "✅" if ok else "❌"


# ── Eval runners ──────────────────────────────────────────────────────────────
def run_factual(questions: list[dict], retrieval_only: bool) -> dict:
    from mf_assistant.pipeline.rag import ask
    from mf_assistant.index.embedder import embed_query
    from mf_assistant.index.vectorstore import query as chroma_query
    from mf_assistant.config import settings

    total = len(questions)
    n_citation = n_fact = n_not_refused = n_format = 0
    rows = []

    print(f"\n{'─'*70}")
    print(f"  FACTUAL QUESTIONS  ({total} total)")
    print(f"{'─'*70}")

    for q in questions:
        qid      = q["id"]
        question = q["question"]
        exp_src  = q["expected_source"]
        exp_fact = q["expected_fact"]

        if retrieval_only:
            # Dense retrieval only — no LLM call
            emb = embed_query(question)
            hits = chroma_query(emb, k=settings.top_k)
            best = hits[0] if hits else None
            citation_ok = best is not None and exp_src in best["metadata"].get("source_url", "")
            fact_ok = False  # can't check without answer
            refused = False
            format_ok = False
            answer_preview = best["metadata"].get("section", "-") if best else "NO RESULTS"
            reason = ""
        else:
            result = ask(question)
            citation_ok = exp_src in (result.citation_url or "")
            fact_ok     = exp_fact.lower() in result.answer.lower()
            refused     = result.was_refused
            format_ok   = _format_ok(result)
            answer_preview = result.answer[:80].replace("\n", " ")
            reason = result.refusal_reason

        not_refused = not refused
        if citation_ok:  n_citation   += 1
        if fact_ok:      n_fact       += 1
        if not_refused:  n_not_refused += 1
        if format_ok:    n_format     += 1

        cite_icon   = _pass(citation_ok)
        fact_icon   = _pass(fact_ok)
        refuse_icon = _pass(not_refused)
        fmt_icon    = _pass(format_ok) if not retrieval_only else "—"

        print(
            f"  {qid}  cite={cite_icon}  fact={fact_icon}  "
            f"not_refused={refuse_icon}  fmt={fmt_icon}"
        )
        print(f"       Q: {question}")
        if refused:
            print(f"       ⚠ REFUSED ({reason})")
        else:
            print(f"       A: {answer_preview}…")
        print()
        time.sleep(0.3)   # slight pause — be polite to the API

    metrics = {
        "citation_hit_rate":  n_citation   / total,
        "fact_accuracy":      n_fact       / total,
        "not_refused_rate":   n_not_refused / total,
        "format_compliance":  n_format     / total if not retrieval_only else None,
        "n_total": total,
    }
    return metrics


def run_refusals(questions: list[dict]) -> dict:
    from mf_assistant.pipeline.rag import ask

    total = len(questions)
    n_refused = n_reason_ok = 0

    print(f"\n{'─'*70}")
    print(f"  REFUSAL QUESTIONS  ({total} total)")
    print(f"{'─'*70}")

    for q in questions:
        qid        = q["id"]
        question   = q["question"]
        exp_reason = q["expected_reason"]
        category   = q.get("category", "")

        result = ask(question)
        refused    = result.was_refused
        reason_ok  = result.refusal_reason == exp_reason

        if refused:   n_refused   += 1
        if reason_ok: n_reason_ok += 1

        print(
            f"  {qid}  [{category:12}]  "
            f"refused={_pass(refused)}  reason={_pass(reason_ok)}"
            f"  (got={result.refusal_reason!r}, want={exp_reason!r})"
        )
        print(f"       Q: {question}")
        print()
        time.sleep(0.3)

    return {
        "refusal_accuracy": n_refused   / total,
        "reason_accuracy":  n_reason_ok / total,
        "n_total": total,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retrieval", action="store_true",
        help="Skip LLM; test retrieval + citation only (no Groq API calls)."
    )
    parser.add_argument(
        "--factual-only", action="store_true",
        help="Run factual set only."
    )
    parser.add_argument(
        "--refusal-only", action="store_true",
        help="Run refusal set only."
    )
    args = parser.parse_args(argv)

    factual_qs  = yaml.safe_load(FACTUAL_FILE.read_text())["questions"]
    advisory_qs = yaml.safe_load(ADVISORY_FILE.read_text())["questions"]

    print("\n" + "═"*70)
    print("  MF Facts Assistant — Phase 6 Evaluation")
    print("═"*70)

    f_metrics = r_metrics = None

    if not args.refusal_only:
        f_metrics = run_factual(factual_qs, retrieval_only=args.retrieval)

    if not args.factual_only and not args.retrieval:
        r_metrics = run_refusals(advisory_qs)

    # ── Summary ──────────────────────────────────────────────────────────────
    print("═"*70)
    print("  SUMMARY")
    print("═"*70)

    all_pass = True

    if f_metrics:
        print(f"\n  Factual set ({f_metrics['n_total']} questions):")
        metrics_to_check = [
            ("citation_hit_rate", f_metrics["citation_hit_rate"], THRESHOLDS["citation_hit_rate"]),
            ("fact_accuracy",     f_metrics["fact_accuracy"],     THRESHOLDS["fact_accuracy"]),
            ("not_refused_rate",  f_metrics["not_refused_rate"],  0.90),
        ]
        if f_metrics["format_compliance"] is not None:
            metrics_to_check.append(
                ("format_compliance", f_metrics["format_compliance"], THRESHOLDS["format_compliance"])
            )
        for name, val, threshold in metrics_to_check:
            ok = val >= threshold
            all_pass = all_pass and ok
            bar = "█" * int(val * 20) + "░" * (20 - int(val * 20))
            print(f"    {_pass(ok)} {name:22} {val:.0%}  [{bar}]  (threshold ≥{threshold:.0%})")

    if r_metrics:
        print(f"\n  Refusal set ({r_metrics['n_total']} questions):")
        for name, threshold in [
            ("refusal_accuracy", THRESHOLDS["refusal_accuracy"]),
            ("reason_accuracy",  0.80),
        ]:
            val = r_metrics[name]
            ok  = val >= threshold
            all_pass = all_pass and ok
            bar = "█" * int(val * 20) + "░" * (20 - int(val * 20))
            print(f"    {_pass(ok)} {name:22} {val:.0%}  [{bar}]  (threshold ≥{threshold:.0%})")

    print()
    if all_pass:
        print("  ✅  All thresholds met — Phase 6 PASS")
    else:
        print("  ❌  One or more thresholds missed — see detail above")
    print("═"*70 + "\n")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
