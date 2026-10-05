import os
import sys
from functools import lru_cache
from dotenv import load_dotenv

# Load .env from the same directory as this file regardless of working directory
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

_RAG_DIR = os.path.dirname(os.path.abspath(__file__))
_FAISS_INDEX = os.path.join(
    _RAG_DIR,
    os.getenv("FAISS_INDEX_PATH", "./faiss_index").lstrip("./")
)


@lru_cache(maxsize=1)
def _get_vectorstore():
    """
    Standalone vectorstore loader used when running outside Streamlit
    (e.g. ingest scripts, test_rag.py). Uses lru_cache for process-level
    singleton.

    Inside the Streamlit app, all pages use shared_vectorstore.load_vectorstore()
    via @st.cache_resource instead, which is thread-safe and shared across pages.
    """
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return FAISS.load_local(_FAISS_INDEX, embeddings, allow_dangerous_deserialization=True)


def get_relevant_docs(prompt: str, top_k: int = 5) -> list[dict]:
    """
    Return the top_k most relevant document chunks for the given prompt.
    Tries to use the shared Streamlit vectorstore first (avoids double load);
    falls back to the local lru_cache loader when called outside Streamlit.
    """
    if not os.path.exists(_FAISS_INDEX):
        return [{"id": "no-index", "content": "RAG index not built yet. Run ingest_all.py first."}]

    # Try to use the shared @st.cache_resource loader (avoids loading FAISS twice)
    try:
        # shared_vectorstore lives in custom-agent-ui/ — add it to path if needed
        _ui_dir = os.path.join(_RAG_DIR, "../custom-agent-ui")
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)
        from shared_vectorstore import load_vectorstore
        vs = load_vectorstore()
    except Exception:
        # Fallback: standalone mode (ingest scripts, test_rag.py, MCP server)
        vs = _get_vectorstore()

    if vs is None:
        return [{"id": "no-index", "content": "RAG index not built yet. Run ingest_all.py first."}]

    docs = vs.similarity_search(prompt, k=top_k)
    results = []
    for doc in docs:
        entry = {"content": doc.page_content}
        entry.update(doc.metadata)
        results.append(entry)
    return results


def get_relevant_docs_filtered(
    prompt: str,
    top_k: int = 5,
    source_eq: str = "",
    source_contains: str = "",
    type_eq: str = "",
    type_prefix: str = "",
    feature_key_eq: str = "",
    doc_domain_eq: str = "",
    path_contains: str = "",
    max_candidates: int = 60,
) -> list[dict]:
    """
    Semantic retrieval with optional metadata filters.
    Pulls a larger candidate set, then filters/ranks down to top_k.
    """
    if not os.path.exists(_FAISS_INDEX):
        return [{"id": "no-index", "content": "RAG index not built yet. Run ingest_all.py first."}]

    try:
        _ui_dir = os.path.join(_RAG_DIR, "../custom-agent-ui")
        if _ui_dir not in sys.path:
            sys.path.insert(0, _ui_dir)
        from shared_vectorstore import load_vectorstore
        vs = load_vectorstore()
    except Exception:
        vs = _get_vectorstore()

    if vs is None:
        return [{"id": "no-index", "content": "RAG index not built yet. Run ingest_all.py first."}]

    k = max(top_k * 5, 30)
    k = min(k, max(1, int(max_candidates)))
    docs = vs.similarity_search(prompt, k=k)

    source_eq_l = (source_eq or "").strip().lower()
    source_contains_l = (source_contains or "").strip().lower()
    type_eq_l = (type_eq or "").strip().lower()
    type_prefix_l = (type_prefix or "").strip().lower()
    feature_key_eq_l = (feature_key_eq or "").strip().lower()
    doc_domain_eq_l = (doc_domain_eq or "").strip().lower()
    path_contains_l = (path_contains or "").strip().lower().replace("\\", "/")

    filtered = []
    for doc in docs:
        meta = doc.metadata or {}
        src = str(meta.get("source", "")).lower()
        typ = str(meta.get("type", "")).lower()
        feature_key = str(meta.get("feature_key", "")).lower()
        doc_domain = str(meta.get("doc_domain", "")).lower()
        rel_path = str(meta.get("relative_source_path", "")).lower().replace("\\", "/")
        path_text = f"{src} {rel_path}".replace("\\", "/")

        if source_eq_l and src != source_eq_l:
            continue
        if source_contains_l and source_contains_l not in src:
            continue
        if type_eq_l and typ != type_eq_l:
            continue
        if type_prefix_l and not typ.startswith(type_prefix_l):
            continue
        if feature_key_eq_l and feature_key != feature_key_eq_l:
            continue
        if doc_domain_eq_l and doc_domain != doc_domain_eq_l:
            continue
        if path_contains_l and path_contains_l not in path_text:
            continue

        entry = {"content": doc.page_content}
        entry.update(meta)
        filtered.append(entry)
        if len(filtered) >= top_k:
            break

    return filtered
