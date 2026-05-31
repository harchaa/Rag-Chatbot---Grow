# Architecture — Mutual Fund Facts-Only FAQ Assistant

> A lightweight, compliance-first RAG assistant that answers **objective, verifiable**
> mutual-fund questions and **refuses** advisory ones. Every factual answer is
> ≤ 3 sentences, carries **exactly one source link**, and ends with a
> `Last updated from sources: <date>` footer.

---

## 1. Goal in one line

Retrieve facts from a curated set of official mutual-fund scheme pages, ground a
Groq-hosted LLM strictly on that retrieved text, and wrap the whole thing in
guardrails that enforce *facts-only, single-citation, short-answer* behaviour.

---

## 2. Key decisions (and why)

| Area | Choice | Why |
|------|--------|-----|
| **Data source** | Curated **Groww scheme URLs** (user-supplied), one per scheme, listed in `data/sources.yaml` | Source-agnostic design: the pipeline only knows "a list of URLs + metadata", so adding/replacing/expanding the corpus is a config edit, not a code change. |
| **Scraping** | `requests` + `BeautifulSoup`, parsing the embedded **`__NEXT_DATA__` JSON** first | Groww is a Next.js app; the page ships clean structured scheme facts (expense ratio, exit load, min SIP, AUM, risk, benchmark, lock-in) inside a JSON blob. Parsing JSON beats scraping rendered HTML. Headless **Playwright** is an optional fallback for pages that don't ship the blob. |
| **Embeddings** | Local **`BAAI/bge-small-en-v1.5`** (384-dim) via `sentence-transformers` | Free, no API key, runs on CPU, strong retrieval quality on small corpora. `bge-base-en-v1.5` (768-dim) is a drop-in upgrade if quality needs a bump. |
| **Vector store** | **ChromaDB** (persistent, cosine) | Tiny corpus (hundreds–low-thousands of chunks). Chroma gives native metadata storage + filtering, which we *need* — every chunk carries its `source_url` and `fetched_at` for citations. |
| **Retrieval** | Dense top-k → **cross-encoder rerank** (`bge-reranker-base`) → pick best | Each answer needs **exactly one** citation, so reranking to surface the single most relevant chunk is directly aligned with the requirement. |
| **LLM** | **Groq** — `llama-3.3-70b-versatile` (generation), `llama-3.1-8b-instant` (classifier) | Groq = very fast inference. 70B follows the strict format reliably; the 8B model is cheap/fast enough to run a per-query intent classifier. Both are env-configurable. |
| **Citations** | **Deterministic, not LLM-generated** | The LLM never emits a URL. We attach the link + date *programmatically* from the chosen chunk's metadata. This guarantees "exactly one valid citation, correct date" — the single biggest compliance risk if left to the model. |
| **UI** | **Streamlit** | Fastest path to a clean, demoable chat with welcome message, example questions, and a persistent disclaimer banner. |
| **Orchestration** | Thin custom pipeline (no heavy framework) | Keeps the code readable and portfolio-clean. We use small, direct libraries instead of a large RAG framework. |

> **Note on the "official sources only" constraint.** The problem statement asks for
> AMC/AMFI/SEBI sources and excludes aggregators. Per project direction, the corpus is
> built from **Groww scheme pages** the user supplies; each answer cites that exact page.
> AMFI/SEBI links are still used as the **educational links** returned on refusals. The
> source list lives in one file, so the corpus can be re-pointed to pure AMC/AMFI/SEBI
> URLs at any time with zero code changes.

---

## 3. System overview

```
                         ┌──────────────────────────────────────────────┐
                         │                INGESTION (offline)            │
   data/sources.yaml ──▶ │  scrape → normalize → chunk → embed → store   │ ──▶ Chroma index
   (Groww scheme URLs)    │  (raw/ + processed/ snapshots, timestamped)   │     (persisted)
                         └──────────────────────────────────────────────┘
                                                                                   │
─────────────────────────────────────────────────────────────────────────────────┼────────
                                                                                   ▼
        ┌────────────────────────────  QUERY TIME (online)  ───────────────────────────────┐
        │                                                                                   │
  user  │  ① PII guard ─▶ ② intent classifier ─▶ (advisory? → REFUSAL + edu link)            │
  query │        │                  │                                                       │
        │        │ (PII? → privacy refusal)   ③ retrieve (dense) ─▶ ④ rerank ─▶ best chunk   │
        │        │                              │                                            │
        │        │                              ⑤ answerable? (score ≥ τ)  ── no ─▶ "not in   │
        │        │                              │                                  sources"  │
        │        │                              ▼                                            │
        │        │                  ⑥ Groq LLM (grounded, facts-only, ≤3 sentences)          │
        │        │                              │                                            │
        │        └──────────────────────────────▼                                            │
        │                       ⑦ validate + attach single citation + footer                 │
        └───────────────────────────────────────┬───────────────────────────────────────────┘
                                                 ▼
                                   answer  (≤3 sentences)
                                   🔗 <one source link>
                                   Last updated from sources: <date>
```

