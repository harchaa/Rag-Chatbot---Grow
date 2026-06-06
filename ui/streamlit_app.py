"""Phase 5 — Streamlit chat UI for MF Facts Assistant.

Run locally:  streamlit run ui/streamlit_app.py
Deploy:       Streamlit Community Cloud — set GROQ_API_KEY + USE_RERANKER=false in secrets.
"""

from __future__ import annotations

import html
from urllib.parse import urlparse

import streamlit as st

# ── Startup: build Chroma index if missing (needed on cloud deployments) ──────
@st.cache_resource(show_spinner=False)
def _ensure_index() -> None:
    """Embed & index data/processed/ if the collection is empty.

    Runs once per server start. On Streamlit Cloud (ephemeral disk) this takes
    ~60-90 seconds on cold start; subsequent page loads hit the cache instantly.
    """
    import json
    from mf_assistant.config import settings
    from mf_assistant.index.vectorstore import count, _collection, _clean_meta
    from mf_assistant.ingestion.chunker import chunk_document
    from mf_assistant.index.embedder import embed_documents

    if count() > 0:
        return  # index already populated

    docs = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(settings.processed_dir.glob("*.json"))
    ]
    chunks = []
    for doc in docs:
        chunks.extend(chunk_document(doc, settings.chunk_size_tokens, settings.chunk_overlap_tokens))

    embeddings = embed_documents([c["text"] for c in chunks])
    _collection().upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[_clean_meta(c["metadata"]) for c in chunks],
    )


from mf_assistant.pipeline.rag import RAGResult, ask

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MF Facts Assistant",
    page_icon="₹",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ── Streamlit chrome cleanup ─────────────────────────────────────────────── */
#MainMenu,
footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
header[data-testid="stHeader"] { display: none !important; }

/* ── Root layout ──────────────────────────────────────────────────────────── */
.main > .block-container {
    padding-top: 0 !important;
    padding-left:  1.5rem !important;
    padding-right: 1.5rem !important;
    padding-bottom: 5rem !important;
    max-width: 980px !important;
}

