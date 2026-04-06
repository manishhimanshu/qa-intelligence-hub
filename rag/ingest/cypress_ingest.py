"""
Cypress automation pattern ingestion for Kapost.

This is unique to your setup — it ingests your existing Cypress spec files
and page objects so the RAG knows your real automation patterns.

When Copilot asks the RAG "how do we test the content catalog?", it gets back
real examples from YOUR codebase, not generic Cypress documentation.

Env vars:
  CYPRESS_ROOT – path to the ph project root (default: current working directory)
"""
import os
import re
from typing import List, Dict


def _extract_describe_blocks(text: str) -> List[str]:
    """
    Extract each describe/context/it block's text as a chunk.
    We keep the outer describe for context.
    """
    # Split on describe( or context( boundaries while keeping the text
    chunks = re.split(r'\n(?=\s*(?:describe|context)\s*\()', text)
    return [c.strip() for c in chunks if c.strip()]


def _ingest_spec_file(path: str, rel_path: str) -> List[Dict]:
    """Ingest a single .cy.js spec file into document chunks."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        print(f"[cypress_ingest] Failed to read {rel_path}: {e}")
        return []

    # Skip empty or near-empty files
    if len(text.strip()) < 50:
        return []

    # Extract top-level describe name if present
    outer_match = re.search(r"describe\(['\"`](.+?)['\"`]", text)
    feature_name = outer_match.group(1) if outer_match else os.path.basename(path)

    chunks = _extract_describe_blocks(text)
    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "id":      f"cypress_{rel_path.replace(os.sep, '_')}_{i}",
            "content": (
                f"[Cypress Spec: {rel_path}]\n"
                f"Feature: {feature_name}\n\n"
                f"{chunk}"
            ),
            "source":  path,
            "feature": feature_name,
            "type":    "cypress_spec",
        })
    return docs


def _ingest_page_object(path: str, rel_path: str) -> List[Dict]:
    """Ingest a page object file as a single knowledge chunk."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        print(f"[cypress_ingest] Failed to read {rel_path}: {e}")
        return []

    if len(text.strip()) < 50:
        return []

    class_match = re.search(r"class\s+(\w+)", text)
    class_name = class_match.group(1) if class_match else os.path.basename(path)

    return [{
        "id":      f"cypress_po_{rel_path.replace(os.sep, '_')}",
        "content": (
            f"[Cypress Page Object: {rel_path}]\n"
            f"Class: {class_name}\n\n"
            f"{text}"
        ),
        "source":  path,
        "class":   class_name,
        "type":    "cypress_page_object",
    }]


def _ingest_commands(path: str) -> List[Dict]:
    """Ingest commands.js as signature-level chunks so LLM knows available commands."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        print(f"[cypress_ingest] Failed to read commands.js: {e}")
        return []

    # Split at each Cypress.Commands.add boundary
    raw_commands = re.split(r'\n(?=Cypress\.Commands\.add)', text)
    docs = []
    for i, cmd in enumerate(raw_commands):
        if "Cypress.Commands.add" not in cmd:
            continue
        name_match = re.search(r"Cypress\.Commands\.add\(['\"`](\w+)['\"`]", cmd)
        cmd_name = name_match.group(1) if name_match else f"command_{i}"
        docs.append({
            "id":      f"cypress_cmd_{cmd_name}",
            "content": (
                f"[Cypress Custom Command: cy.{cmd_name}]\n"
                f"File: cypress/support/commands.js\n\n"
                f"{cmd.strip()}"
            ),
            "source":  path,
            "command": cmd_name,
            "type":    "cypress_command",
        })
    return docs


def ingest_cypress_patterns(cypress_root: str = None) -> List[Dict]:
    """
    Ingest Cypress automation patterns from the ph project:
    - All .cy.js spec files under cypress/e2e/
    - All page object files under cypress/e2e/kapost/pageObjects/
    - Custom commands from cypress/support/commands.js
    """
    cypress_root = cypress_root or os.getenv("CYPRESS_ROOT", os.getcwd())
    docs: List[Dict] = []

    e2e_dir        = os.path.join(cypress_root, "cypress", "e2e")
    page_obj_dir   = os.path.join(cypress_root, "cypress", "e2e", "kapost", "pageObjects")
    commands_file  = os.path.join(cypress_root, "cypress", "support", "commands.js")

    # ── 1. Spec files ────────────────────────────────────────────────────────
    if os.path.isdir(e2e_dir):
        for root, _, files in os.walk(e2e_dir):
            # Skip page object dir — handled separately
            if "pageObjects" in root:
                continue
            for fname in sorted(files):
                if fname.endswith(".cy.js"):
                    path     = os.path.join(root, fname)
                    rel_path = os.path.relpath(path, cypress_root)
                    docs.extend(_ingest_spec_file(path, rel_path))

    # ── 2. Page objects ──────────────────────────────────────────────────────
    if os.path.isdir(page_obj_dir):
        for root, _, files in os.walk(page_obj_dir):
            for fname in sorted(files):
                if fname.endswith(".cy.js") or fname.endswith(".js"):
                    path     = os.path.join(root, fname)
                    rel_path = os.path.relpath(path, cypress_root)
                    docs.extend(_ingest_page_object(path, rel_path))

    # ── 3. Custom commands ───────────────────────────────────────────────────
    if os.path.isfile(commands_file):
        docs.extend(_ingest_commands(commands_file))

    print(f"[cypress_ingest] Ingested {len(docs)} Cypress knowledge chunks.")
    return docs
