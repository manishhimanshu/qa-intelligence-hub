"""
shared_vectorstore.py — Single FAISS + embeddings singleton for all pages.

All three Streamlit pages import `load_vectorstore` from here.
Using ONE @st.cache_resource-decorated function means the FAISS index
(~150 MB) and sentence-transformers model (~90 MB) are loaded ONCE per
process, not once per page — critical for Streamlit Cloud's 1 GB free tier.
"""
import os
import sys
import streamlit as st

# Ensure rag/ is on path regardless of which page imports this first
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_DIR = os.path.join(_UI_DIR, "../rag")
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)


@st.cache_resource(show_spinner="Loading RAG knowledge base (first load only)…")
def load_vectorstore():
    """
    Load HuggingFace embeddings + FAISS index exactly once per process.
    Thread-safe via st.cache_resource (handles concurrent first-load requests).
    Returns None if the index has not been built yet.
    """
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS

    index_path = os.path.join(
        _RAG_DIR,
        os.getenv("FAISS_INDEX_PATH", "faiss_index").strip("./"),
    )

    if not os.path.exists(index_path):
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    return FAISS.load_local(
        index_path, embeddings, allow_dangerous_deserialization=True
    )
