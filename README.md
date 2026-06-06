# Mutual Fund Facts-Only FAQ Assistant

A lightweight, **compliance-first RAG assistant** that answers objective, verifiable
questions about mutual fund schemes and **refuses** advisory ones. Every factual answer
is ≤ 3 sentences, carries **exactly one source link**, and ends with a
`Last updated from sources: <date>` footer.

> **Facts-only. No investment advice.**

---

## Status

🚧 In development — **Phase 0 (scaffolding) complete.** See the roadmap in
[docs/ImplementationPlan.md](docs/ImplementationPlan.md).

## Documentation

- [docs/ProblemStatement.md](docs/ProblemStatement.md) — requirements
- [docs/Architecture.md](docs/Architecture.md) — design & key decisions
- [docs/ImplementationPlan.md](docs/ImplementationPlan.md) — phase-wise plan

---

## Selected AMC & schemes

**AMC:** HDFC Mutual Fund — facts sourced from the curated Groww scheme pages listed in
[data/sources.yaml](data/sources.yaml):

| Scheme | Category |
|--------|----------|
| HDFC Mid-Cap Fund | Equity |
| HDFC Equity Fund | Equity |
| HDFC Small Cap Fund | Equity |
| HDFC Multi Cap Fund | Equity |
| HDFC Nifty 50 Index Fund | Index |
| HDFC Balanced Advantage Fund | Hybrid |
| HDFC Short Term Opportunities Fund | Debt |
| HDFC Gold ETF Fund of Fund | Commodity |

---

## Tech stack

Python 3.11+ · local **BGE** embeddings (`sentence-transformers`) · **ChromaDB** vector
store · **Groq** LLM (`llama-3.3-70b-versatile`) · **Streamlit** UI.

---

## Setup

```bash
# 1. Clone, then create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies (also installs this package in editable mode)
pip install -r requirements.txt        # add -dev for pytest + ruff

# 3. Configure secrets
cp .env.example .env
#   then edit .env and set GROQ_API_KEY (https://console.groq.com/keys)
```

Verify the install:

```bash
python -c "from mf_assistant.config import settings; print(settings.embedding_model)"
# -> BAAI/bge-small-en-v1.5
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

---

## Architecture (overview)

Offline: scrape curated source URLs → normalize → chunk (structure-aware + contextual
prefix) → embed (BGE) → store in Chroma. Online: PII guard → intent classifier
(facts-only vs advisory) → dense retrieve → rerank → grounded Groq generation →
validate (≤3 sentences, attach single citation, append footer). Full diagram in
[docs/Architecture.md](docs/Architecture.md).

## Known limitations

- Corpus is built from Groww scheme pages (an aggregator); the design re-points to pure
  AMC/AMFI/SEBI URLs via `data/sources.yaml` with no code change.
- Facts are only as current as the last data refresh (shown in each answer's footer).
- Answers are intentionally single-source; no performance/return computation is done.

## Disclaimer

This assistant provides **facts only** and does **not** offer investment advice,
recommendations, or performance comparisons. Always verify against official documents.