/* ── App header ───────────────────────────────────────────────────────────── */
.mf-header {
    position: sticky;
    top: 0;
    z-index: 1000;
    background: #1A2744;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.75rem;
    height: 54px;
    margin: 0 -1.5rem;
}
.mf-header-left  { display: flex; align-items: center; gap: 10px; }
.mf-logo         { color: #fff; font-size: 20px; font-weight: 700; }
.mf-title        { color: #fff; font-size: 18px; font-weight: 700;
                   font-family: Inter, 'Segoe UI', sans-serif; letter-spacing: -.2px; }
.mf-header-right { color: #7B93BF; font-size: 12.5px;
                   font-family: Inter, 'Segoe UI', sans-serif; }

/* ── Disclaimer banner ────────────────────────────────────────────────────── */
.mf-disclaimer {
    position: sticky;
    top: 54px;
    z-index: 999;
    background: #FFFDE7;
    border-bottom: 1px solid #F6D860;
    padding: 9px 1.75rem;
    font-size: 13.5px;
    color: #856404;
    font-family: Inter, 'Segoe UI', sans-serif;
    margin: 0 -1.5rem;
}

/* ── "Try asking" label ───────────────────────────────────────────────────── */
.try-asking-label {
    color: #9CA3AF;
    font-size: 13px;
    font-family: Inter, 'Segoe UI', sans-serif;
    margin: 20px 0 8px;
}

/* ── Example question pill buttons ───────────────────────────────────────── */
div[data-testid="stButton"] > button {
    background: #EEF2F7 !important;
    color: #374151 !important;
    border: none !important;
    border-radius: 999px !important;
    padding: 7px 16px !important;
    font-size: 13px !important;
    font-weight: 400 !important;
    box-shadow: none !important;
    white-space: normal !important;
    text-align: left !important;
    line-height: 1.4 !important;
    min-height: unset !important;
    transition: background .15s ease !important;
}
div[data-testid="stButton"] > button:hover {
    background: #DDE4EF !important;
    color: #1A2744 !important;
}
div[data-testid="stButton"] > button:focus,
div[data-testid="stButton"] > button:active {
    box-shadow: none !important;
    border: none !important;
    outline: none !important;
}

/* ── User message bubble ──────────────────────────────────────────────────── */
.user-row {
    display: flex;
    justify-content: flex-end;
    margin: 16px 0 4px;
}
.user-bubble {
    background: #1A2744;
    color: #fff;
    padding: 11px 18px;
    border-radius: 14px 14px 3px 14px;
    max-width: 62%;
    font-size: 14px;
    font-family: Inter, 'Segoe UI', sans-serif;
    line-height: 1.55;
    word-wrap: break-word;
}

/* ── Answer card ──────────────────────────────────────────────────────────── */
.answer-card {
    background: #fff;
    border: 1px solid #E5EAF0;
    border-radius: 10px;
    padding: 16px 20px;
    max-width: 62%;
    margin: 4px 0 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.answer-text {
    color: #1F2937;
    font-size: 14px;
    font-family: Inter, 'Segoe UI', sans-serif;
    line-height: 1.65;
    margin: 0 0 12px;
}
.source-link {
    color: #2563EB !important;
    font-size: 12.5px;
    text-decoration: none !important;
    display: flex;
    align-items: flex-start;
    gap: 5px;
    margin-bottom: 10px;
    word-break: break-all;
    line-height: 1.4;
}
.source-link:hover { text-decoration: underline !important; }
.card-divider {
    border: none;
    border-top: 1px solid #E5EAF0;
    margin: 6px 0 10px;
}
.card-footer {
    color: #9CA3AF;
    font-size: 12px;
    font-style: italic;
    margin: 0;
    font-family: Inter, 'Segoe UI', sans-serif;
}

/* ── Refusal card ─────────────────────────────────────────────────────────── */
.refusal-card {
    background: #FFF8F4;
    border: 1px solid #FDDCCC;
    border-left: 4px solid #E07B39;
    border-radius: 10px;
    padding: 16px 20px;
    max-width: 62%;
    margin: 4px 0 16px;
}
.refusal-text {
    color: #1F2937;
    font-size: 14px;
    font-family: Inter, 'Segoe UI', sans-serif;
    line-height: 1.65;
    margin: 0 0 10px;
}
.learn-more-link {
    color: #E07B39 !important;
    font-size: 13px;
    font-weight: 500;
    text-decoration: none !important;
    font-family: Inter, 'Segoe UI', sans-serif;
}
.learn-more-link:hover { text-decoration: underline !important; }

/* ── Privacy note above chat input ───────────────────────────────────────── */
.privacy-note {
    text-align: center;
    color: #B0B8C4;
    font-size: 11.5px;
    font-family: Inter, 'Segoe UI', sans-serif;
    margin: 2px 0 0;
    line-height: 1.5;
}

/* ── Spinner ──────────────────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: #1A2744 !important; }

/* ── Chat input ───────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] textarea {
    font-size: 14px !important;
    font-family: Inter, 'Segoe UI', sans-serif !important;
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

# ── Header + disclaimer ───────────────────────────────────────────────────────
st.markdown("""
<div class="mf-header">
  <div class="mf-header-left">
    <span class="mf-logo">₹</span>
    <span class="mf-title">MF Facts Assistant</span>
  </div>
  <div class="mf-header-right">Powered by HDFC MF corpus&nbsp;·&nbsp;Groq LLM</div>
</div>
<div class="mf-disclaimer">
  ⚠️&nbsp; <strong>Facts-only. No investment advice.</strong>&nbsp;
  Always verify with official sources.
</div>
""", unsafe_allow_html=True)

# ── Ensure index is ready (no-op after first build) ──────────────────────────
with st.spinner("Loading knowledge base… (first visit may take ~60 s)"):
    _ensure_index()

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question: str | None = None

# Pick up a question set by an example-button click in the previous run
_process_now: str | None = None
if st.session_state.pending_question:
    _process_now = st.session_state.pending_question
    st.session_state.pending_question = None

# ── Example questions ─────────────────────────────────────────────────────────
_EXAMPLES = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "What is the minimum SIP for HDFC Small Cap Fund?",
    "What is the exit load for HDFC Gold ETF Fund?",
]

st.markdown('<p class="try-asking-label">Try asking:</p>', unsafe_allow_html=True)

# Row 1: two pills
_c1, _c2 = st.columns(2)
with _c1:
    if st.button(_EXAMPLES[0], key="eq0"):
        st.session_state.pending_question = _EXAMPLES[0]
        st.rerun()
with _c2:
    if st.button(_EXAMPLES[1], key="eq1"):
        st.session_state.pending_question = _EXAMPLES[1]
        st.rerun()

# Row 2: one pill (matches mockup layout)
_c3, _ = st.columns([1, 1])
with _c3:
    if st.button(_EXAMPLES[2], key="eq2"):
        st.session_state.pending_question = _EXAMPLES[2]
        st.rerun()

# ── Helpers ───────────────────────────────────────────────────────────────────
def _short_url(full: str) -> str:
    """Return a display-friendly URL (no scheme, no www)."""
    try:
        p = urlparse(full)
        return (p.netloc + p.path).removeprefix("www.")
    except Exception:
        return full


def _render_user(text: str) -> None:
    st.markdown(
        f'<div class="user-row">'
        f'<div class="user-bubble">{html.escape(text)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_answer(r: RAGResult) -> None:
    url = r.citation_url or "#"
    st.markdown(f"""
<div class="answer-card">
  <p class="answer-text">{html.escape(r.answer)}</p>
  <a href="{url}" target="_blank" rel="noopener" class="source-link">
    🔗&nbsp;Source:&nbsp;{_short_url(url)}
  </a>
  <hr class="card-divider">
  <p class="card-footer">Last updated from sources: {html.escape(r.fetched_at)}</p>
</div>""", unsafe_allow_html=True)


def _render_refusal(r: RAGResult) -> None:
    url = r.citation_url or "https://www.amfiindia.com/investor-corner/knowledge-center"
    st.markdown(f"""
<div class="refusal-card">
  <p class="refusal-text">🚫&nbsp;&nbsp;{html.escape(r.answer)}</p>
  <a href="{url}" target="_blank" rel="noopener" class="learn-more-link">
    Learn more →
  </a>
</div>""", unsafe_allow_html=True)


# ── Render chat history ───────────────────────────────────────────────────────
for _msg in st.session_state.messages:
    if _msg["role"] == "user":
        _render_user(_msg["content"])
    else:
        _r: RAGResult = _msg["result"]
        (_render_refusal if _r.was_refused else _render_answer)(_r)

# ── Privacy note + sticky chat input ─────────────────────────────────────────
st.markdown(
    '<p class="privacy-note">Please do not share sensitive personal information or '
    'financial identifiers. All data is pulled from verified HDFC Mutual Fund sources.</p>',
    unsafe_allow_html=True,
)
_chat_input = st.chat_input("Ask a factual question about HDFC mutual fund schemes…")

# ── Process question (from input or example button) ───────────────────────────
_question: str | None = _process_now or (_chat_input.strip() if _chat_input else None)

if _question:
    st.session_state.messages.append({"role": "user", "content": _question})
    try:
        with st.spinner(""):
            _result = ask(_question)
    except Exception:
        _result = RAGResult(
            answer="Sorry, I couldn't process that request. Please try again.",
            was_refused=True,
            refusal_reason="error",
            citation_url="https://www.amfiindia.com/investor-corner/knowledge-center",
        )
    st.session_state.messages.append({"role": "assistant", "result": _result})
    st.rerun()
