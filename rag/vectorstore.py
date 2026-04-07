import os
import json
from datetime import datetime, timezone
from typing import List, Dict

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index")

# Text splitter for large documents (PDFs, long HTML)
_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


def build_vectorstore(docs: List[Dict], persist: bool = True) -> FAISS:
    """
    Build or update a FAISS vectorstore from a list of doc dicts.
    Each dict must have an 'id' key and either a 'content' key or
    'summary'+'description' keys.  Large 'content' values are automatically
    split into smaller chunks so embeddings stay accurate.
    Duplicate IDs are skipped so repeated runs are safe.
    """
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    # Load existing index if present
    if persist and os.path.exists(FAISS_INDEX_PATH):
        vs = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        existing_ids: set = {
            m.metadata.get("id")
            for m in vs.docstore._dict.values()
            if hasattr(m, "metadata")
        }
    else:
        vs = None
        existing_ids = set()

    texts: List[str] = []
    metadatas: List[Dict] = []

    for doc in docs:
        doc_id = doc.get("id")
        if doc_id and doc_id in existing_ids:
            continue  # skip already-ingested document

        raw_text = doc.get("content") or f"{doc.get('summary', '')}\n{doc.get('description', '')}"
        meta = {k: v for k, v in doc.items() if k not in ("content", "summary", "description")}

        # Split long documents into chunks; each chunk gets the same metadata
        chunks = _splitter.split_text(raw_text)
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            chunk_meta = {**meta, "id": f"{doc_id}_chunk{i}" if len(chunks) > 1 else doc_id}
            metadatas.append(chunk_meta)

    if texts:
        if vs:
            vs.add_texts(texts, metadatas=metadatas)
        else:
            vs = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
        if persist:
            os.makedirs(os.path.dirname(os.path.abspath(FAISS_INDEX_PATH)), exist_ok=True)
            vs.save_local(FAISS_INDEX_PATH)
            # Write ingest timestamp so the app can show a staleness warning
            meta_path = os.path.join(FAISS_INDEX_PATH, "metadata.json")
            with open(meta_path, "w") as f:
                json.dump({
                    "built_at": datetime.now(timezone.utc).isoformat(),
                    "doc_count": len(texts),
                }, f)

    return vs
