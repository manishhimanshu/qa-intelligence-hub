"""
Gap Analysis
Structured requirement gap analysis for any Jira story, following
gap-analysis.instructions.md exactly:
  1. Requirement Summary
  2. Identified Gaps (Functional / Role & Permission / Data Validation /
     State & Edge Case / Integration / Non-Functional)
  3. Questions for the Product Owner
  4. Test Scope Estimate
  5. Automation Recommendation
"""

import os
import sys
import re
import json
import requests
from datetime import datetime
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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
JIRA_URL       = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_USER      = os.getenv("JIRA_USER", "")
JIRA_TOKEN     = os.getenv("JIRA_TOKEN", "")

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="Gap Analysis", page_icon="🔍", layout="wide")


# ── Helpers ───────────────────────────────────────────────────────────────────
def rag_query(query: str, top_k: int = 20) -> list:
    from get_relevant_docs import get_relevant_docs
    return get_relevant_docs(query, top_k=top_k)


# Shared singleton loader — ONE @st.cache_resource across all pages prevents triple FAISS load
sys.path.insert(0, os.path.join(_DIR, ".."))
from shared_vectorstore import load_vectorstore as _load_vectorstore


@st.cache_data(show_spinner="Loading Jira stories…")
def load_stories() -> list:
    """Iterate ALL documents in the FAISS docstore — no top_k cap."""
    vs = _load_vectorstore()
    if vs is None:
        st.error("RAG index not found. Run `python ingest_all.py` first.")
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
        content = langchain_doc.page_content
        summary = key
        for line in content.splitlines():
            if re.match(r'summary:', line, re.IGNORECASE):
                summary = line.split(":", 1)[-1].strip()
                break
        stories.append({"key": key, "summary": summary, "content": content})

    return sorted(stories, key=lambda x: (
        x["key"].split("-")[0],
        int(re.search(r'\d+$', x["key"]).group(0)) if re.search(r'\d+$', x["key"]) else 0
    ))


def _adf_to_markdown(node) -> str:
    """Convert Atlassian Document Format (ADF) JSON to markdown, preserving structure."""
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


@st.cache_data(show_spinner="Fetching story from Jira…")
def get_story_content(story_key: str, fallback: str) -> str:
    """Fetch full story from Jira API including Description, AC, and Steps to Reproduce."""
    if JIRA_URL and JIRA_USER and JIRA_TOKEN:
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
            if r.status_code == 200:
                fields = r.json().get("fields", {})

                def _custom(field_id: str) -> str:
                    if not field_id:
                        return ""
                    val = fields.get(field_id)
                    if not val:
                        return ""
                    if isinstance(val, dict):
                        return _adf_to_markdown(val)
                    if isinstance(val, str):
                        return val
                    return ""

                summary  = fields.get("summary", "")
                desc_md  = _adf_to_markdown(fields.get("description") or {})
                ac_md    = _custom(ac_field_id)
                str_md   = _custom(str_field_id)

                parts = [f"Summary: {summary}"]
                if desc_md.strip():
                    parts.append(f"\n## Description\n{desc_md}")
                if ac_md.strip():
                    parts.append(f"\n## Acceptance Criteria\n{ac_md}")
                if str_md.strip():
                    parts.append(f"\n## Steps to Reproduce\n{str_md}")
                return "\n".join(parts)
        except Exception:
            pass
    return fallback


