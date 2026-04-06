"""
Markdown documentation ingestion for Kapost.
Walks the docs directory and ingests all .md files, chunking by heading
sections so retrieval returns focused, readable content.

Env vars:
  DOCS_DIR – directory to scan for .md files (default: ./docs)
"""
import os
import re
from typing import List, Dict


def _split_by_headings(text: str, source_file: str) -> List[Dict]:
    """Split a markdown file into sections at each # or ## heading."""
    sections = re.split(r'\n(?=#{1,3} )', text)
    docs = []
    for i, section in enumerate(sections):
        if not section.strip():
            continue
        # Extract heading as the first line
        heading_match = re.match(r'^(#{1,3} .+)', section)
        heading = heading_match.group(1).lstrip("# ").strip() if heading_match else f"section_{i}"
        docs.append({
            "id":      f"{os.path.basename(source_file)}_{i}",
            "content": section.strip(),
            "source":  source_file,
            "heading": heading,
        })
    return docs


def ingest_markdown_dir(docs_dir: str = None) -> List[Dict]:
    """
    Walk docs_dir recursively and ingest every .md file,
    split by heading sections.
    """
    docs_dir = docs_dir or os.getenv("DOCS_DIR", "./docs")
    docs: List[Dict] = []

    if not os.path.isdir(docs_dir):
        print(f"[md_ingest] Directory not found: {docs_dir} — skipping markdown ingestion.")
        return docs

    for root, _, files in os.walk(docs_dir):
        for fname in sorted(files):
            if not fname.lower().endswith(".md"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                chunks = _split_by_headings(text, path)
                docs.extend(chunks)
            except Exception as e:
                print(f"[md_ingest] Failed to read {fname}: {e}")

    return docs
