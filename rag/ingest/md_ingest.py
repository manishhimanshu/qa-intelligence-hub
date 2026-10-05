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


def _normalize_feature_key(value: str) -> str:
    value = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    value = re.sub(r"-+", "-", value)
    return value


def _infer_md_metadata(source_file: str, docs_dir: str) -> Dict:
    rel_path = os.path.relpath(source_file, docs_dir).replace("\\", "/")
    lower = rel_path.lower()
    meta = {
        "relative_source_path": rel_path,
        "doc_domain": "docs_general",
        "feature_key": "",
    }

    if lower.endswith("role-permissions.md"):
        meta["doc_domain"] = "role_permissions"
        return meta

    if "automation/feature-context/" in lower:
        meta["doc_domain"] = "automation_feature_context"
        fname = os.path.basename(lower)
        feature = fname.replace(".md", "")
        feature = feature.replace("-feature-context", "")
        meta["feature_key"] = _normalize_feature_key(feature)
        return meta

    if "product_knowledge/" in lower:
        meta["doc_domain"] = "product_knowledge"
        parts = lower.split("/")
        try:
            idx = parts.index("product_knowledge")
            if len(parts) > idx + 1:
                meta["feature_key"] = _normalize_feature_key(parts[idx + 1])
        except ValueError:
            pass
        return meta

    return meta


def _apply_inline_metadata(text: str, meta: Dict) -> Dict:
    """Allow execution maps to declare stable metadata without filename rules."""
    match = re.search(
        r"Required ingestion metadata:\s*feature_key=([^;>]+);\s*doc_domain=([^\s>]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return meta
    raw_feature_key = match.group(1).strip()
    if raw_feature_key.startswith("<") and raw_feature_key.endswith(">"):
        raw_feature_key = ""
    feature_key = _normalize_feature_key(raw_feature_key)
    doc_domain = match.group(2).strip().lower()
    if feature_key:
        meta["feature_key"] = feature_key
    if doc_domain:
        meta["doc_domain"] = doc_domain
    return meta


def _split_by_headings(text: str, source_file: str, extra_meta: Dict) -> List[Dict]:
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
            **extra_meta,
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
                metadata = _apply_inline_metadata(
                    text,
                    _infer_md_metadata(path, docs_dir),
                )
                chunks = _split_by_headings(text, path, metadata)
                docs.extend(chunks)
            except Exception as e:
                print(f"[md_ingest] Failed to read {fname}: {e}")

    return docs