@st.cache_data(show_spinner=False, ttl=3600)
def run_gap_analysis(story_key: str, summary: str, content: str) -> dict:
    """Call GPT to produce the 5-section gap analysis from instructions."""
    prompt = f"""You are a QA Architect performing a structured Requirement Gap Analysis for a Kapost Jira story.

Platform context:
- B2B content marketing SaaS
- 4 user roles: admin, editor, contributor, consumer
- Core features: Content Catalog, Initiatives (Campaigns), Ideas, Gallery, Members,
  Settings, Calendar, Global Search, Notifications, Dashboard/NAPA

Story: {story_key} — {summary}

Full Story Content:
{content}

Produce a COMPLETE gap analysis. Return ONLY valid JSON — no markdown fences:
{{
  "requirement_summary": [
    "Bullet: what is explicitly stated (3-5 bullets, factual only)"
  ],
  "functional_gaps": [
    "Behaviours implied but not specified",
    "What happens on failure (network error, server 500)",
    "What happens on concurrent edits",
    "Is there a confirmation dialog for destructive actions"
  ],
  "role_permission_gaps": [
    "Which of the 4 roles is this defined for",
    "Are role restrictions explicitly stated or assumed",
    "Does each role have a defined expected outcome"
  ],
  "data_validation_gaps": [
    "Input field constraints (max length, allowed formats, required vs optional)",
    "Error messages for invalid inputs — are they specified",
    "Uniqueness constraints"
  ],
  "state_edge_case_gaps": [
    "Empty state: what does the user see with no data",
    "Dependency deletion: what if a linked entity is deleted",
    "Mid-workflow reload behavior",
    "Unsaved changes warning"
  ],
  "integration_gaps": [
    "Calendar view impact",
    "Content Catalog count / filter impact",
    "Notification triggers",
    "Initiative ↔ Content relationship",
    "Dashboard / NAPA metrics impact",
    "Global Search results impact"
  ],
  "non_functional_gaps": [
    "Performance expectations (load time)",
    "Mobile / responsive layout",
    "Audit log / activity feed entry",
    "Accessibility (WCAG) requirement"
  ],
  "po_questions": [
    "Q1: What should happen when [scenario from the gaps above]?",
    "Q2: ...",
    "Q3: ..."
  ],
  "test_scope": {{
    "happy_path":          3,
    "negative_validation": 4,
    "role_based":          5,
    "edge_integration":    3,
    "total":               15,
    "split_recommended":   false,
    "split_reason":        ""
  }},
  "automation": {{
    "automate_now":   ["Stable, high-value, repeatable scenario e.g. happy path creation"],
    "automate_later": ["Valid but lower priority or complex UI scenario"],
    "manual_only":    ["Exploratory, one-off, or unstable scenario"]
  }}
}}

Be specific and reference Kapost domain concepts.
Flag anything not covered in the requirement as a gap — do not assume it is handled."""

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


def build_markdown_report(story_key: str, summary: str, gap: dict) -> str:
    md  = f"# Gap Analysis Report: {story_key} — {summary}\n\n"
    md += f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
    md += "---\n\n"

    md += "## 1. Requirement Summary\n\n"
    for b in gap.get("requirement_summary", []):
        md += f"- {b}\n"

    md += "\n## 2. Identified Gaps\n\n"
    for section_title, key in [
        ("### Functional Gaps",          "functional_gaps"),
        ("### Role & Permission Gaps",   "role_permission_gaps"),
        ("### Data Validation Gaps",     "data_validation_gaps"),
        ("### State & Edge Case Gaps",   "state_edge_case_gaps"),
        ("### Integration Gaps",         "integration_gaps"),
        ("### Non-Functional Gaps",      "non_functional_gaps"),
    ]:
        items = gap.get(key, [])
        md += f"\n{section_title}\n\n"
        if items:
            for item in items:
                md += f"- {item}\n"
        else:
            md += "*No gaps identified.*\n"

    md += "\n## 3. Questions for the Product Owner\n\n"
    for q in gap.get("po_questions", []):
        md += f"- {q}\n"

    scope = gap.get("test_scope", {})
    md += "\n## 4. Test Scope Estimate\n\n"
    md += f"- Happy Path cases:           {scope.get('happy_path', 0)}\n"
    md += f"- Negative / Validation cases: {scope.get('negative_validation', 0)}\n"
    md += f"- Role-Based cases:            {scope.get('role_based', 0)}\n"
    md += f"- Edge / Integration cases:    {scope.get('edge_integration', 0)}\n"
    md += f"\n**Total: {scope.get('total', 0)} test cases**\n"
    if scope.get("split_recommended"):
        md += f"\n> ⚠️ **Split recommended:** {scope.get('split_reason', '')}\n"

    auto = gap.get("automation", {})
    md += "\n## 5. Automation Recommendation\n\n"
    md += "**Automate Now** (stable, high-value, repeatable):\n"
    for item in auto.get("automate_now", []):
        md += f"- {item}\n"
    md += "\n**Automate Later** (valid but lower priority or UI-heavy):\n"
    for item in auto.get("automate_later", []):
        md += f"- {item}\n"
    md += "\n**Manual Only** (exploratory, one-off, or too unstable):\n"
    for item in auto.get("manual_only", []):
        md += f"- {item}\n"

    return md


# ── Epic / multi-story helpers ───────────────────────────────────────────────

