# Implementation Plan — Mutual Fund Facts-Only FAQ Assistant

Phase-wise plan to build the assistant described in [Architecture.md](Architecture.md).
Each phase is **independently shippable**, has a clear **deliverable** and
**acceptance criteria**, and ends in a state you can demo or commit.

> **Guiding principles:** keep it lean, make every phase verifiable, and treat the
> compliance rules (facts-only, one citation, ≤3 sentences, refusals) as
> *acceptance criteria*, not afterthoughts.

---

## Phase 0 — Scaffolding & setup
**Goal:** a clean, runnable skeleton committed to GitHub.

- Initialise git repo + create GitHub repo.
- Create the folder structure from Architecture §9.
- `requirements.txt`, `.env.example` (`GROQ_API_KEY`, model IDs), `.gitignore`
  (ignore `.env`, `data/raw/` optionally, Chroma index dir, caches).
- `config.py` with `pydantic-settings` (paths, model IDs, `k`, chunk size, score
  threshold τ).
- `README.md` skeleton + move `ProblemStatement.md` into `docs/`.
- `ruff` config; Python virtualenv.

**Deliverable:** repo that installs cleanly (`pip install -r requirements.txt`).
**Acceptance:** `python -c "import mf_assistant"` works; config loads from `.env`.

---

## Phase 1 — Data ingestion & corpus
**Goal:** turn a list of Groww URLs into clean, timestamped per-scheme documents.

- Define `data/sources.yaml` schema: `url`, `scheme_name`, `amc`, `source_type`.
- Populate with the **15–25 Groww scheme URLs** (user-supplied).
- `scraper.py`: fetch each URL; parse `__NEXT_DATA__` JSON for structured facts;
  fall back to readable HTML sections; stamp `fetched_at`. *(Optional Playwright
  fallback only if a page needs JS rendering.)*
- `normalizer.py`: emit one clean JSON doc per scheme → `data/processed/`.
- Save verbatim snapshots → `data/raw/`.
- `scripts/refresh_data.py`: re-run ingestion for all/selected sources.

**Deliverable:** `data/processed/*.json` for the full corpus.
**Acceptance:** every source yields a normalized doc with the core facts (expense
ratio, exit load, min SIP, lock-in if applicable, benchmark, riskometer) + `fetched_at`.

---

## Phase 2 — Chunking, embedding & indexing
**Goal:** a queryable vector index built from the processed corpus.

- `chunker.py`: structure-aware + recursive chunking, contextual prefix, full metadata
  (Architecture §5).
- `embedder.py`: BGE wrapper (normalized embeddings; query instruction prefix).
- `vectorstore.py`: Chroma persistent collection (cosine); upsert chunks + metadata.
- `scripts/build_index.py`: `processed/ → chunk → embed → Chroma`.

**Deliverable:** persisted Chroma index.
**Acceptance:** a manual top-k query for "expense ratio of <scheme>" returns the
correct chunk in the top results, with `source_url` + `fetched_at` intact.

---

## Phase 3 — Retrieval & generation (happy path)
**Goal:** factual questions get grounded, cited, correctly-formatted answers.

- `retriever.py`: embed query → dense top-k (+ optional scheme metadata filter).
- `reranker.py`: cross-encoder rerank → best chunk(s); record top score.
- `prompts/system.txt`: strict facts-only, context-only, ≤3 sentences, no URLs in body,
  say "not available in sources" when unsupported.
- `groq_client.py`: generation call (low temperature).
- `pipeline/rag.py` (happy path): retrieve → rerank → generate → attach citation + footer.

**Deliverable:** CLI/notebook answering factual queries with one citation + footer.
**Acceptance:** 8–10 sample factual questions return accurate, ≤3-sentence answers
citing the right Groww page and a correct date.

---

## Phase 4 — Guardrails & compliance
**Goal:** the assistant is *safe and compliant by construction*.

