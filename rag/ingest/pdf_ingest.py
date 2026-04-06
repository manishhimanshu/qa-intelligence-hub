"""
PDF ingestion for Kapost product documentation.
Reads all PDFs from the configured directory and returns chunked text
ready for the FAISS vectorstore.

Env vars:
  PDF_DIR  – directory containing .pdf files (default: ./pdfs)
"""
import os
from typing import List, Dict

from PyPDF2 import PdfReader


def ingest_pdfs(pdf_dir: str = None) -> List[Dict]:
    """
    Ingest all PDF files in pdf_dir.
    Each page becomes its own document chunk so retrieval is precise.
    """
    pdf_dir = pdf_dir or os.getenv("PDF_DIR", "./pdfs")
    docs: List[Dict] = []

    if not os.path.isdir(pdf_dir):
        print(f"[pdf_ingest] Directory not found: {pdf_dir} — skipping PDF ingestion.")
        return docs

    for fname in sorted(os.listdir(pdf_dir)):
        if not fname.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, fname)
        try:
            reader = PdfReader(path)
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                if not text.strip():
                    continue
                docs.append({
                    "id":      f"{fname}_page{page_num}",
                    "content": f"[Source: {fname}, Page {page_num}]\n{text}",
                    "source":  path,
                    "file":    fname,
                    "page":    page_num,
                })
        except Exception as e:
            print(f"[pdf_ingest] Failed to read {fname}: {e}")

    return docs