@st.cache_data(show_spinner="Fetching epic children from Jira…", ttl=600)
def fetch_epic_children(epic_key: str) -> list:
    """Return all child issues of an epic via Jira REST API v3 (search/jql endpoint).

    Uses POST /rest/api/3/search/jql (the current non-deprecated endpoint).
    Supports both next-gen (parent =) and classic ("Epic Link" =) project styles.
    """
    if not (JIRA_URL and JIRA_USER and JIRA_TOKEN):
        return []
    try:
        jql = f'(parent = "{epic_key}" OR "Epic Link" = "{epic_key}") ORDER BY created ASC'
        url = f"{JIRA_URL}/rest/api/3/search/jql"
        all_issues: list = []
        next_page_token: str | None = None

        while True:
            body: dict = {
                "jql":      jql,
                "maxResults": 100,
                "fields":   ["summary", "status", "issuetype"],
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            r = requests.post(
                url,
                auth=(JIRA_USER, JIRA_TOKEN),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=body,
                timeout=15,
            )
            if r.status_code != 200:
                st.error(f"Jira API error {r.status_code}: {r.text[:300]}")
                break

            data   = r.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)

            # New API uses cursor-based pagination via nextPageToken
            next_page_token = data.get("nextPageToken")
            if not next_page_token or len(issues) == 0:
                break

        # Deduplicate by key (OR query can return duplicates)
        seen, unique = set(), []
        for issue in all_issues:
            if issue["key"] not in seen:
                seen.add(issue["key"])
                unique.append({
                    "key":       issue["key"],
                    "summary":   issue["fields"].get("summary", issue["key"]),
                    "issuetype": (issue["fields"].get("issuetype") or {}).get("name", "Story"),
                    "status":    (issue["fields"].get("status") or {}).get("name", "Unknown"),
                })
        return unique
    except Exception as e:
        st.error(f"Failed to fetch epic children: {e}")
        return []


@st.cache_data(show_spinner=False, ttl=3600)
def run_multi_gap_analysis(stories_data: tuple) -> dict:
    """Consolidated gap analysis across multiple stories treated as one feature.

    stories_data: tuple of (key, summary, content) tuples — hashable for caching.
    """
    stories_list  = [{"key": k, "summary": s, "content": c} for k, s, c in stories_data]
    stories_block = ""
    for i, story in enumerate(stories_list, 1):
        stories_block += f"\n--- Story {i}: {story['key']} — {story['summary']} ---\n"
        stories_block += story["content"] + "\n"

    n = len(stories_list)
    prompt = f"""You are a QA Architect performing a consolidated Requirement Gap Analysis for a Kapost feature consisting of {n} Jira story/stories.

Platform context:
- B2B content marketing SaaS
- 4 user roles: admin, editor, contributor, consumer
- Core features: Content Catalog, Initiatives (Campaigns), Ideas, Gallery, Members,
  Settings, Calendar, Global Search, Notifications, Dashboard/NAPA

Stories being analysed as a complete feature:
{stories_block}

Treat these stories as a SINGLE FEATURE. Identify:
1. Gaps within individual stories (unfilled requirements)
2. Cross-story gaps (e.g. one story defines creation but no story handles deletion)
3. Missing role coverage across the full feature
4. Integration gaps between stories
5. Combined test scope for the entire feature

Return ONLY valid JSON — no markdown fences:
{{
  "requirement_summary": [
    "Bullet summarising what the full feature does across all {n} stories (3-7 bullets, factual only)"
  ],
  "functional_gaps": ["..."],
  "role_permission_gaps": ["..."],
  "data_validation_gaps": ["..."],
  "state_edge_case_gaps": ["..."],
  "integration_gaps": ["..."],
  "non_functional_gaps": ["..."],
  "cross_story_gaps": [
    "Gap spanning multiple stories — e.g. STUD-X defines creation but no story covers deletion"
  ],
  "po_questions": ["Q1: What should happen when …?", "Q2: …"],
  "test_scope": {{
    "happy_path": 0,
    "negative_validation": 0,
    "role_based": 0,
    "edge_integration": 0,
    "total": 0,
    "split_recommended": false,
    "split_reason": ""
  }},
  "automation": {{
    "automate_now":   ["..."],
    "automate_later": ["..."],
    "manual_only":    ["..."]
  }}
}}

Be specific. Reference Jira story keys by name (e.g. "STUD-123 does not define…"). Flag anything not covered across all stories as a gap."""

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