---

## 4. Components

### 4.1 Ingestion (offline, re-runnable)
- **`scraper.py`** — fetches each URL in `sources.yaml`; extracts the `__NEXT_DATA__`
  JSON for structured facts; falls back to readable HTML sections; records `fetched_at`.
- **`normalizer.py`** — converts raw output into a clean **per-scheme document**:
  structured facts (key→value) + narrative/FAQ text sections, all tagged with
  `scheme_name`, `source_url`, `source_type`, `fetched_at`.
- **`chunker.py`** — see §5. Produces chunks + metadata ready for embedding.
- Snapshots: `data/raw/` (verbatim HTML/JSON for reproducibility & git history),
  `data/processed/` (normalized JSON the index is built from).

### 4.2 Index
- **`embedder.py`** — BGE wrapper; normalizes embeddings; applies BGE's query
  instruction prefix (`"Represent this sentence for searching relevant passages:"`)
  to queries only.
- **`vectorstore.py`** — Chroma persistent client; upsert chunks with metadata; query.

### 4.3 Retrieval
- **`retriever.py`** — embed query → dense top-k (k≈6); optional metadata filter by
  scheme when the query names one.
- **`reranker.py`** *(core for this use-case)* — cross-encoder scores the k candidates;
  returns the single best (or top-N) chunk(s) for grounding + citation.

### 4.4 LLM
- **`groq_client.py`** — thin Groq SDK wrapper (generation + classification calls),
  with model IDs, temperature (low, ~0.1), and timeouts from config.

### 4.5 Guardrails (the compliance core)
- **`pii.py`** — regex detectors for PAN, Aadhaar, phone, email, account numbers, OTP
  context. On hit: never log/store the value; return a privacy-safe message.
