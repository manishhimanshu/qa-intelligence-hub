"""
PDF ingestion for Kapost product documentation.
Reads all PDFs from the configured directory and returns chunked text
ready for the FAISS vectorstore.

Env vars:
    PDF_DIR  – directory containing .pdf files (default: ./docs/product_knowledge)
"""
import os
import re
from typing import List, Dict

from PyPDF2 import PdfReader


def _normalize_feature_key(value: str) -> str:
    value = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    value = re.sub(r"-+", "-", value)
    return value


def _infer_pdf_metadata(path: str, root_dir: str) -> Dict:
    rel_path = os.path.relpath(path, root_dir).replace("\\", "/")
    lower = rel_path.lower()
    meta = {
        "relative_source_path": rel_path,
        "doc_domain": "pdf_general",
        "feature_key": "",
    }

    if "product_knowledge/" in lower:
        parts = lower.split("/")
        try:
            idx = parts.index("product_knowledge")
            if len(parts) > idx + 1:
                meta["doc_domain"] = "product_knowledge"
                meta["feature_key"] = _normalize_feature_key(parts[idx + 1])
        except ValueError:
            pass
        return meta

    # If PDF_DIR itself points to product_knowledge, first segment is feature folder.
    root_name = os.path.basename(root_dir).lower()
    if root_name == "product_knowledge":
        parts = lower.split("/")
        if parts:
            meta["doc_domain"] = "product_knowledge"
            meta["feature_key"] = _normalize_feature_key(parts[0])
        return meta

    return meta


def ingest_pdfs(pdf_dir: str = None) -> List[Dict]:
    """
    Ingest all PDF files in pdf_dir recursively.
    Each page becomes its own document chunk so retrieval is precise.
    """
    pdf_dir = pdf_dir or os.getenv("PDF_DIR", "./docs/product_knowledge")
    docs: List[Dict] = []

    if not os.path.isdir(pdf_dir):
        print(f"[pdf_ingest] Directory not found: {pdf_dir} — skipping PDF ingestion.")
        return docs

    for root, _, files in os.walk(pdf_dir):
        for fname in sorted(files):
            if not fname.lower().endswith(".pdf"):
                continue
            path = os.path.join(root, fname)
            try:
                meta = _infer_pdf_metadata(path, pdf_dir)
                reader = PdfReader(path)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text() or ""
                    if not text.strip():
                        continue
                    rel_source = meta.get("relative_source_path", fname)
                    docs.append({
                        "id":      f"{rel_source.replace('/', '_')}_page{page_num}",
                        "content": f"[Source: {rel_source}, Page {page_num}]\n{text}",
                        "source":  path,
                        "file":    fname,
                        "page":    page_num,
                        **meta,
                    })
            except Exception as e:
                print(f"[pdf_ingest] Failed to read {fname}: {e}")

    return docs