def build_multi_markdown_report(story_keys: list, epic_key: str, gap: dict) -> str:
    title = f"Epic {epic_key}" if epic_key else f"{len(story_keys)} Stories"
    md  = f"# Consolidated Gap Analysis: {title}\n\n"
    md += f"**Stories covered:** {', '.join(story_keys)}\n\n"
    md += f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
    md += "---\n\n"

    md += "## 1. Requirement Summary\n\n"
    for b in gap.get("requirement_summary", []):
        md += f"- {b}\n"

    md += "\n## 2. Identified Gaps\n\n"
    for section_title, key in [
        ("### Functional Gaps",        "functional_gaps"),
        ("### Role & Permission Gaps", "role_permission_gaps"),
        ("### Data Validation Gaps",   "data_validation_gaps"),
        ("### State & Edge Case Gaps", "state_edge_case_gaps"),
        ("### Integration Gaps",       "integration_gaps"),
        ("### Non-Functional Gaps",    "non_functional_gaps"),
        ("### Cross-Story Gaps",       "cross_story_gaps"),
    ]:
        items = gap.get(key, [])
        md += f"\n{section_title}\n\n"
        for item in items:
            md += f"- {item}\n"
        if not items:
            md += "*No gaps identified.*\n"

    md += "\n## 3. Questions for the Product Owner\n\n"
    for q in gap.get("po_questions", []):
        md += f"- {q}\n"

    scope = gap.get("test_scope", {})
    md += "\n## 4. Test Scope Estimate\n\n"
    md += f"- Happy Path cases:            {scope.get('happy_path', 0)}\n"
    md += f"- Negative / Validation cases: {scope.get('negative_validation', 0)}\n"
    md += f"- Role-Based cases:            {scope.get('role_based', 0)}\n"
    md += f"- Edge / Integration cases:    {scope.get('edge_integration', 0)}\n"
    md += f"\n**Total: {scope.get('total', 0)} test cases**\n"
    if scope.get("split_recommended"):
        md += f"\n> ⚠️ **Split recommended:** {scope.get('split_reason', '')}\n"

    auto = gap.get("automation", {})
    md += "\n## 5. Automation Recommendation\n\n"
    md += "**Automate Now:**\n"
    for item in auto.get("automate_now", []):
        md += f"- {item}\n"
    md += "\n**Automate Later:**\n"
    for item in auto.get("automate_later", []):
        md += f"- {item}\n"
    md += "\n**Manual Only:**\n"
    for item in auto.get("manual_only", []):
        md += f"- {item}\n"

    return md


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("🔍 Gap Analysis")
st.caption("Structured requirement gap analysis — single story, multiple stories, or full epic")

stories = load_stories()
if not stories:
    st.error("No Jira stories found in RAG. Run `python rag/ingest_all.py`.")
    st.stop()

story_map = {s["key"]: s for s in stories}

# ── Mode selector ─────────────────────────────────────────────────────────────
mode = st.radio(
    "Analysis Mode",
    ["🔹 Single Story", "🔷 Multiple Stories", "🔶 By Epic"],
    horizontal=True,
    label_visibility="collapsed",
)

selected_stories: list = []   # list of {key, summary, content}
epic_key_used:    str  = ""

# ── Single Story ──────────────────────────────────────────────────────────────
if mode == "🔹 Single Story":
    story_options  = {f"{s['key']}  —  {s['summary'][:70]}": s for s in stories}
    selected_label = st.selectbox("📋 Select Jira Story", list(story_options.keys()))
    selected_stories = [story_options[selected_label]]

# ── Multiple Stories ──────────────────────────────────────────────────────────
elif mode == "🔷 Multiple Stories":
    st.caption("Select 2–20 stories to analyse as a combined feature. Use the search box to filter by key or keyword.")
    story_options   = {f"{s['key']}  —  {s['summary'][:70]}": s for s in stories}
    selected_labels = st.multiselect(
        "📋 Select Stories",
        list(story_options.keys()),
        max_selections=20,
        placeholder="Type a story key or keyword…",
    )
    selected_stories = [story_options[lbl] for lbl in selected_labels]
    if selected_labels:
        st.info(f"Selected **{len(selected_labels)}** stor{'y' if len(selected_labels) == 1 else 'ies'}")

