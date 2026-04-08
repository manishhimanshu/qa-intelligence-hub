"""
Test Case Generator
Generates structured manual test cases from Jira stories following
Kapost/Pilyr test-cases.instructions.md format:
  - TC-FEATURE-NNN IDs with Priority, Type, Steps, Expected Result
  - Role-based test cases (admin / editor / contributor / consumer)
  - Exports directly to TestRail
"""

import os
import sys
import json
import re
import requests
from collections import Counter
import sys as _sys
if _sys.platform == "win32":  # Windows corporate SSL certs only
    import truststore
    truststore.inject_into_ssl()

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# ── Path / env setup ─────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, "../../rag"))
load_dotenv(os.path.join(_DIR, "../../rag/.env"))

# ── Config ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL        = os.getenv("OPENAI_MODEL", "gpt-4o")
TESTRAIL_URL        = os.getenv("TESTRAIL_URL", "").rstrip("/")
TESTRAIL_USER       = os.getenv("TESTRAIL_USER", "")
TESTRAIL_TOKEN      = os.getenv("TESTRAIL_TOKEN", "")
TESTRAIL_PROJECT_ID = int(os.getenv("TESTRAIL_PROJECT_ID", "2"))
JIRA_URL            = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_USER           = os.getenv("JIRA_USER", "")
JIRA_TOKEN          = os.getenv("JIRA_TOKEN", "")

client = OpenAI(api_key=OPENAI_API_KEY)

# ── Domain constants ──────────────────────────────────────────────────────────
FEATURE_PREFIXES = {
    "content":      "TC-CONTENT",
    "initiative":   "TC-INIT",
    "campaign":     "TC-INIT",
    "idea":         "TC-IDEA",
    "gallery":      "TC-GALLERY",
    "member":       "TC-MEMBERS",
    "setting":      "TC-SETTINGS",
    "calendar":     "TC-CALENDAR",
    "search":       "TC-SEARCH",
    "dashboard":    "TC-DASH",
    "notification": "TC-NOTIF",
    "napa":         "TC-DASH",
}

ROLES = ["admin", "editor", "contributor", "consumer"]

PRIORITY_MAP = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}
TYPE_MAP     = {
    "Functional":  "⚙️",
    "Regression":  "♻️",
    "Smoke":       "💨",
    "Integration": "🔗",
    "Negative":    "❌",
}
TESTRAIL_PRIORITY = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}

# ── Edit helper ───────────────────────────────────────────────────────────────
_PRIS  = ["Critical", "High", "Medium", "Low"]
_TYPES = ["Functional", "Regression", "Smoke", "Integration", "Negative"]
_AUTOS = ["Manual", "Candidate", "Automated"]

def _safe_idx(lst, val, default=0):
    try: return lst.index(val)
    except ValueError: return default

def _get_edited(tc: dict, pfx: str) -> dict:
    """Merge session_state edits back into a case dict before export."""
    return {
        **tc,
        "title":             st.session_state.get(f"{pfx}_title",       tc.get("title", "")),
        "priority":          st.session_state.get(f"{pfx}_priority",    tc.get("priority", "Medium")),
        "type":              st.session_state.get(f"{pfx}_type",        tc.get("type", "Functional")),
        "automation_status": st.session_state.get(f"{pfx}_auto",        tc.get("automation_status", "Manual")),
        "test_data":         st.session_state.get(f"{pfx}_test_data",   tc.get("test_data", "N/A")),
        "preconditions":     st.session_state.get(f"{pfx}_prec",        tc.get("preconditions", "")),
        "steps":             st.session_state.get(f"{pfx}_steps",       tc.get("steps", "")),
        "expected_result":   st.session_state.get(f"{pfx}_expected",    tc.get("expected_result", "")),
        "jira_ref":          st.session_state.get(f"{pfx}_jira_ref",    tc.get("jira_ref", "")),
    }

st.set_page_config(page_title="Test Case Generator", page_icon="📝", layout="wide")


# ── Helpers ───────────────────────────────────────────────────────────────────
def rag_query(query: str, top_k: int = 20) -> list:
    from get_relevant_docs import get_relevant_docs
    return get_relevant_docs(query, top_k=top_k)


def _adf_to_markdown(node) -> str:
    """
    Convert Atlassian Document Format (ADF) JSON to markdown-structured text,
    preserving headings, bullet/numbered lists, and paragraph breaks.
    """
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(_adf_to_markdown(n) for n in node)
    if not isinstance(node, dict):
        return str(node)
    ntype   = node.get("type", "")
    content = node.get("content") or []
    if ntype == "text":
        return node.get("text", "")
    if ntype == "doc":
        parts = [_adf_to_markdown(c) for c in content]
        return "\n".join(p for p in parts if p.strip())
    if ntype == "paragraph":
        return "".join(_adf_to_markdown(c) for c in content)
    if ntype == "heading":
        level = node.get("attrs", {}).get("level", 2)
        inner = "".join(_adf_to_markdown(c) for c in content)
        return "#" * level + " " + inner
    if ntype == "bulletList":
        return "\n".join(_adf_to_markdown(c) for c in content)
    if ntype == "orderedList":
        lines = []
        for i, c in enumerate(content, 1):
            text = _adf_to_markdown(c).lstrip("- ").strip()
            lines.append(f"{i}. {text}")
        return "\n".join(lines)
    if ntype == "listItem":
        inner = "\n".join(_adf_to_markdown(c) for c in content).strip()
        return "- " + inner
    if ntype == "hardBreak":
        return "\n"
    if ntype == "rule":
        return "---"
    if ntype == "codeBlock":
        inner = "".join(_adf_to_markdown(c) for c in content)
        return f"```\n{inner}\n```"
    if ntype == "blockquote":
        inner = "\n".join(_adf_to_markdown(c) for c in content)
        return "> " + inner
    # Fallback: recurse into content
    if content:
        return "".join(_adf_to_markdown(c) for c in content)
    return node.get("text", "")


