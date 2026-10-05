"""
Automation repository ingestion for Cypress-grounded code generation.

This ingester walks the automation repo and indexes framework artifacts so
LLM generation can reference real project patterns:
  - Cypress specs (.cy.js/.cy.ts)
  - Page objects
  - Custom commands
  - Test data and setup/cleanup helpers
"""

import os
import re
from typing import Dict, List


def _safe_read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _normalize_rel(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace("\\", "/")


def _tags_for_path(rel_path: str) -> list:
    lower = rel_path.lower()
    tags = []
    for token in ("smoke", "regression", "parallel", "api", "auth", "role", "fixture", "cleanup"):
        if token in lower:
            tags.append(token)
    return tags


def _extract_describe_chunks(text: str) -> list:
    chunks = re.split(r"\n(?=\s*(?:describe|context)\s*\()", text)
    return [c.strip() for c in chunks if c.strip()]


def _extract_command_chunks(text: str) -> list:
    chunks = re.split(r"\n(?=\s*Cypress\.Commands\.add\s*\()", text)
    return [c.strip() for c in chunks if "Cypress.Commands.add" in c]


def _ingest_spec(path: str, root: str) -> List[Dict]:
    text = _safe_read(path)
    if len(text.strip()) < 60:
        return []

    rel_path = _normalize_rel(path, root)
    outer_match = re.search(r"describe\(['\"`](.+?)['\"`]", text)
    feature_name = outer_match.group(1) if outer_match else os.path.basename(path)
    chunks = _extract_describe_chunks(text)

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append(
            {
                "id": f"auto_spec_{rel_path.replace('/', '_')}_{i}",
                "content": f"[Automation Spec: {rel_path}]\nFeature: {feature_name}\n\n{chunk}",
                "source": "automation_repo",
                "type": "automation_spec",
                "repo_path": rel_path,
                "feature": feature_name,
                "tags": _tags_for_path(rel_path),
            }
        )
    return docs


def _ingest_page_object(path: str, root: str) -> List[Dict]:
    text = _safe_read(path)
    if len(text.strip()) < 60:
        return []

    rel_path = _normalize_rel(path, root)
    class_match = re.search(r"class\s+(\w+)", text)
    class_name = class_match.group(1) if class_match else os.path.basename(path)
    return [
        {
            "id": f"auto_po_{rel_path.replace('/', '_')}",
            "content": f"[Automation Page Object: {rel_path}]\nClass: {class_name}\n\n{text}",
            "source": "automation_repo",
            "type": "automation_page_object",
            "repo_path": rel_path,
            "class": class_name,
            "tags": _tags_for_path(rel_path),
        }
    ]


def _ingest_command_file(path: str, root: str) -> List[Dict]:
    text = _safe_read(path)
    if len(text.strip()) < 40:
        return []

    rel_path = _normalize_rel(path, root)
    docs: List[Dict] = []
    for i, cmd in enumerate(_extract_command_chunks(text)):
        name_match = re.search(r"Cypress\.Commands\.add\(['\"`]([\w$]+)['\"`]", cmd)
        cmd_name = name_match.group(1) if name_match else f"command_{i}"
        docs.append(
            {
                "id": f"auto_cmd_{cmd_name}_{i}",
                "content": f"[Automation Custom Command: cy.{cmd_name}]\nFile: {rel_path}\n\n{cmd}",
                "source": "automation_repo",
                "type": "automation_command",
                "repo_path": rel_path,
                "command": cmd_name,
                "tags": _tags_for_path(rel_path),
            }
        )
    return docs


def _ingest_data_helper(path: str, root: str) -> List[Dict]:
    text = _safe_read(path)
    if len(text.strip()) < 40:
        return []

    rel_path = _normalize_rel(path, root)
    kind = "automation_fixture" if "/fixtures/" in f"/{rel_path}" else "automation_data_helper"
    return [
        {
            "id": f"auto_data_{rel_path.replace('/', '_')}",
            "content": f"[Automation Data Utility: {rel_path}]\n\n{text}",
            "source": "automation_repo",
            "type": kind,
            "repo_path": rel_path,
            "tags": _tags_for_path(rel_path),
        }
    ]


def ingest_automation_repo(repo_root: str) -> List[Dict]:
    """
    Ingest automation repository artifacts for Cypress code generation grounding.
    """
    if not repo_root or not os.path.isdir(repo_root):
        print("[automation_ingest] Repo root missing or invalid; skipping.")
        return []

    docs: List[Dict] = []
    cypress_root = os.path.join(repo_root, "cypress")
    if not os.path.isdir(cypress_root):
        print("[automation_ingest] No cypress directory found; skipping.")
        return []

    for root, _, files in os.walk(cypress_root):
        for fname in sorted(files):
            path = os.path.join(root, fname)
            lower = fname.lower()
            rel_path = _normalize_rel(path, repo_root).lower()

            if lower.endswith((".cy.js", ".cy.ts")):
                docs.extend(_ingest_spec(path, repo_root))
                continue

            if any(token in rel_path for token in ("/pageobjects/", "/page_objects/", "/pages/")) and lower.endswith((".js", ".ts")):
                docs.extend(_ingest_page_object(path, repo_root))
                continue

            if lower in ("commands.js", "commands.ts") or "/support/commands" in rel_path:
                docs.extend(_ingest_command_file(path, repo_root))
                continue

            if any(token in rel_path for token in ("/fixtures/", "/data/", "/helpers/", "/utils/", "/support/")) and lower.endswith((".js", ".ts", ".json")):
                docs.extend(_ingest_data_helper(path, repo_root))

    print(f"[automation_ingest] Ingested {len(docs)} automation knowledge chunks.")
    return docs