# ── By Epic ───────────────────────────────────────────────────────────────────
elif mode == "🔶 By Epic":
    st.caption("Enter an Epic key to fetch all child stories from Jira, then run a consolidated gap analysis.")
    col_epic, col_fetch = st.columns([3, 1])
    with col_epic:
        epic_key_input = st.text_input("🏷️ Epic Key", placeholder="e.g. STUD-123").strip().upper()
    with col_fetch:
        st.write("")
        fetch_clicked = st.button("🔍 Fetch Stories", use_container_width=True)

    if fetch_clicked and epic_key_input:
        with st.spinner(f"Fetching stories under {epic_key_input}…"):
            children = fetch_epic_children(epic_key_input)
        if children:
            st.session_state["epic_children"] = children
            st.session_state["epic_key_used"]  = epic_key_input
            st.success(f"Found **{len(children)}** stories under **{epic_key_input}**")
        else:
            st.warning("No stories found. Check the epic key and ensure Jira credentials are configured.")
    elif fetch_clicked and not epic_key_input:
        st.warning("Please enter an Epic key first.")

    children      = st.session_state.get("epic_children", [])
    epic_key_used = st.session_state.get("epic_key_used", "")

    if children:
        st.caption(f"**{len(children)} stories** found under **{epic_key_used}** — deselect any to exclude:")
        child_options   = {f"{c['key']}  —  {c['summary'][:70]}": c for c in children}
        selected_labels = st.multiselect(
            "Stories to include",
            list(child_options.keys()),
            default=list(child_options.keys()),
            label_visibility="collapsed",
        )
        selected_stories = []
        for lbl in selected_labels:
            child     = child_options[lbl]
            rag_story = story_map.get(child["key"], child)
            selected_stories.append({
                "key":     child["key"],
                "summary": child["summary"],
                "content": rag_story.get("content", f"Summary: {child['summary']}"),
            })

# ── Run / Clear buttons ────────────────────────────────────────────────────────
st.divider()
is_multi = (mode != "🔹 Single Story") and len(selected_stories) > 1
n        = len(selected_stories)

if n == 0:
    st.info("Select at least one story above to run gap analysis.")
    st.stop()

state_key = "gap_multi_" + "_".join(sorted(s["key"] for s in selected_stories))

col_run, col_clr = st.columns([4, 1])
with col_run:
    btn_label   = f"🔍 Run Gap Analysis on {n} Stor{'y' if n == 1 else 'ies'}"
    run_clicked = st.button(btn_label, type="primary", use_container_width=True)
with col_clr:
    if st.button("🗑️ Clear", use_container_width=True):
        st.session_state.pop(state_key, None)
        st.session_state.pop("epic_children", None)
        st.rerun()

if run_clicked:
    if is_multi:
        enriched: list = []
        with st.spinner(f"Fetching content for {n} stories…"):
            for s in selected_stories:
                live = get_story_content(s["key"], s.get("content", ""))
                enriched.append((s["key"], s["summary"], live))
        with st.spinner(f"Running consolidated gap analysis with {OPENAI_MODEL}…"):
            try:
                result = run_multi_gap_analysis(tuple(enriched))
                result["_mode"]       = "multi"
                result["_story_keys"] = [s["key"] for s in selected_stories]
                result["_summaries"]  = [s["summary"] for s in selected_stories]
                result["_epic_key"]   = epic_key_used
                st.session_state[state_key] = result
            except Exception as e:
                st.error(f"Gap analysis failed: {e}")
    else:
        s       = selected_stories[0]
        content = get_story_content(s["key"], s.get("content", ""))
        with st.spinner(f"Analysing requirements with {OPENAI_MODEL}…"):
            try:
                result = run_gap_analysis(s["key"], s["summary"], content)
                result["_mode"]       = "single"
                result["_story_keys"] = [s["key"]]
                result["_summaries"]  = [s["summary"]]
                result["_epic_key"]   = ""
                st.session_state[state_key] = result
            except Exception as e:
                st.error(f"Gap analysis failed: {e}")

gap = st.session_state.get(state_key)

if not gap:
    st.info("Configure your selection above and click **Run Gap Analysis** to begin.")
    st.stop()

analysis_mode = gap.get("_mode", "single")
story_keys    = gap.get("_story_keys", [])
summaries     = gap.get("_summaries", [])
result_epic   = gap.get("_epic_key", "")

st.divider()

