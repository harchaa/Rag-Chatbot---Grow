# Mutual Fund Facts-Only FAQ Assistant

[![Refresh MF Data](https://github.com/harchaa/Rag-Chatbot---Grow/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/harchaa/Rag-Chatbot---Grow/actions/workflows/refresh-data.yml)

A lightweight, **compliance-first RAG assistant** that answers objective, verifiable
questions about HDFC mutual fund schemes and **refuses** advisory ones. Every factual
answer is ≤ 3 sentences, carries **exactly one source link**, and ends with a
`Last updated from sources: <date>` footer.

> **Facts-only. No investment advice.**

---

## What it does

| Query type | Example | Response |
|---|---|---|
| ✅ Factual | "What is the expense ratio of HDFC Mid Cap Fund?" | Answers with cited source + date |
| 🚫 Advisory | "Should I invest in HDFC Mid Cap?" | Politely refused, AMFI link provided |
| 🚫 Performance | "What returns did HDFC Mid Cap give last year?" | Refused, links to official factsheet |
| 🚫 PII | Query containing PAN / Aadhaar / phone | Privacy-safe response, nothing logged |

---

## Evaluation results (Phase 6)

Tested against 32 queries (18 factual + 14 must-refuse) using `eval/phase6/run_eval.py`:

| Metric | Score | Threshold |
|---|---|---|
| Citation hit rate | **100%** | ≥ 75% |
| Fact accuracy | **100%** | ≥ 75% |
| Format compliance (≤3 sentences, footer, link) | **100%** | ≥ 95% |
| Refusal accuracy | **100%** | ≥ 90% |

---

## Selected AMC & schemes

**AMC:** HDFC Mutual Fund — facts sourced from Groww scheme pages listed in
[data/sources.yaml](data/sources.yaml):

| Scheme | Category |
|---|---|
| HDFC Mid Cap Fund | Equity |
| HDFC Flexi Cap Fund | Equity |
| HDFC Small Cap Fund | Equity |
| HDFC Multi Cap Fund | Equity |
| HDFC NIFTY 50 Index Fund | Index |
| HDFC Balanced Advantage Fund | Hybrid |
| HDFC Short Term Debt Fund | Debt |
| HDFC Gold ETF Fund of Fund | Commodity |

---

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` (local, CPU) |
| Reranker | `sentence-transformers` CrossEncoder — `BAAI/bge-reranker-base` |
| Vector store | `chromadb` (persistent, cosine) |
| LLM | `groq` SDK — `llama-3.3-70b-versatile` (generation), `llama-3.1-8b-instant` (classifier) |
| UI | `streamlit` |
| Tests | `pytest` — 92 tests across 4 phases |
| Automation | GitHub Actions (monthly corpus refresh) |

---

## Setup

```bash
# 1. Clone and create a virtual environment
git clone https://github.com/harchaa/Rag-Chatbot---Grow.git
cd Rag-Chatbot---Grow
python3 -m venv .venv && source .venv/bin/activate

# 2. Install all dependencies
pip install -r requirements.txt

# 3. Add your Groq API key  (https://console.groq.com/keys)
cp .env.example .env
# edit .env → set GROQ_API_KEY=...
```

### Build the corpus and index

```bash
# Scrape all 8 HDFC scheme pages → data/processed/
python scripts/refresh_data.py

# Embed + index → .chroma/  (downloads BGE ~130 MB on first run)
python scripts/build_index.py
```

### Launch the UI

```bash
streamlit run ui/streamlit_app.py
# → http://localhost:8501
```

### Run the test suite

```bash
pytest                              # 92 tests, all offline
```

### Run the evaluation

```bash
python eval/phase6/run_eval.py                # full eval (calls Groq, ~2 min)
python eval/phase6/run_eval.py --retrieval    # retrieval-only, no API calls
```

---

## Project structure

```
├── data/
│   ├── sources.yaml          # curated Groww scheme URLs (the only corpus config)
│   └── processed/            # normalised per-scheme JSON (versioned, audit trail)
├── src/mf_assistant/
│   ├── config.py
│   ├── ingestion/            # scraper, normalizer, chunker  (Phase 1–2)
│   ├── index/                # BGE embedder, Chroma vectorstore  (Phase 2)
│   ├── retrieval/            # dense retriever, cross-encoder reranker  (Phase 3)
│   ├── llm/                  # Groq client  (Phase 3)
│   ├── guardrails/           # PII, classifier, refusals, validators  (Phase 4)
│   ├── pipeline/             # end-to-end RAG orchestration  (Phase 3–4)
│   └── prompts/              # system + classifier prompt templates
├── scripts/
│   ├── refresh_data.py       # re-scrape → data/processed/
│   └── build_index.py        # chunk → embed → Chroma index
├── ui/
│   └── streamlit_app.py      # chat UI
├── eval/phase6/              # evaluation YAML sets + run_eval.py
├── tests/phase{1..4}/        # 92 offline pytest tests
└── .github/workflows/
    └── refresh-data.yml      # monthly automated corpus refresh
```

---

## Architecture (overview)

**Offline (ingestion):** Groww scheme pages scraped via `__NEXT_DATA__` JSON parsing →
normalized per-scheme docs (performance/returns data deliberately excluded) →
structure-aware chunks with contextual prefix → BGE embeddings → ChromaDB.

**Online (query time):**
```
query → PII guard → intent classifier (FACTUAL / ADVISORY / PERFORMANCE / OOS)
      → dense retrieve (BGE) → cross-encoder rerank → answerability gate
      → Groq LLM (grounded, ≤3 sentences) → attach citation + footer
```

Full design in [docs/Architecture.md](docs/Architecture.md).

---

## How data stays fresh

`data/processed/*.json` (the clean corpus snapshots) are committed to git — providing
an audit trail of what facts were live at any point in time. The GitHub Action in
`.github/workflows/refresh-data.yml` runs `refresh_data.py` on the 1st of every month
and commits any changes back. The Chroma index (`.chroma/`) is a build artifact
(git-ignored) and is rebuilt from `data/processed/` by `build_index.py`.

---

## Known limitations

- Corpus is sourced from Groww scheme pages (a distributor/aggregator). The
  `data/sources.yaml` file is the single config to re-point the corpus to pure
  AMC/AMFI/SEBI URLs with zero code changes.
- Facts are only as current as the last monthly refresh — the answer footer
  shows this date explicitly.
- Answers are intentionally single-source (one citation per answer by design).
- No performance/return data in the corpus — by design, not a gap.

---

## Disclaimer

This assistant provides **facts only** and does **not** offer investment advice,
recommendations, or performance comparisons. Always verify information against
official AMC documents before making any financial decisions.