- `pii.py`: PAN/Aadhaar/phone/email/account/OTP detectors; privacy-safe response; no
  logging of detected values.
- `classifier.py`: rule pre-filter + 8B LLM fallback → `FACTUAL | ADVISORY | OUT_OF_SCOPE`.
- `refusals.py`: polite refusal copy + relevant AMFI/SEBI educational link; performance
  queries → point to official factsheet only.
- `validators.py`: enforce ≤3 sentences, strip stray URLs, attach single citation,
  append footer.
- **Answerability gate:** if best rerank score < τ → "not available in my sources" +
  closest source link (no hallucination).
- Wire all of the above into `pipeline/rag.py` (full flow ①–⑦).

**Deliverable:** end-to-end compliant pipeline.
**Acceptance:** advisory queries ("Should I invest?", "Which is better?") are refused
with an educational link; PII inputs are handled safely; every factual answer satisfies
the output contract.

---

## Phase 5 — Streamlit UI
**Goal:** a clean, minimal demo interface.

- Welcome message + **3 example questions** (clickable) + persistent disclaimer banner
  *"Facts-only. No investment advice."*
- Chat transcript; render answer, citation link, and footer distinctly.
- Loading/error states; refusals rendered clearly.

**Deliverable:** `streamlit run ui/streamlit_app.py` working locally.
**Acceptance:** a non-technical user can ask a factual question, see a cited answer,
and get a clear refusal for an advisory one.

---

## Phase 6 — Evaluation & hardening
**Goal:** prove it works and tune it.

- `eval/factual_questions.yaml` (Q → expected source/fact) and
  `eval/advisory_questions.yaml` (should-refuse set).
- `eval/run_eval.py` metrics: retrieval hit-rate, **citation correctness**,
  refusal accuracy, format-compliance (sentence count / footer / single link).
- Tune `k`, τ, chunk size, reranker on/off, model choice.
- `pytest` unit tests for `pii`, `classifier`, `validators`, `chunker`.

**Deliverable:** eval report + passing tests.
**Acceptance:** high factual accuracy, ~100% refusal accuracy on the advisory set,
100% format compliance.

---

## Phase 7 — Automation & documentation
**Goal:** keep data fresh and ship a portfolio-ready repo.

- `.github/workflows/refresh-data.yml`: scheduled/manual `refresh_data.py` +
  `build_index.py`; commit updated `data/processed/` snapshots.
- Finalise `README.md`: setup steps, selected schemes, architecture overview,
  **known limitations**, and the disclaimer snippet.
- Final polish: screenshots/GIF of the UI, example transcript, repo hygiene.

**Deliverable:** automated refresh + complete, portfolio-quality README.
**Acceptance:** the Action runs green on demand; a fresh clone can be set up and run
from the README alone.

---

## Sequencing & estimate

| Phase | Focus | Rough effort |
|------|-------|------|
| 0 | Scaffolding | ~0.5 day |
| 1 | Ingestion | ~1–1.5 days |
| 2 | Index | ~0.5 day |
| 3 | Retrieval + generation | ~1 day |
| 4 | Guardrails | ~1.5 days |
| 5 | Streamlit UI | ~1 day |
| 6 | Eval + tests | ~1 day |
| 7 | Automation + docs | ~0.5 day |

**Critical path:** 0 → 1 → 2 → 3 → 4 (compliance) is the backbone; UI (5), eval (6),
and automation (7) build on a working pipeline. A demoable end-to-end happy path exists
at the end of **Phase 3**; a *compliant* one at the end of **Phase 4**.

---

## Out of scope (deliberately, to avoid complexity)
- Hybrid (BM25 + dense) search, multi-turn memory, and a FastAPI service layer are
  **optional enhancements**, not in the core plan.
- No user accounts, no persistence of user queries beyond anonymized, PII-free logs.
- No performance/return computation of any kind (per the problem statement).
```