# ── Consolidated results header (multi only) ──────────────────────────────────
if analysis_mode == "multi":
    title_suffix = f"Epic **{result_epic}**" if result_epic else f"**{len(story_keys)} Stories**"
    st.subheader(f"📊 Consolidated Gap Analysis — {title_suffix}")
    st.caption("Stories covered: " + " · ".join(story_keys))
    st.divider()

# ── Section 1: Requirement Summary ───────────────────────────────────────────
st.subheader("1️⃣ Requirement Summary")
for bullet in gap.get("requirement_summary", []):
    st.markdown(f"- {bullet}")

# ── Section 2: Identified Gaps ────────────────────────────────────────────────
st.subheader("2️⃣ Identified Gaps")
gap_sections = [
    ("⚙️ Functional Gaps",         "functional_gaps"),
    ("🔐 Role & Permission Gaps",  "role_permission_gaps"),
    ("📋 Data Validation Gaps",    "data_validation_gaps"),
    ("🔄 State & Edge Case Gaps",  "state_edge_case_gaps"),
    ("🔗 Integration Gaps",        "integration_gaps"),
    ("⚡ Non-Functional Gaps",     "non_functional_gaps"),
]
if analysis_mode == "multi":
    gap_sections.append(("🔀 Cross-Story Gaps", "cross_story_gaps"))

for title, key in gap_sections:
    items = gap.get(key, [])
    label = f"{title} ({len(items)} item(s))" if items else f"{title} — ✅ None identified"
    with st.expander(label, expanded=bool(items)):
        if items:
            for item in items:
                st.markdown(f"- {item}")
        else:
            st.markdown("*No gaps identified for this section.*")

# ── Section 3: PO Questions ───────────────────────────────────────────────────
st.subheader("3️⃣ Questions for the Product Owner")
po_questions = gap.get("po_questions", [])
if po_questions:
    for q in po_questions:
        st.markdown(f"- {q}")
else:
    st.info("No PO questions generated.")

# ── Section 4: Test Scope Estimate ────────────────────────────────────────────
st.subheader("4️⃣ Test Scope Estimate")
scope = gap.get("test_scope", {})
if scope:
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Happy Path",          scope.get("happy_path", 0))
    s2.metric("Negative/Validation", scope.get("negative_validation", 0))
    s3.metric("Role-Based",          scope.get("role_based", 0))
    s4.metric("Edge/Integration",    scope.get("edge_integration", 0))
    s5.metric("Total",               scope.get("total", 0))

    total_tcs = scope.get("total", 0)
    if scope.get("split_recommended"):
        st.warning(f"⚠️ **Split recommended:** {scope.get('split_reason', 'Feature is too large for a single sprint.')}")
    elif total_tcs > 20:
        st.warning(f"⚠️ **{total_tcs} test cases** — consider splitting (> 20 TCs = risk of under-testing).")
    else:
        st.success(f"✅ {total_tcs} test cases — appropriately scoped.")

# ── Section 5: Automation Recommendation ──────────────────────────────────────
st.subheader("5️⃣ Automation Recommendation")
auto = gap.get("automation", {})
if auto:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**🚀 Automate Now**")
        st.caption("Stable, high-value, repeatable — smoke or regression candidates")
        for item in auto.get("automate_now", []):
            st.markdown(f"- {item}")
    with col_b:
        st.markdown("**⏳ Automate Later**")
        st.caption("Valid but lower priority or UI-heavy")
        for item in auto.get("automate_later", []):
            st.markdown(f"- {item}")
    with col_c:
        st.markdown("**👁️ Manual Only**")
        st.caption("Exploratory, one-off, or too unstable to automate")
        for item in auto.get("manual_only", []):
            st.markdown(f"- {item}")

# ── Download ───────────────────────────────────────────────────────────────────
st.divider()
if analysis_mode == "multi":
    md_content = build_multi_markdown_report(story_keys, result_epic, gap)
    fname_key  = result_epic if result_epic else "_".join(story_keys[:3])
else:
    md_content = build_markdown_report(
        story_keys[0] if story_keys else "unknown",
        summaries[0]  if summaries  else "",
        gap,
    )
    fname_key  = story_keys[0] if story_keys else "unknown"

st.download_button(
    label="📥 Download Gap Analysis (Markdown)",
    data=md_content.encode("utf-8"),
    file_name=f"gap_analysis_{fname_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
    mime="text/markdown",
)