@st.cache_data(show_spinner="Loading Jira AC field metadata…")
def _get_jira_field_ids() -> tuple[str, str]:
    """Return (ac_field_id, steps_to_reproduce_field_id) from Jira field metadata."""
    if not (JIRA_URL and JIRA_USER and JIRA_TOKEN):
        return "", ""
    try:
        r = requests.get(
            f"{JIRA_URL}/rest/api/3/field",
            auth=(JIRA_USER, JIRA_TOKEN),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        ac_id, str_id = "", ""
        for field in r.json():
            name_lower = field.get("name", "").lower().strip()
            # Exact match first, then broader fallback
            if name_lower == "acceptance criteria" and not ac_id:
                ac_id = field["id"]
            elif "acceptance criteria" in name_lower and not ac_id:
                ac_id = field["id"]
            if name_lower == "steps to reproduce" and not str_id:
                str_id = field["id"]
            elif ("steps to reproduce" in name_lower or "steps_to_reproduce" in name_lower) and not str_id:
                str_id = field["id"]
        return ac_id, str_id
    except Exception:
        return "", ""


# Shared singleton loader — ONE @st.cache_resource across all pages prevents triple FAISS load
sys.path.insert(0, os.path.join(_DIR, ".."))
from shared_vectorstore import load_vectorstore as _load_vectorstore


@st.cache_data(show_spinner="Loading Jira stories from RAG…")
def load_jira_stories() -> list:
    """
    Iterate ALL documents in the FAISS docstore to return every indexed Jira story.
    Using docstore iteration (not similarity search) avoids the top_k cap.
    """
    vs = _load_vectorstore()

    if vs is None:
        return []

    stories, seen = [], set()
    for langchain_doc in vs.docstore._dict.values():
        if not hasattr(langchain_doc, "metadata"):
            continue
        meta = langchain_doc.metadata
        if meta.get("source") != "jira":
            continue
        doc_id = meta.get("id", "")
        key    = doc_id.split("_chunk")[0] if "_chunk" in doc_id else doc_id
        if not key or key in seen:
            continue
        seen.add(key)
        content    = langchain_doc.page_content
        summary    = key
        issuetype  = meta.get("type", "Story")
        status     = meta.get("status", "Unknown")
        for line in content.splitlines():
            if re.match(r'summary:', line, re.IGNORECASE):
                summary = line.split(":", 1)[-1].strip()
                break
        stories.append({"key": key, "summary": summary,
                         "issuetype": issuetype, "status": status, "content": content})

    return sorted(stories, key=lambda x: (
        x["key"].split("-")[0],
        int(re.search(r'\d+$', x["key"]).group(0)) if re.search(r'\d+$', x["key"]) else 0
    ))


def detect_feature_prefix(summary: str) -> str:
    s = summary.lower()
    for kw, prefix in FEATURE_PREFIXES.items():
        if kw in s:
            return prefix
    return "TC-FEATURE"


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_story_from_jira(story_key: str) -> str:
    """
    Fetch full story details from the live Jira API:
    - All navigable fields (captures custom AC and Steps to Reproduce fields)
    - Structured markdown output preserving headings and lists
    """
    if not (JIRA_URL and JIRA_USER and JIRA_TOKEN):
        return ""
    try:
        ac_field_id, str_field_id = _get_jira_field_ids()

        url = f"{JIRA_URL}/rest/api/3/issue/{story_key}"
        r = requests.get(
            url,
            auth=(JIRA_USER, JIRA_TOKEN),
            headers={"Accept": "application/json"},
            params={"fields": "*navigable"},
            timeout=15,
        )
        if r.status_code != 200:
            return ""
        fields = r.json().get("fields", {})

        summary    = fields.get("summary", "")
        issuetype  = (fields.get("issuetype") or {}).get("name", "")
        status     = (fields.get("status") or {}).get("name", "")
        priority   = (fields.get("priority") or {}).get("name", "")
        labels     = ", ".join(fields.get("labels") or [])
        components = ", ".join(c.get("name", "") for c in (fields.get("components") or []))

        desc_md = _adf_to_markdown(fields.get("description") or {})

        def _extract_custom(field_id: str) -> str:
            """Extract ADF or plain-text value from a custom field."""
            if not field_id:
                return ""
            val = fields.get(field_id)
            if not val:
                # fallback: scan all custom fields whose name matches
                for fkey, fval in fields.items():
                    if fkey.startswith("customfield_") and fval:
                        if field_id in fkey:
                            val = fval
                            break
            if not val:
                return ""
            if isinstance(val, dict):
                return _adf_to_markdown(val)
            if isinstance(val, str):
                return val
            return ""

        ac_md  = _extract_custom(ac_field_id)
        str_md = _extract_custom(str_field_id)

        # Fallback: scan all custom fields by keyword if dedicated fields empty
        if not ac_md or not str_md:
            for fkey, fval in fields.items():
                if not fkey.startswith("customfield_") or not fval:
                    continue
                fname = next(
                    (f.get("name", "") for f in (getattr(fetch_story_from_jira, "_fields_cache", []))
                     if f.get("id") == fkey), fkey
                ).lower()
                if "acceptance" in fname and not ac_md:
                    ac_md = _adf_to_markdown(fval) if isinstance(fval, dict) else str(fval)
                if ("steps to reproduce" in fname or "steps_to_reproduce" in fname) and not str_md:
                    str_md = _adf_to_markdown(fval) if isinstance(fval, dict) else str(fval)

        parts = [
            f"Jira Issue: {story_key}",
            f"Type: {issuetype} | Priority: {priority} | Status: {status}",
            f"Labels: {labels} | Components: {components}",
            f"Summary: {summary}",
        ]
        if desc_md.strip():
            parts.append(f"\n## Description\n{desc_md}")
        if ac_md.strip():
            parts.append(f"\n## Acceptance Criteria\n{ac_md}")
        if str_md.strip():
            parts.append(f"\n## Steps to Reproduce\n{str_md}")
        return "\n".join(parts)
    except Exception:
        return ""


@st.cache_data(show_spinner="Fetching story content…")
def get_story_content(story_key: str, rag_content: str) -> str:
    live = fetch_story_from_jira(story_key)
    return live if live else rag_content


@st.cache_data(show_spinner="Finding existing TestRail test cases…")
def get_existing_test_cases(story_key: str, summary: str) -> list:
    # top_k=40 so we search a wider slice of the 4,105 TestRail chunks;
    # only TestRail docs are kept, so the prompt stays lean.
    docs = rag_query(f"{story_key} {summary}", top_k=40)

    # Aggregate ALL chunks per case (cases can be split across multiple 800-char chunks)
    case_chunks: dict = {}   # case_id → list of content strings
    for doc in docs:
        doc_id = doc.get("id", "")
        if not doc_id.startswith("testrail_"):
            continue
        m = re.search(r'testrail_(\d+)', doc_id)
        case_id = f"C{m.group(1)}" if m else doc_id
        raw = doc.get("content", "")
        # Strip HTML inline
        clean = re.sub(r'<br\s*/?>', '\n', raw)
        clean = re.sub(r'<[^>]+>', '', clean)
        # Strip literal string "None" values left by TestRail for empty fields
        clean = re.sub(r'(?m)^(Preconditions|Expected Result):\s*None\s*$', '', clean)
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        case_chunks.setdefault(case_id, []).append(clean)

    tcs = []
    for case_id, chunks in case_chunks.items():
        # Merge all chunks, dedup repeated header lines, cap at 1500 chars
        merged = "\n\n".join(chunks)
        # Remove duplicate header lines that repeat across chunk boundaries
        seen_lines: set = set()
        deduped_lines = []
        _dedup_headers = (
            "TestRail Case:", "Suite:", "Priority:", "Title:",
            "Preconditions:", "Steps:", "Expected Result:", "Section:",
        )
        for line in merged.splitlines():
            key = line.strip()
            if key and key in seen_lines and any(
                key.startswith(h) for h in _dedup_headers
            ):
                continue
            seen_lines.add(key)
            deduped_lines.append(line)
        merged = "\n".join(deduped_lines).strip()[:1500]
        tcs.append({"id": case_id, "content": merged})
    return tcs


@st.cache_data(show_spinner="Finding similar Cypress automation patterns…")
def get_cypress_patterns(summary: str, top_k: int = 5) -> str:
    """
    Query FAISS for the most semantically similar Cypress spec/page-object
    chunks and return them as a condensed context block.
    Only 'cypress'-sourced docs are kept; each is capped at 300 chars
    so the total stays well under 1500 chars.
    """
    docs = rag_query(summary, top_k=30)   # cast wide, filter below
    patterns = []
    seen_ids = set()
    for doc in docs:
        src = doc.get("source", "")
        if src != "cypress":
            continue
        doc_id = doc.get("id", "")
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        snippet = doc.get("content", "").strip()[:300]
        patterns.append(f"// {doc_id}\n{snippet}")
        if len(patterns) >= top_k:
            break
    return "\n\n".join(patterns)


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_jira_comments(story_key: str, max_chars: int = 1500) -> str:
    """
    Fetch comments for a Jira issue via the live API.
    Filters out trivial status-update comments (< 30 chars) and
    caps total text at max_chars to control token usage.
    Returns a formatted string, or '' if none / API unavailable.
    """
    if not (JIRA_URL and JIRA_USER and JIRA_TOKEN):
        return ""
    try:
        url = f"{JIRA_URL}/rest/api/3/issue/{story_key}/comment"
        r = requests.get(
            url,
            auth=(JIRA_USER, JIRA_TOKEN),
            headers={"Accept": "application/json"},
            params={"maxResults": 50, "orderBy": "-created"},
            timeout=15,
        )
        if r.status_code != 200:
            return ""
        comments = r.json().get("comments", [])
        parts = []
        total = 0
        for c in comments:
            author = (c.get("author") or {}).get("displayName", "Unknown")
            body   = _adf_to_markdown(c.get("body") or {}).strip()
            if len(body) < 30:          # skip trivial one-liners
                continue
            chunk = f"[{author}]: {body}"
            if total + len(chunk) > max_chars:
                remaining = max_chars - total
                if remaining > 60:
                    parts.append(chunk[:remaining] + "…")
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n\n".join(parts)
    except Exception:
        return ""


def extract_comments(content: str) -> str:
    """Extract the ## Comments section from RAG-sourced story content (fallback)."""
    lines, in_comments = [], False
    _stop = re.compile(r'^#{1,4}\s', re.IGNORECASE)
    for line in content.splitlines():
        s = line.strip()
        if re.search(r'^#{1,4}\s+comments', s, re.IGNORECASE):
            in_comments = True
            continue
        if in_comments:
            if _stop.match(s):
                break
            lines.append(line)
    return "\n".join(lines).strip()


def extract_acceptance_criteria(content: str) -> list:
    """
    Extract Acceptance Criteria lines from structured story content.
    Preserves group/parent context so sub-bullets carry their parent label.

    Handles all common Jira AC formats:
      1. Pure bullet/numbered lists           (- item, * item, 1. item)
      2. ADF headings + bullets               (## Scenario → converted by _adf_to_markdown)
      3. Colon-terminated labels + bullets    (Search behavior: → - bullet)
      4. Plain short labels + bullets         (Some heading → * step)
      5. Gherkin Given/When/Then/And/But      (always AC items, never headers)
      6. Plain prose sentences                (The system should..., As an admin...)
      7. Mixed formats within one AC field
    """
    ac, in_ac = [], False

    _stop_named = re.compile(
        r'^#{1,4}\s+(definition of done|notes?|out of scope|assumptions?|dependencies|steps to reproduce)',
        re.IGNORECASE,
    )
    _stop_unnumbered = re.compile(
        r'^(definition of done|notes?:|out of scope|assumptions?|dependencies|steps to reproduce|---)',
        re.IGNORECASE,
    )
    _md_heading   = re.compile(r'^#{1,4}\s+(.+)')
    _colon_header = re.compile(r'^[^-*•\d].*:\s*$')          # ends with colon, no bullet
    _bullet_start = re.compile(r'^[-*•]|^\d+\.')
    _strip_bullet = re.compile(r'^[-*•]\s*|^\d+\.\s+')
    _gherkin      = re.compile(r'^(Given|When|Then|And|But)\b', re.IGNORECASE)
    _sentence_end = re.compile(r'[.?!]\s*$')                  # ends with sentence punctuation

    lines = [ln.strip() for ln in content.splitlines()]
    current_group = ""
    i = 0

    while i < len(lines):
        s = lines[i]
        i += 1
        if not s:
            continue

        if re.search(r'acceptance criteria', s, re.IGNORECASE):
            in_ac = True
            current_group = ""
            continue

        if not in_ac:
            continue

        # ── Section boundary ─────────────────────────────────────────────────
        if _stop_named.match(s) or _stop_unnumbered.match(s):
            break

        # ── ADF-converted heading → group header ─────────────────────────────
        m = _md_heading.match(s)
        if m:
            current_group = m.group(1).strip()
            continue

        # ── Gherkin keywords → always an AC item, never a header ─────────────
        if _gherkin.match(s):
            ac.append(f"{current_group}: {s}" if current_group else s)
            continue

        # ── Bullet / numbered item ────────────────────────────────────────────
        if _bullet_start.match(s):
            clean = _strip_bullet.sub('', s).strip()
            if clean:
                ac.append(f"{current_group}: {clean}" if current_group else clean)
            continue

        # ── Colon-terminated label → group header ─────────────────────────────
        if _colon_header.match(s):
            current_group = s.rstrip(':').strip()
            continue

        # ── Plain non-bullet line: decide header vs AC item ──────────────────
        # Group header ONLY when ALL three conditions hold:
        #   (a) short label (≤ 6 words) — typical section titles are terse
        #   (b) no sentence-ending punctuation (. ? !)
        #   (c) the NEXT non-empty line is a bullet/numbered item
        # Everything else (long prose, sentences, short statements not followed
        # by bullets) is treated directly as an AC item.
        next_s = next((lines[j] for j in range(i, len(lines)) if lines[j]), "")
        is_short_label = (
            len(s.split()) <= 6
            and not _sentence_end.search(s)
            and _bullet_start.match(next_s)
        )
        if is_short_label:
            current_group = s
        else:
            ac.append(f"{current_group}: {s}" if current_group else s)

    return ac


def extract_steps_to_reproduce(content: str) -> list:
    """Extract Steps to Reproduce lines from structured story content."""
    steps, in_steps = [], False
    _stop_sections = re.compile(
        r'^(#{1,4}\s|acceptance criteria|definition of done|notes?:|out of scope|---)',
        re.IGNORECASE,
    )
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.search(r'steps to reproduce', s, re.IGNORECASE):
            in_steps = True
            continue
        if in_steps:
            if _stop_sections.match(s):
                break
            clean = re.sub(r'^[-*•]\s+|^\d+\.\s+', '', s).strip()
            if clean:
                steps.append(clean)
    return steps


def extract_description(content: str) -> str:
    """Extract the Description section from structured story content."""
    desc, in_desc = [], False
    _stop = re.compile(r'^#{1,4}\s', re.IGNORECASE)
    for line in content.splitlines():
        s = line.strip()
        if re.search(r'^#{1,4}\s+description', s, re.IGNORECASE):
            in_desc = True
            continue
        if in_desc:
            if _stop.match(s):
                break
            desc.append(line)
    return "\n".join(desc).strip()


@st.cache_data(show_spinner=False, ttl=3600)
def generate_test_cases(
    story_key: str,
    summary: str,
    description: str,     # full description text
    ac_list: tuple,       # tuple so it's hashable for cache key
    str_list: tuple,
    comments: str,        # pre-fetched comment text ('' if disabled)
    cypress_context: str, # relevant Cypress patterns from RAG ('' if none)
    existing_tcs: tuple,
    selected_roles: tuple,
    feature_prefix: str,
) -> list:
    # P1-fix: send only clean titles so GPT can identify duplicates reliably.
    # Raw content (TestRail Case ID, Suite, Priority noise) wastes tokens and
    # causes GPT to miss duplicate detection when only the title matches.
    existing_titles = []
    for tc in existing_tcs:
        try:
            raw_content = json.loads(tc).get("content", "")
        except (json.JSONDecodeError, TypeError):
            raw_content = tc if isinstance(tc, str) else ""
        title_match = re.search(r'Title:\s*(.+)', raw_content)
        if title_match:
            existing_titles.append(title_match.group(1).strip()[:120])
    existing_block = (
        "\n".join(f"- {t}" for t in existing_titles) or "None"
    )
    desc_block = description.strip() or "Not provided."

    # P1-fix: when AC is empty, extract numbered/bulleted items from Description
    # so the per-AC coverage rules still apply to description-only stories
    effective_ac = list(ac_list)
    if not effective_ac and description.strip():
        for line in description.splitlines():
            s = line.strip()
            clean = re.sub(r'^[-*•]\s+|^\d+\.\s+', '', s).strip()
            if clean and len(clean) > 15:   # skip very short noise lines
                effective_ac.append(clean)

    ac_fallback = (
        "No Acceptance Criteria found — infer test cases from the Description and Summary above."
        if not effective_ac
        else ""
    )
    ac_block = (
        "\n".join(f"AC-{i:02d}: {a}" for i, a in enumerate(effective_ac, 1))
        or ac_fallback
    )
    ac_count = len(effective_ac) or 1   # floor at 1 to avoid "AC-01 … AC-00" in prompt
    str_block = (
        "\n".join(f"{i}. {s}" for i, s in enumerate(str_list, 1))
        or "Not provided."
    )
    roles_block = ", ".join(selected_roles) or "admin, editor, contributor, consumer"
    comments_block = comments.strip() or None
    comments_section = (
        f"\nComments (BA/PO clarifications — treat as supplementary requirements):\n{comments_block}\n"
        if comments_block else ""
    )
    cypress_section = (
        f"\nExisting Cypress Automation Patterns (use to inform automation_status and step phrasing):\n{cypress_context}\n"
        if cypress_context.strip() else ""
    )

    prompt = f"""You are a senior QA engineer following Kapost/Pilyr testing standards.
The platform is a B2B content marketing SaaS with 4 user roles: admin, editor, contributor, consumer.

Jira Story: {story_key} — {summary}

Description:
{desc_block}

Acceptance Criteria ({ac_count} items — each MUST be covered):
{ac_block}

Steps to Reproduce (use to inform negative/regression cases):
{str_block}
{comments_section}
Existing TestRail Test Cases (do NOT duplicate these):
{existing_block}
{cypress_section}
Roles to cover: {roles_block}
Feature prefix for TC IDs: {feature_prefix}

══════════════════════════════════════════════════════
COVERAGE MANDATE
══════════════════════════════════════════════════════
There are {ac_count} AC items above (AC-01 … AC-{ac_count:02d}).

STEP 1 — PER-AC CASES (do this first, in order):
  Write one dedicated positive test case per AC item.
  Tag each title: "[AC-XX] <what is being verified>"
  Example: "[AC-05] Search box displays cross icon only when text is entered"

  ONLY group multiple AC items into one test case when they are literally
  sub-steps of the exact same indivisible user action
  (e.g. "1. Click Save → 2. Spinner shows → 3. Toast appears" = one flow).
  Even then, every AC number in the group must appear in the title tag.
  When in doubt — do NOT group. Give each item its own test case.

STEP 2 — NEGATIVE CASES:
  For every AC item that involves a UI control, an input field, a conditional
  display rule, or a state change — write one negative/boundary test case.
  Tag: "[AC-XX – Negative] <what fails or is invalid>"

STEP 3 — SUPPLEMENTARY (add after all per-AC cases):
  - 1–3 role permission cases: contributor and consumer trying to use the feature
  - 1–2 edge cases: empty state, dependency deletion, concurrent edit, reload
  - 1 error-handling case: network failure or server 500

Expected output range: {ac_count} to {ac_count * 2} test cases.
If you are producing fewer than {ac_count} cases you are grouping too aggressively — stop and revise.
Do NOT stop generating until every AC-01 through AC-{ac_count:02d} is covered.
══════════════════════════════════════════════════════

Return ONLY a valid JSON array — no markdown fences, no explanation:
[
  {{
    "tc_id":             "{feature_prefix}-001",
    "title":             "[AC-XX] [Action] [Object] verifies [Expected Outcome]",
    "priority":          "Critical|High|Medium|Low",
    "type":              "Functional|Regression|Smoke|Integration|Negative",
    "preconditions":     "Role required, existing data state, feature flags if any",
    "steps":             "1. First step\\n2. Second step\\n3. Third step",
    "expected_result":   "Observable, verifiable outcome after all steps",
    "test_data":         "CY_Test | specific values, or 'N/A'",
    "automation_status": "Automated|Manual|Candidate",
    "roles_covered":     ["admin"]
  }}
]

Rules:
- Sequential IDs: {feature_prefix}-001, {feature_prefix}-002, etc.
- Priority: Critical = core/data-loss, High = main flows, Medium = edge cases, Low = cosmetic
- automation_status: "Candidate" for stable repeatable flows, "Manual" for exploratory,
  "Automated" if it clearly maps to an existing Cypress pattern
- Always prefix test data with "CY_Test |"
- ROLE SCOPING RULE:
  ALWAYS include at least one negative case for contributor and one for consumer
  (cannot perform write/admin actions). Generate full role-specific flows ONLY when
  the story explicitly names a role or behaviour clearly differs by role.
  Do NOT duplicate the full happy-path per role — role cases must focus on
  access-control boundaries (403 / permission denied / feature hidden).
  When in doubt, use admin for positive flows."""

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=16000,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    # P1-fix: recover from truncated JSON — trim to last complete object
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        last_close = raw.rfind("},")
        if last_close == -1:
            last_close = raw.rfind("}")
        if last_close != -1:
            trimmed = raw[:last_close + 1].rstrip(",").strip()
            if not trimmed.startswith("["):
                trimmed = "[" + trimmed
            trimmed += "]"
            try:
                cases = json.loads(trimmed)
                st.warning(
                    f"⚠️ GPT response was truncated — recovered {len(cases)} of the generated "
                    "test cases. Consider re-generating or splitting into smaller stories.",
                    icon="⚠️",
                )
                return cases
            except json.JSONDecodeError:
                pass
        raise


@st.cache_data(show_spinner=False, ttl=3600)
def generate_bulk_test_cases(
    stories_data: tuple,     # tuple of JSON strings, one serialised story dict each
    existing_tcs_json: str,  # JSON string of existing TC summaries
    cypress_context: str,    # relevant Cypress patterns from RAG
    selected_roles: tuple,
    feature_prefix: str,
) -> list:
    """Generate a unified, deduplicated feature test suite from multiple Jira stories."""
    stories     = [json.loads(s) for s in stories_data]
    roles_block = ", ".join(selected_roles) or "admin, editor, contributor, consumer"
    all_keys    = ", ".join(s["key"] for s in stories)

    story_sections = []
    for s in stories:
        ac_items   = s.get("ac_list", [])
        ac_lines   = "\n".join(f"  AC-{i:02d}: {a}" for i, a in enumerate(ac_items, 1)) or "  Not specified."
        str_lines  = "\n".join(f"  {i}. {step}" for i, step in enumerate(s.get("str_list", []), 1)) or "  Not specified."
        desc_text     = (s.get("desc", "") or "")[:800]
        comments_text = (s.get("comments", "") or "").strip()
        comments_line = f"\nComments: {comments_text[:600]}" if comments_text else ""
        story_sections.append(
            f"--- {s['key']}: {s['summary']} ---\n"
            f"Description: {desc_text or 'Not provided.'}\n"
            f"Acceptance Criteria ({len(ac_items)} items):\n{ac_lines}\n"
            f"Steps to Reproduce:\n{str_lines}"
            f"{comments_line}"
        )

    stories_block = "\n\n".join(story_sections)

    prompt = (
        "You are a senior QA engineer following Kapost/Pilyr testing standards.\n"
        "The platform is a B2B content marketing SaaS with 4 user roles: admin, editor, contributor, consumer.\n\n"
        f"You are generating a UNIFIED test suite for a FEATURE spanning {len(stories)} Jira stories/bugs.\n"
        f"Stories in this feature: {all_keys}\n\n"
        "Read ALL stories below, understand the full feature scope, then generate a "
        "complete, non-redundant test suite covering the entire feature.\n"
        "Tag each test case with the most relevant `jira_ref` (or \"General\" for cross-story tests).\n\n"
        f"{stories_block}\n\n"
        f"Existing TestRail Test Cases (do NOT duplicate):\n{existing_tcs_json or 'None'}\n\n"
        + (f"Existing Cypress Automation Patterns (use to inform automation_status):\n{cypress_context}\n\n" if cypress_context.strip() else "")
        + f"Roles to cover: {roles_block}\n"
        f"Feature prefix for TC IDs: {feature_prefix}\n\n"
        "Generate a unified, deduplicated test suite covering ALL of the following:\n"
        "1. Happy path for each acceptance criterion across all stories\n"
        "2. Cross-story integration flows (where story A creates something story B uses)\n"
        "3. Negative / validation cases (invalid data, missing required fields, wrong format)\n"
        "4. Role-based access for the feature as a whole\n"
        "5. Edge cases: empty state, dependency deletion, concurrent edits, mid-flow reload\n"
        "6. Regression risk areas most likely to break if any story changes\n\n"
        "AC TYPE CLASSIFICATION — apply this per-AC when deciding coverage:\n"
        "  TYPE A (Explicit functional): AC describes exact UI action and measurable outcome → 1 positive + 1 negative\n"
        "  TYPE B (Rule/constraint): AC describes a business rule, permission, or limit → 1 in-bounds + 1 boundary/limit test\n"
        "  TYPE C (Non-functional): AC covers error messages, performance, UX, or display only → 1 positive (verify message/display)\n"
        "You MUST produce at least one test case per AC item (AC-01 .. AC-N) across all stories listed.\n\n"
        "Return ONLY a valid JSON array — no markdown fences, no explanation:\n"
        "[\n"
        "  {\n"
        f'    \"tc_id\":             \"{feature_prefix}-001\",\n'
        '    \"jira_ref\":          \"STUD-XXXX or General\",\n'
        '    \"title\":             \"[Action] [Object] verifies [Expected Outcome]\",\n'
        '    \"priority\":          \"Critical|High|Medium|Low\",\n'
        '    \"type\":              \"Functional|Regression|Smoke|Integration|Negative\",\n'
        '    \"preconditions\":     \"Role required, existing data state, feature flags if any\",\n'
        '    \"steps\":             \"1. First step\\\\n2. Second step\",\n'
        '    \"expected_result\":   \"Observable, verifiable outcome after all steps\",\n'
        '    \"test_data\":         \"CY_Test | specific values, or N/A\",\n'
        '    \"automation_status\": \"Automated|Manual|Candidate\",\n'
        '    \"roles_covered\":     [\"admin\"]\n'
        "  }\n"
        "]\n\n"
        "Rules:\n"
        f"- Sequential IDs: {feature_prefix}-001, {feature_prefix}-002, etc.\n"
        "- jira_ref: the story key this test primarily validates, or \"General\" for cross-story tests\n"
        "- Priority: Critical = core/data-loss flows, High = main flows, Medium = edge cases, Low = cosmetic\n"
        "- automation_status: \"Candidate\" for stable repeatable flows, \"Manual\" for exploratory, "
        "\"Automated\" for clear Cypress pattern matches\n"
        "- Always prefix test data with \"CY_Test |\"\n"
        "- Minimum one negative case per acceptance criterion\n"
        "- Do NOT generate duplicate test cases across stories\n"
        "- ROLE SCOPING RULE:\n"
        "  ALWAYS generate:\n"
        "    - At least one negative case for contributor (cannot perform write/admin actions on this feature)\n"
        "    - At least one negative case for consumer (cannot perform write/admin/editor actions on this feature)\n"
        "  Generate FULL additional role-specific flows ONLY when:\n"
        "    a) A story explicitly names a role (e.g. 'admin can...', 'editor should not...'), OR\n"
        "    b) The feature clearly behaves differently between the listed roles.\n"
        "  Do NOT duplicate the full happy-path flow per role — role cases must focus on access-control\n"
        "  boundaries (403 / permission denied / feature hidden). When in doubt, use admin for positive flows."
    )

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


# ── TestRail API ──────────────────────────────────────────────────────────────
def _tr_auth():
    return (TESTRAIL_USER, TESTRAIL_TOKEN)


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_testrail_case_live(case_id_str: str) -> dict | None:
    """
    Fetch a single TestRail case by ID directly from the API.
    Returns a normalised dict with steps/preconditions/expected_result,
    or None if unavailable.
    """
    if not (TESTRAIL_URL and TESTRAIL_USER and TESTRAIL_TOKEN):
        return None
    numeric_id = re.sub(r'\D', '', case_id_str)
    if not numeric_id:
        return None
    try:
        url = f"{TESTRAIL_URL.rstrip('/')}/index.php?/api/v2/get_case/{numeric_id}"
        r = requests.get(url, auth=_tr_auth(), timeout=10)
        if r.status_code != 200:
            return None
        c = r.json()

        def _strip(text) -> str:
            if not text:
                return ""
            text = re.sub(r'<br\s*/?>', '\n', str(text))
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text.strip()

        steps_sep  = c.get("custom_steps_separated") or []
        if steps_sep:
            step_lines = []
            for i, s in enumerate(steps_sep, 1):
                if isinstance(s, dict):
                    step_lines.append(f"Step {i}: {_strip(s.get('content',''))}")
                    exp = _strip(s.get("expected", ""))
                    if exp:
                        step_lines.append(f"  Expected: {exp}")
            steps = "\n".join(step_lines)
        else:
            steps = _strip(c.get("custom_steps", ""))

        expected  = _strip(c.get("custom_expected", ""))
        preconds  = _strip(c.get("custom_preconds", ""))
        if preconds.lower() == "none":
            preconds = ""
        if expected.lower() == "none":
            expected = ""

        priority_map = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
        return {
            "title":           c.get("title", ""),
            "priority":        priority_map.get(c.get("priority_id"), "Medium"),
            "preconditions":   preconds,
            "steps":           steps,
            "expected_result": expected,
        }
    except Exception:
        return None


@st.cache_data(show_spinner="Loading TestRail suites…")
def get_testrail_suites() -> list:
    """Return all suites for the configured TestRail project."""
    if not TESTRAIL_URL:
        return []
    try:
        url = f"{TESTRAIL_URL}/index.php?/api/v2/get_suites/{TESTRAIL_PROJECT_ID}"
        r = requests.get(url, auth=_tr_auth(), timeout=15)
        r.raise_for_status()
        data   = r.json()
        suites = data if isinstance(data, list) else data.get("suites", [])
        return [{"id": s["id"], "name": s["name"]} for s in suites]
    except Exception:
        return []


@st.cache_data(show_spinner="Loading TestRail sections…")
def get_testrail_sections(suite_id: int) -> list:
    """Return all sections for a given suite."""
    if not TESTRAIL_URL:
        return []
    try:
        url = f"{TESTRAIL_URL}/index.php?/api/v2/get_sections/{TESTRAIL_PROJECT_ID}"
        r = requests.get(url, auth=_tr_auth(), params={"suite_id": suite_id}, timeout=15)
        r.raise_for_status()
        data     = r.json()
        sections = data if isinstance(data, list) else data.get("sections", [])
        return [{"id": s["id"], "name": s["name"]} for s in sections]
    except Exception:
        return []


def export_to_testrail(cases: list, suite_id: int, section_id: int) -> list:
    results = []
    for case in cases:
        raw_steps = case.get("steps", "")
        overall_expected = case.get("expected_result", "")

        # P3-fix: parse "Step N: … \n  Expected: …" pairs produced by TYPE C prompt
        # and assign per-step expected results instead of dumping everything on last step.
        step_objs = []
        current_content = None
        current_expected = ""
        _step_re  = re.compile(r'^\s*(?:\d+\.\s*|Step\s*\d+:\s*)(.*)', re.IGNORECASE)
        _exp_re   = re.compile(r'^\s*(?:Expected|Expected Result):\s*(.*)', re.IGNORECASE)

        for line in raw_steps.splitlines():
            s = line.strip()
            if not s:
                continue
            m_step = _step_re.match(s)
            m_exp  = _exp_re.match(s)
            if m_step:
                # Flush previous step
                if current_content is not None:
                    step_objs.append({"content": current_content, "expected": current_expected})
                current_content  = m_step.group(1).strip()
                current_expected = ""
            elif m_exp and current_content is not None:
                current_expected = m_exp.group(1).strip()
            elif current_content is not None:
                # Continuation line — append to current step content
                current_content += " " + s

        if current_content is not None:
            step_objs.append({"content": current_content, "expected": current_expected})

        # If no structured steps were found, fall back to plain split
        if not step_objs and raw_steps.strip():
            for line in raw_steps.splitlines():
                clean = re.sub(r'^\d+\.\s*', '', line.strip())
                if clean:
                    step_objs.append({"content": clean, "expected": ""})

        # Assign overall expected result to the last step if it has none
        if step_objs and overall_expected and not step_objs[-1]["expected"]:
            step_objs[-1]["expected"] = overall_expected

        payload = {
            "title":                  case["title"],
            "type_id":                1,
            "priority_id":            TESTRAIL_PRIORITY.get(case.get("priority", "Medium"), 3),
            "custom_preconds":        case.get("preconditions", ""),
            "custom_steps_separated": step_objs,
            "custom_expected":        overall_expected,
            "refs":                   case.get("jira_ref", case.get("tc_id", "")),
            "suite_id":               suite_id,
        }
        try:
            url = f"{TESTRAIL_URL}/index.php?/api/v2/add_case/{section_id}"
            r = requests.post(url, json=payload, auth=_tr_auth(), timeout=15)
            r.raise_for_status()
            resp = r.json()
            results.append({"title": case["title"], "id": resp.get("id"), "status": "✅ Created"})
        except Exception as e:
            results.append({"title": case["title"], "id": None, "status": f"❌ {e}"})
    return results


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("📝 Test Case Generator")
st.caption("Generate structured manual test cases from Jira stories — export directly to TestRail")

stories = load_jira_stories()
if not stories:
    st.error("No Jira stories found in RAG. Run `python rag/ingest_all.py` to build the index.")
    st.stop()

# ── Sidebar filters & role selector ──────────────────────────────────────────
with st.sidebar:
    st.subheader("🔎 Story Filters")
    issue_types     = sorted(set(s["issuetype"] for s in stories))
    statuses        = sorted(set(s["status"]    for s in stories))
    sel_types       = st.multiselect("Issue Type", issue_types,  default=issue_types)
    sel_statuses    = st.multiselect("Status",     statuses,     default=statuses)
    st.divider()
    st.subheader("👥 Roles to Test")
    st.caption(
        "Default: Admin only. The AI will automatically add other roles "
        "only when the story explicitly mentions them or behaviour differs per role."
    )
    selected_roles  = [
        r for r in ROLES
        if st.checkbox(r.capitalize(), value=(r == "admin"), key=f"role_{r}")
    ]
    st.divider()
    st.subheader("💬 Jira Comments")
    include_comments = st.toggle(
        "Include comments in prompt",
        value=True,
        help="Fetches Jira comments from the live API and passes them to the AI. "
             "Useful when BA/PO clarified requirements in comments. "
             "Disable to reduce token usage or if comments are noisy.",
    )

filtered = [s for s in stories if s["issuetype"] in sel_types and s["status"] in sel_statuses]

if not filtered:
    st.warning("No stories match the current filters.")
    st.stop()

# ── Mode selector ─────────────────────────────────────────────────────────────
mode = st.radio(
    "🎯 Mode",
    ["📋 Single Story", "🔷 Feature Bulk (Multi-Story)"],
    horizontal=True,
    key="gen_mode",
    help="Single Story: generate test cases for one story at a time. "
         "Feature Bulk: select multiple stories belonging to the same feature — "
         "the AI reads all of them and generates a unified, non-redundant test suite.",
)
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# FEATURE BULK MODE  (renders fully then calls st.stop() so single-story
# UI below is skipped when this mode is active)
# ══════════════════════════════════════════════════════════════════════════════
if mode == "🔷 Feature Bulk (Multi-Story)":
    st.subheader("🔷 Feature Bulk — Multi-Story Test Case Generation")
    st.caption(
        "Select all stories and bugs belonging to this feature. "
        "The AI will read each one and generate a unified, non-redundant test suite."
    )

    # ── Story multiselect ──────────────────────────────────────────────────────
    story_opts   = [f"{s['key']}  —  {s['summary'][:70]}" for s in filtered]
    key_to_story = {f"{s['key']}  —  {s['summary'][:70]}": s for s in filtered}
    bulk_labels  = st.multiselect(
        "📋 Select Stories / Bugs for this Feature",
        story_opts,
        help="Pick 2–20 Jira items. Use the sidebar filters to narrow the list first.",
    )
    bulk_stories = [key_to_story[lbl] for lbl in bulk_labels]

    if len(bulk_stories) < 2:
        st.info("Select **2 or more** stories to enable bulk generation.")
    else:
        # ── Feature prefix (auto-detect from majority of stories) ──────────────
        all_prefixes   = [detect_feature_prefix(s["summary"]) for s in bulk_stories]
        best_prefix    = Counter(all_prefixes).most_common(1)[0][0]
        feature_prefix = st.text_input(
            "🏷️ TC Prefix (auto-detected — editable)",
            value=best_prefix, key="bulk_prefix",
        )

        st.divider()
        st.markdown(f"**{len(bulk_stories)} stories selected:**")
        for _s in bulk_stories:
            _icon = "🐛" if "bug" in _s.get("issuetype", "").lower() else "📖"
            st.markdown(
                f"{_icon} `{_s['key']}` | {_s['issuetype']} | {_s['status']} — {_s['summary'][:90]}"
            )

        # ── Session state keys keyed by sorted story set ───────────────────────
        bulk_sig = "_".join(sorted(s["key"] for s in bulk_stories))
        sk_data  = f"bulk_data_{bulk_sig}"
        sk_cases = f"bulk_cases_{bulk_sig}"
        sk_sel   = f"bulk_sel_{bulk_sig}"

        st.divider()
        col_load, col_gen_b, col_clr_b = st.columns([2, 2, 1])
        with col_load:
            load_clicked = st.button(
                "📥 Load All Story Details", use_container_width=True,
                help="Fetches Summary, Description, AC, and STR from Jira for every selected story.",
            )
        with col_gen_b:
            gen_bulk = st.button(
                "🤖 Generate Feature Test Suite", type="primary", use_container_width=True,
                disabled=(sk_data not in st.session_state),
                help="Load stories first, then generate the unified test suite.",
            )
        with col_clr_b:
            if st.button("🗑️ Clear", use_container_width=True, key="bulk_clr"):
                for _k in [sk_data, sk_cases, sk_sel]:
                    st.session_state.pop(_k, None)
                st.rerun()

        # ── Load stories from Jira ─────────────────────────────────────────────
        if load_clicked:
            _loaded = {}
            _prog   = st.progress(0, text="Loading story details from Jira…")
            for _idx, _story in enumerate(bulk_stories):
                _content  = get_story_content(_story["key"], _story.get("content", ""))
                _live_cmt = fetch_jira_comments(_story["key"]) if include_comments else ""
                _comments = _live_cmt or (extract_comments(_content) if include_comments else "")
                _loaded[_story["key"]] = {
                    "key":       _story["key"],
                    "summary":   _story["summary"],
                    "issuetype": _story.get("issuetype", "Story"),
                    "desc":      extract_description(_content),
                    "ac_list":   extract_acceptance_criteria(_content),
                    "str_list":  extract_steps_to_reproduce(_content),
                    "comments":  _comments,
                }
                _prog.progress(
                    (_idx + 1) / len(bulk_stories),
                    text=f"Loaded {_story['key']} ({_idx + 1}/{len(bulk_stories)})",
                )
            st.session_state[sk_data] = _loaded
            _prog.empty()
            st.success(
                f"✅ Loaded {len(_loaded)} stories. "
                "Click **Generate Feature Test Suite** to proceed."
            )

        # ── Preview loaded stories ─────────────────────────────────────────────
        if sk_data in st.session_state:
            _loaded_stories = st.session_state[sk_data]
            st.subheader("📄 Story Details Preview")
            for _key, _data in _loaded_stories.items():
                with st.expander(f"`{_key}` — {_data['summary'][:80]}", expanded=False):
                    _m1, _m2, _m3 = st.columns(3)
                    _m1.metric("AC Items",   len(_data["ac_list"]))
                    _m2.metric("STR Steps",  len(_data["str_list"]))
                    _m3.metric("Desc Words", len(_data["desc"].split()) if _data["desc"] else 0)
                    if _data.get("comments"):
                        st.caption(f"\U0001f4ac {len(_data['comments'].split())} comment words included")
                    if _data["ac_list"]:
                        st.markdown("**Acceptance Criteria:**")
                        for _j, _ac in enumerate(_data["ac_list"], 1):
                            st.markdown(f"{_j}. {_ac}")
                    if _data["str_list"]:
                        st.markdown("**Steps to Reproduce:**")
                        for _j, _step in enumerate(_data["str_list"], 1):
                            st.markdown(f"{_j}. {_step}")
                    if _data["desc"]:
                        _preview = _data["desc"][:400] + ("…" if len(_data["desc"]) > 400 else "")
                        st.markdown(f"**Description:** {_preview}")
                    elif not _data["ac_list"] and not _data["str_list"]:
                        st.warning("No structured content found — will infer from summary only.")

        # ── Generate ───────────────────────────────────────────────────────────
        if gen_bulk and sk_data in st.session_state:
            _loaded_stories = st.session_state[sk_data]
            _stories_tuple  = tuple(
                json.dumps({
                    "key":      _d["key"],
                    "summary":  _d["summary"],
                    "desc":     (_d["desc"] or "")[:800],
                    "ac_list":  _d["ac_list"],
                    "str_list": _d["str_list"],
                }, sort_keys=True)
                for _d in _loaded_stories.values()
            )
            _all_ex: list = []
            for _d in _loaded_stories.values():
                _all_ex.extend(get_existing_test_cases(_d["key"], _d["summary"]))
            _ex_json = json.dumps(
                [{"id": t["id"], "content": t["content"][:100]} for t in _all_ex[:25]],
                sort_keys=True,
            )
            with st.spinner(
                f"Analysing {len(bulk_stories)} stories and generating unified "
                f"test suite with {OPENAI_MODEL}…"
            ):
                try:
                    _bulk_cypress = get_cypress_patterns(
                        " ".join(s["summary"] for s in bulk_stories)
                    )
                    _cases = generate_bulk_test_cases(
                        _stories_tuple, _ex_json, _bulk_cypress,
                        tuple(sorted(selected_roles)), feature_prefix,
                    )
                    st.session_state[sk_cases] = _cases
                    st.session_state[sk_sel]   = list(range(len(_cases)))
                except Exception as _e:
                    st.error(f"Generation failed: {_e}")

        # ── Display generated cases ────────────────────────────────────────────
        _bulk_generated = st.session_state.get(sk_cases, [])
        if _bulk_generated:
            st.divider()
            st.subheader(f"🎯 Generated {len(_bulk_generated)} Test Case(s) for Feature")
            st.caption(
                f"Covering {len(bulk_stories)} stories — grouped by source story. "
                "Select cases to export."
            )

            _all_selected: list = []
            _by_ref: dict = {}
            for _i, _tc in enumerate(_bulk_generated):
                _ref = _tc.get("jira_ref", "General")
                _by_ref.setdefault(_ref, []).append((_i, _tc))

            for _ref, _tc_pairs in sorted(_by_ref.items()):
                _ref_label = (
                    "🔗 `General` (cross-story / integration)"
                    if _ref == "General"
                    else f"📖 `{_ref}`"
                )
                st.markdown(f"### {_ref_label} — {len(_tc_pairs)} case(s)")
                for _i, _tc in _tc_pairs:
                    _pri  = _tc.get("priority", "Medium")
                    _typ  = _tc.get("type", "Functional")
                    _auto = _tc.get("automation_status", "Manual")
                    _checked = st.checkbox(
                        f"**[{_tc.get('tc_id', f'{feature_prefix}-{_i+1:03d}')}]** "
                        f"{PRIORITY_MAP.get(_pri, '')} {_pri}  |  "
                        f"{TYPE_MAP.get(_typ, '')} {_typ}  |  "
                        f"🤖 {_auto}  —  {_tc['title']}",
                        value=(_i in st.session_state.get(sk_sel, [])),
                        key=f"bulk_chk_{bulk_sig}_{_i}",
                    )
                    if _checked:
                        _all_selected.append(_i)
                    with st.expander("✏️ Edit Details", expanded=False):
                        _pfx = f"bulk_edit_{bulk_sig}_{_i}"
                        st.text_input("Title", value=_tc.get("title", ""), key=f"{_pfx}_title")
                        _ec1, _ec2, _ec3 = st.columns(3)
                        _ec1.selectbox("Priority", _PRIS, index=_safe_idx(_PRIS, _pri), key=f"{_pfx}_priority")
                        _ec2.selectbox("Type",     _TYPES, index=_safe_idx(_TYPES, _typ), key=f"{_pfx}_type")
                        _ec3.selectbox("Automation", _AUTOS, index=_safe_idx(_AUTOS, _auto), key=f"{_pfx}_auto")
                        _el, _er = st.columns(2)
                        with _el:
                            st.caption(f"**TC ID:** `{_tc.get('tc_id', '')}` | **Roles:** {', '.join(_tc.get('roles_covered', []))}")
                            st.text_input("Story Ref (Jira ID)", value=_tc.get("jira_ref", "General"), key=f"{_pfx}_jira_ref")
                            st.text_input("Test Data", value=_tc.get("test_data", "N/A"), key=f"{_pfx}_test_data")
                        with _er:
                            st.text_area("Preconditions", value=_tc.get("preconditions", ""), key=f"{_pfx}_prec", height=80)
                        st.text_area("Steps", value=_tc.get("steps", "").replace(chr(92)+"n", chr(10)), key=f"{_pfx}_steps", height=150)
                        st.text_area("Expected Result", value=_tc.get("expected_result", ""), key=f"{_pfx}_expected", height=80)

            st.session_state[sk_sel] = _all_selected

            st.divider()
            st.subheader("📤 Export to TestRail")
            if not TESTRAIL_URL:
                st.warning("TestRail URL not configured in `rag/.env`. Set TESTRAIL_URL to enable export.")
            else:
                _suites = get_testrail_suites()
                if _suites:
                    _suite_map   = {f"[{_s['id']}] {_s['name']}": _s for _s in _suites}
                    _suite_label = st.selectbox("📁 TestRail Suite", list(_suite_map.keys()), key="bulk_suite_sel")
                    _suite_id    = _suite_map[_suite_label]["id"]
                    _sections    = get_testrail_sections(_suite_id)
                    if _sections:
                        _sec_map   = {f"[{_s['id']}] {_s['name']}": _s["id"] for _s in _sections}
                        _sec_label = st.selectbox("📂 Section within Suite", list(_sec_map.keys()), key="bulk_sec_sel")
                        _sec_id    = _sec_map[_sec_label]
                    else:
                        st.caption("No sections found — enter section ID manually.")
                        _sec_id = st.number_input("Section ID", min_value=1, value=1, step=1, key="bulk_sec_manual")
                else:
                    st.caption("Could not fetch suites — enter IDs manually.")
                    _suite_id = st.number_input("Suite ID",   min_value=1, value=1, step=1, key="bulk_suite_id")
                    _sec_id   = st.number_input("Section ID", min_value=1, value=1, step=1, key="bulk_sec_id")

                _n_sel = len(_all_selected)
                if st.button(
                    f"📤 Export {_n_sel} Case(s) to TestRail",
                    disabled=(_n_sel == 0),
                    type="primary",
                    key="bulk_export_btn",
                ):
                    _to_export = [_get_edited(_bulk_generated[_i], f"bulk_edit_{bulk_sig}_{_i}") for _i in _all_selected]
                    with st.spinner(f"Exporting {len(_to_export)} test case(s)…"):
                        _results = export_to_testrail(_to_export, int(_suite_id), int(_sec_id))
                    _created = sum(1 for _r in _results if "✅" in _r["status"])
                    _failed  = len(_results) - _created
                    if _created:
                        st.success(f"✅ {_created} test case(s) created in TestRail.")
                    if _failed:
                        st.error(f"❌ {_failed} test case(s) failed to export.")
                    for _r in _results:
                        _link = (
                            f" → [C{_r['id']}]({TESTRAIL_URL}/index.php?/cases/view/{_r['id']})"
                            if _r["id"] else ""
                        )
                        st.markdown(f"{_r['status']} **{_r['title']}**{_link}")

        elif sk_data in st.session_state:
            st.info("Stories loaded. Click **Generate Feature Test Suite** to generate test cases.")

    st.stop()  # ← Prevents single-story UI below from rendering in Bulk mode

# ══════════════════════════════════════════════════════════════════════════════
# SINGLE STORY MODE  (existing code — unchanged)
# ══════════════════════════════════════════════════════════════════════════════

# ── Story selector ────────────────────────────────────────────────────────────
story_options  = {f"{s['key']}  —  {s['summary'][:70]}": s for s in filtered}
selected_label = st.selectbox("📋 Select Jira Story", list(story_options.keys()))
selected       = story_options[selected_label]
feature_prefix = detect_feature_prefix(selected["summary"])

st.divider()

# ── Story header ──────────────────────────────────────────────────────────────
cols = st.columns(4)
cols[0].metric("Story Key",      selected["key"])
cols[1].metric("Issue Type",     selected["issuetype"])
cols[2].metric("Status",         selected["status"])
cols[3].metric("TC Prefix",      feature_prefix)
st.markdown(f"**📝 Summary:** {selected['summary']}")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📄 Story Details & AC", "✅ Existing Test Cases", "🤖 Generate & Export"])

# ── Tab 1: Story Details ──────────────────────────────────────────────────────
with tab1:
    with st.spinner("Fetching story details…"):
        content = get_story_content(selected["key"], selected.get("content", ""))
    if content:
        with st.expander("📄 Full Story Content", expanded=True):
            st.text(content[:2500])
        ac_list  = extract_acceptance_criteria(content)
        str_list = extract_steps_to_reproduce(content)
        desc     = extract_description(content)
        if desc:
            with st.expander(f"📝 Description ({len(desc.split())} words)", expanded=False):
                st.markdown(desc)
        else:
            st.caption("ℹ️ No Description found in this story.")
        if ac_list:
            st.divider()
            st.markdown(f"**✅ Acceptance Criteria ({len(ac_list)} items):**")
            for i, item in enumerate(ac_list, 1):
                st.markdown(f"{i}. {item}")
        else:
            st.info(
                "No structured Acceptance Criteria found — the generator will infer test cases "
                + ("from the Description above." if desc else "from the story summary.")
            )
        if str_list:
            st.divider()
            st.markdown(f"**🔄 Steps to Reproduce ({len(str_list)} steps):**")
            for i, step in enumerate(str_list, 1):
                st.markdown(f"{i}. {step}")
        # ── Comments preview ──
        if include_comments:
            _live_comments = fetch_jira_comments(selected["key"])
            _comments_text = _live_comments or extract_comments(content)
            if _comments_text:
                st.divider()
                with st.expander(
                    f"💬 Comments ({len(_comments_text.split())} words — included in prompt)",
                    expanded=False,
                ):
                    st.markdown(_comments_text[:1500])
            else:
                st.caption("ℹ️ No comments found for this story.")
    else:
        st.warning("Could not retrieve story content from Jira API or RAG.")

# ── Tab 2: Existing Test Cases ────────────────────────────────────────────────
with tab2:
    existing_tcs = get_existing_test_cases(selected["key"], selected["summary"])
    if existing_tcs:
        st.success(f"Found **{len(existing_tcs)}** existing TestRail test case(s) for this story.")
        st.caption("Step details fetched live from TestRail API — always up to date.")
        for tc in existing_tcs:
            import re as _re
            _raw = tc["content"]
            _title_match = _re.search(r'Title:\s*(.+)', _raw)
            _suite_match = _re.search(r'Suite:\s*(.+)', _raw)
            _pri_match   = _re.search(r'Priority:\s*(.+)', _raw)
            _label = _title_match.group(1).strip()[:80] if _title_match else tc['id']

            with st.expander(f"🧪 {tc['id']} — {_label}"):
                if _suite_match:
                    st.markdown(f"**Suite/Section:** {_suite_match.group(1).strip()}")
                if _pri_match:
                    st.markdown(f"**Priority:** {_pri_match.group(1).strip()}")

                # Always try live API for steps — FAISS index can be stale
                live = fetch_testrail_case_live(tc['id'])
                if live:
                    st.markdown(f"**Title:** {live['title']}")
                    st.markdown("**Preconditions:**")
                    st.code(live["preconditions"] or "*(none)*", language=None)
                    st.markdown("**Steps:**")
                    st.code(live["steps"] or "*(empty in TestRail)*", language=None)
                    st.markdown("**Expected Result:**")
                    st.code(live["expected_result"] or "*(empty in TestRail)*", language=None)
                else:
                    # Fallback to index content if API unavailable
                    _clean = _re.sub(r'<br\s*/?>', '\n', _raw)
                    _clean = _re.sub(r'<[^>]+>', '', _clean)
                    _clean = _re.sub(r'\n{3,}', '\n\n', _clean).strip()
                    st.code(_clean, language=None)
                    st.caption("⚠️ Live TestRail API unavailable — showing cached index data.")
    else:
        st.info("No existing TestRail test cases found for this story in the RAG index.")

# ── Tab 3: Generate & Export ──────────────────────────────────────────────────
with tab3:
    state_cases = f"gen_cases_{selected['key']}"
    state_sel   = f"sel_idx_{selected['key']}"

    if state_cases not in st.session_state:
        st.session_state[state_cases] = []
        st.session_state[state_sel]   = []

    col_gen, col_clr = st.columns([3, 1])
    with col_gen:
        gen_clicked = st.button("🤖 Generate Test Cases", type="primary", use_container_width=True)
    with col_clr:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state[state_cases] = []
            st.session_state[state_sel]   = []

    if gen_clicked:
        content  = get_story_content(selected["key"], selected.get("content", ""))
        ac_list  = extract_acceptance_criteria(content)
        str_list = extract_steps_to_reproduce(content)
        desc     = extract_description(content)
        _live_cmt = fetch_jira_comments(selected["key"]) if include_comments else ""
        comments  = _live_cmt or (extract_comments(content) if include_comments else "")
        ex_tcs      = get_existing_test_cases(selected["key"], selected["summary"])
        cypress_ctx = get_cypress_patterns(selected["summary"])
        with st.spinner(f"Generating structured test cases with {OPENAI_MODEL}…"):
            try:
                cases = generate_test_cases(
                    selected["key"], selected["summary"],
                    desc,
                    tuple(ac_list), tuple(str_list),
                    comments,
                    cypress_ctx,
                    tuple(json.dumps(t, sort_keys=True) for t in ex_tcs),
                    tuple(sorted(selected_roles)), feature_prefix,
                )
                # P3-fix: flag near-duplicate titles within this generation run
                # so the user can deselect before export (token overlap ≥ 70%)
                def _title_tokens(t: str) -> set:
                    return {w.lower().strip(".,;:!?()[]") for w in t.split() if len(w) > 2}

                dup_indices: set = set()
                for a in range(len(cases)):
                    if a in dup_indices:
                        continue
                    for b in range(a + 1, len(cases)):
                        if b in dup_indices:
                            continue
                        ta = _title_tokens(cases[a].get("title", ""))
                        tb = _title_tokens(cases[b].get("title", ""))
                        if ta and tb:
                            overlap = len(ta & tb) / max(len(ta), len(tb))
                            if overlap >= 0.70:
                                dup_indices.add(b)
                                cases[b]["_duplicate_of"] = cases[a].get("tc_id", str(a))

                st.session_state[state_cases] = cases
                st.session_state[state_sel]   = [i for i in range(len(cases)) if i not in dup_indices]
                if dup_indices:
                    st.warning(
                        f"⚠️ {len(dup_indices)} near-duplicate case(s) detected and pre-deselected. "
                        "Review them below before exporting.",
                        icon="⚠️",
                    )
            except Exception as e:
                st.error(f"Generation failed: {e}")

    generated = st.session_state[state_cases]

    if generated:
        st.subheader(f"Generated {len(generated)} Test Case(s)")
        st.caption("Select cases to review and export to TestRail:")

        selected_indices = []
        for i, tc in enumerate(generated):
            pri  = tc.get("priority", "Medium")
            typ  = tc.get("type", "Functional")
            auto = tc.get("automation_status", "Manual")

            _dup_tag = " ⚠️ NEAR-DUPLICATE" if tc.get("_duplicate_of") else ""
            checked = st.checkbox(
                f"**[{tc.get('tc_id', f'{feature_prefix}-{i+1:03d}')}]** "
                f"{PRIORITY_MAP.get(pri, '')} {pri}  |  "
                f"{TYPE_MAP.get(typ, '')} {typ}  |  "
                f"🤖 {auto}  —  {tc['title']}{_dup_tag}",
                value=(i in st.session_state[state_sel]),
                key=f"chk_{selected['key']}_{i}",
            )
            if checked:
                selected_indices.append(i)

            with st.expander("✏️ Edit Details", expanded=False):
                _pfx = f"edit_{selected['key']}_{i}"
                st.text_input("Title", value=tc.get("title", ""), key=f"{_pfx}_title")
                _c1, _c2, _c3 = st.columns(3)
                _c1.selectbox("Priority",   _PRIS,  index=_safe_idx(_PRIS,  pri),  key=f"{_pfx}_priority")
                _c2.selectbox("Type",       _TYPES, index=_safe_idx(_TYPES, typ),  key=f"{_pfx}_type")
                _c3.selectbox("Automation", _AUTOS, index=_safe_idx(_AUTOS, auto), key=f"{_pfx}_auto")
                _l, _r = st.columns(2)
                with _l:
                    st.caption(f"**TC ID:** `{tc.get('tc_id', '')}` | **Roles:** {', '.join(tc.get('roles_covered', []))}")
                    st.text_input("Story Ref (Jira ID)", value=tc.get("jira_ref", selected["key"]), key=f"{_pfx}_jira_ref")
                    st.text_input("Test Data", value=tc.get("test_data", "N/A"), key=f"{_pfx}_test_data")
                with _r:
                    st.text_area("Preconditions", value=tc.get("preconditions", ""), key=f"{_pfx}_prec", height=80)
                st.text_area("Steps", value=tc.get("steps", "").replace(chr(92)+"n", chr(10)), key=f"{_pfx}_steps", height=150)
                st.text_area("Expected Result", value=tc.get("expected_result", ""), key=f"{_pfx}_expected", height=80)

        st.session_state[state_sel] = selected_indices

        st.divider()
        st.subheader("📤 Export to TestRail")

        if not TESTRAIL_URL:
            st.warning("TestRail URL not configured in `rag/.env`. Set TESTRAIL_URL to enable export.")
        else:
            suites = get_testrail_suites()
            if suites:
                suite_map    = {f"[{s['id']}] {s['name']}": s for s in suites}
                suite_label  = st.selectbox("📁 TestRail Suite", list(suite_map.keys()))
                chosen_suite = suite_map[suite_label]
                suite_id     = chosen_suite["id"]

                sections = get_testrail_sections(suite_id)
                if sections:
                    section_map   = {f"[{s['id']}] {s['name']}": s["id"] for s in sections}
                    section_label = st.selectbox("📂 Section within Suite", list(section_map.keys()))
                    section_id    = section_map[section_label]
                else:
                    st.caption("No sections found in this suite — enter section ID manually.")
                    section_id = st.number_input("Section ID", min_value=1, value=1, step=1)
            else:
                st.caption("Could not fetch suites — enter suite and section IDs manually.")
                suite_id   = st.number_input("Suite ID",   min_value=1, value=1, step=1)
                section_id = st.number_input("Section ID", min_value=1, value=1, step=1)

            n_selected = len(selected_indices)
            if st.button(
                f"📤 Export {n_selected} Case(s) to TestRail",
                disabled=(n_selected == 0),
                type="primary",
            ):
                cases_to_export = [_get_edited(generated[i], f"edit_{selected['key']}_{i}") for i in selected_indices]
                with st.spinner(f"Exporting {len(cases_to_export)} test case(s)…"):
                    results = export_to_testrail(cases_to_export, int(suite_id), int(section_id))

                created = sum(1 for r in results if "✅" in r["status"])
                failed  = len(results) - created
                if created:
                    st.success(f"✅ {created} test case(s) created in TestRail.")
                if failed:
                    st.error(f"❌ {failed} test case(s) failed to export.")
                for r in results:
                    link = (
                        f" → [C{r['id']}]({TESTRAIL_URL}/index.php?/cases/view/{r['id']})"
                        if r["id"] else ""
                    )
                    st.markdown(f"{r['status']} **{r['title']}**{link}")
    else:
        st.info("Click **Generate Test Cases** to analyse coverage gaps and generate structured test cases for this story.")