- **`classifier.py`** — two-stage intent router:
  1. **Rules** catch obvious advisory/comparison triggers ("should I", "which is
     better", "recommend", "worth investing", "vs", "best fund", "predict returns").
  2. **LLM** (8B) resolves ambiguous cases → `FACTUAL | ADVISORY | OUT_OF_SCOPE`.
- **`refusals.py`** — polite refusal text + a relevant **AMFI/SEBI educational link**.
- **`validators.py`** — enforces output contract: ≤ 3 sentences, strips any
  model-emitted URLs, attaches the single citation, appends the footer.

### 4.6 Pipeline
- **`rag.py`** — orchestrates the query-time flow (steps ①–⑦ in §3) and returns a
  structured result (`answer_text`, `citation_url`, `last_updated`, `was_refused`,
  `refusal_reason`).

### 4.7 UI
- **`streamlit_app.py`** — welcome message, **3 example questions** (buttons),
  persistent disclaimer banner *"Facts-only. No investment advice."*, chat transcript,
  and rendered citation + footer per answer.

---

## 5. Chunking strategy

Facts in these documents are **localized and often key-value** (expense ratio, exit
load, min SIP, lock-in, benchmark, riskometer). The strategy is tuned for *pinpoint
factual retrieval*, not long-form reasoning.

1. **Structure-aware split.** Structured facts are grouped into small, labelled chunks
   (e.g. *"Fees & Charges — expense ratio…, exit load…"*). FAQ pages are split **one
   Q&A per chunk**. Narrative sections use recursive character splitting
   (~**400–600 tokens**, **~80-token overlap**).
2. **Contextual prefix.** Every chunk is prefixed with
   `Scheme: <name> | AMC: <amc> | Section: <section>`. Short factual chunks retrieve far
   better when they carry this lightweight context (a "contextual retrieval" lite trick).
3. **Rich metadata** per chunk: `doc_id`, `chunk_id`, `scheme_name`, `source_url`,
   `source_type`, `section`, `fetched_at`. `source_url` + `fetched_at` drive the citation
   and footer.

**Rationale:** small + labelled chunks maximise precision for single-fact questions and
make the *one* cited source unambiguous.

---

## 6. Compliance traceability

| Requirement (Problem Statement) | Where it's enforced |
|---|---|
| Facts-only; no advice/opinions | System prompt + intent classifier + refusal handler |
| Answer ≤ 3 sentences | `validators.py` (sentence cap) |
| Exactly one citation link | Deterministic citation attach from chunk metadata |
| Footer `Last updated from sources: <date>` | `validators.py`, date = chunk `fetched_at` |
| Refuse advisory queries + give educational link | `classifier.py` + `refusals.py` (AMFI/SEBI) |
| No PII collection/processing/storage | `pii.py` + no-logging-of-PII policy |
| No performance comparison / return calc | Rules block it; for performance → link factsheet only |
| Verifiable, source-backed, official | One curated source per chunk; raw snapshots versioned |
| Minimal UI: welcome, 3 examples, disclaimer | `streamlit_app.py` |

---

## 7. Data update flow (GitHub)

```
edit data/sources.yaml ──▶ run scripts/refresh_data.py ──▶ updated data/raw + data/processed
        │                                                          │
        └────────────────── commit & push ─────────────────────────┘
                                   │
                 GitHub Action (scheduled or manual) ──▶ refresh + rebuild index
```

- The **source list and processed snapshots are versioned in git** (human-readable JSON),
  giving a clean audit trail of *what facts were current when*.
- The Chroma index is a build artifact (git-ignored), rebuilt from `data/processed/` via
  `scripts/build_index.py` — so it never needs to be committed as a binary.
- A GitHub Action (`.github/workflows/refresh-data.yml`) runs the refresh on a schedule
  or on demand and rebuilds the index.

---

## 8. Tech stack

| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| Scraping | `requests`, `beautifulsoup4`, `lxml`; *(optional)* `playwright` |
| Embeddings | `sentence-transformers` → `BAAI/bge-small-en-v1.5` |
| Reranker | `sentence-transformers` CrossEncoder → `BAAI/bge-reranker-base` |
| Vector store | `chromadb` (persistent) |
| LLM | `groq` SDK — `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` |
| Config | `pydantic-settings`, `python-dotenv` |
| UI | `streamlit` |
| Tests | `pytest` |
| Lint/format | `ruff` |
| Automation | GitHub Actions |

---

## 9. Project structure

```
mf-facts-assistant/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── docs/
│   ├── ProblemStatement.md
│   ├── Architecture.md
│   └── ImplementationPlan.md
├── data/
│   ├── sources.yaml          # curated Groww scheme URLs + metadata
│   ├── raw/                  # verbatim HTML/JSON snapshots (timestamped)
│   └── processed/            # normalized per-scheme JSON
├── src/mf_assistant/
│   ├── config.py
│   ├── ingestion/  (scraper, normalizer, chunker)
│   ├── index/      (embedder, vectorstore)
│   ├── retrieval/  (retriever, reranker)
│   ├── llm/        (groq_client)
│   ├── guardrails/ (pii, classifier, refusals, validators)
│   ├── pipeline/   (rag)
│   └── prompts/    (system.txt, classifier.txt)
├── scripts/        (build_index.py, refresh_data.py)
├── ui/             (streamlit_app.py)
├── eval/           (factual_questions.yaml, advisory_questions.yaml, run_eval.py)
├── tests/
└── .github/workflows/refresh-data.yml
```

---

## 10. Known limitations

- **Source dependency.** Per project direction the corpus is Groww scheme pages, which
  are an aggregator; strict regulatory compliance would prefer pure AMC/AMFI/SEBI URLs.
  The design supports that swap via `sources.yaml` with no code change.
- **Scraping fragility.** Site markup/JSON shape can change; the `__NEXT_DATA__` parser
  may need updates. Raw snapshots + the optional Playwright fallback mitigate this.
- **Freshness.** Facts are only as current as the last successful refresh; the footer
  date makes this explicit to the user.
- **Single-source answers.** The "exactly one citation" rule means questions that truly
  span multiple sources are answered from the single best one (others omitted by design).
- **No numbers we compute.** Returns/performance comparisons are intentionally not
  produced — the assistant points to the official factsheet instead.
```
