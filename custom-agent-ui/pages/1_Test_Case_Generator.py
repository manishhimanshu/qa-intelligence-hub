"""
Test Case Generator
Generates structured manual test cases from Jira stories following
Kapost test-cases.instructions.md format:
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
AUTOMATION_REPO_ROOT = os.getenv("AUTOMATION_REPO_ROOT", "").strip()

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
# 5=Base level test, 4=Regression level, 3=Functional, 2=Edge case, 1=Don't Test
TESTRAIL_PRIORITY = {"Critical": 5, "High": 3, "Medium": 2, "Low": 1}

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


def rag_query_filtered(
    query: str,
    top_k: int = 10,
    source_eq: str = "",
    source_contains: str = "",
    type_eq: str = "",
    type_prefix: str = "",
    feature_key_eq: str = "",
    doc_domain_eq: str = "",
    path_contains: str = "",
) -> list:
    try:
        from get_relevant_docs import get_relevant_docs_filtered

        return get_relevant_docs_filtered(
            query,
            top_k=top_k,
            source_eq=source_eq,
            source_contains=source_contains,
            type_eq=type_eq,
            type_prefix=type_prefix,
            feature_key_eq=feature_key_eq,
            doc_domain_eq=doc_domain_eq,
            path_contains=path_contains,
        )
    except Exception:
        return rag_query(query, top_k=top_k)


def _normalize_feature_key(value: str) -> str:
    value = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    value = re.sub(r"-+", "-", value)
    return value


@st.cache_data(show_spinner=False)
def load_feature_aliases() -> dict:
    """Load canonical feature aliases used for deterministic feature-scoped retrieval."""
    path = os.path.join(_DIR, "../../rag/docs/automation/feature-context/feature-aliases.json")
    defaults = {
        "notes": ["notes", "note"],
        "archive-content-type": [
            "archive-content-type",
            "archived-content-type",
            "archived_content_type",
            "archive content type",
            "archived content type",
        ],
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            out = {}
            for k, aliases in raw.items():
                canon = _normalize_feature_key(k)
                vals = aliases if isinstance(aliases, list) else [str(aliases)]
                vals = [_normalize_feature_key(v) for v in vals if str(v).strip()]
                out[canon] = sorted(set([canon] + vals))
            return out or defaults
    except Exception:
        pass
    return defaults


def resolve_feature_key(summary: str, feature_prefix: str = "", extra_text: str = "") -> str:
    text = _normalize_feature_key(f"{summary} {feature_prefix} {extra_text}")
    aliases = load_feature_aliases()
    for canon, words in aliases.items():
        for token in words:
            if not token:
                continue
            if re.search(rf"(^|-)({re.escape(token)})(-|$)", text):
                return canon
    return ""


@st.cache_data(show_spinner=False)
def load_automation_guidelines() -> str:
    path = os.path.join(_DIR, "../../rag/docs/automation/automation-guidelines.md")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def _compact_chunks(docs: list, max_items: int = 5, max_chars: int = 650) -> list:
    snippets = []
    for doc in docs[:max_items]:
        path = doc.get("repo_path") or doc.get("source") or doc.get("id", "unknown")
        content = (doc.get("content") or "").strip()
        if not content:
            continue
        snippets.append({
            "path": str(path),
            "snippet": content[:max_chars],
            "id": doc.get("id", ""),
            "type": doc.get("type", ""),
        })
    return snippets


def _exclude_guidelines_docs(docs: list) -> list:
    """Avoid duplicating automation-guidelines in both RAG context and direct prompt injection."""
    filtered = []
    for doc in docs:
        path = str(doc.get("repo_path") or doc.get("source") or "").lower().replace("\\", "/")
        if path.endswith("automation/automation-guidelines.md"):
            continue
        if path.endswith("qa/automation-guidelines.md"):
            continue
        filtered.append(doc)
    return filtered


def _docstore_feature_chunks(
    feature_key: str,
    doc_domain: str,
    path_contains: str,
    max_items: int = 6,
    query_hint: str = "",
) -> list:
    """
    Deterministic fallback: read matching chunks directly from FAISS docstore
    metadata when semantic top-k misses feature-scoped docs.
    """
    if not feature_key:
        return []

    try:
        vs = _load_vectorstore()
    except Exception:
        return []
    if vs is None or not hasattr(vs, "docstore"):
        return []

    q_tokens = {
        t for t in re.split(r"\W+", (query_hint or "").lower()) if len(t) > 3
    }
    path_contains_l = (path_contains or "").lower()
    domain_l = (doc_domain or "").lower()
    feature_l = (feature_key or "").lower()

    scored = []
    for d in vs.docstore._dict.values():
        if not hasattr(d, "metadata"):
            continue
        meta = d.metadata or {}
        mk = str(meta.get("feature_key", "")).lower()
        md = str(meta.get("doc_domain", "")).lower()
        rel = str(meta.get("relative_source_path", "")).lower().replace("\\", "/")
        src = str(meta.get("source", "")).lower().replace("\\", "/")
        path_text = f"{rel} {src}"

        if mk != feature_l:
            continue
        if domain_l and md != domain_l:
            continue
        if path_contains_l and path_contains_l not in path_text:
            continue

        content = getattr(d, "page_content", "") or ""
        content_l = content.lower()
        score = 0
        if q_tokens:
            score += sum(1 for t in q_tokens if t in content_l)
        if feature_l and feature_l in content_l:
            score += 2
        if meta.get("heading"):
            score += 1
        scored.append((score, {
            "content": content,
            **meta,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:max_items]]


@st.cache_data(show_spinner=False, ttl=1800)
def get_feature_context_chunks(
    summary: str,
    feature_prefix: str,
    case_context_text: str = "",
    forced_feature_key: str = "",
    top_k_each: int = 4,
) -> dict:
    feature_key = _normalize_feature_key(forced_feature_key) if forced_feature_key else \
        resolve_feature_key(summary, feature_prefix, case_context_text)
    if not feature_key:
        return {"feature_key": "", "chunks": []}

    query = f"{summary} {feature_key} {case_context_text[:500]} feature context"
    docs = rag_query_filtered(
        query,
        top_k=top_k_each,
        doc_domain_eq="automation_feature_context",
        feature_key_eq=feature_key,
        path_contains="automation/feature-context",
    )
    if not docs:
        docs = _docstore_feature_chunks(
            feature_key=feature_key,
            doc_domain="automation_feature_context",
            path_contains="automation/feature-context",
            max_items=top_k_each,
            query_hint=f"{summary} {case_context_text[:300]}",
        )
    docs = _exclude_guidelines_docs(docs)
    return {
        "feature_key": feature_key,
        "chunks": _compact_chunks(docs, max_items=top_k_each, max_chars=700),
    }


@st.cache_data(show_spinner=False, ttl=1800)
def get_product_knowledge_chunks(
    summary: str,
    feature_prefix: str,
    extra_text: str = "",
    forced_feature_key: str = "",
    top_k_each: int = 6,
) -> dict:
    """
    Return only feature-scoped product knowledge context (md/pdf) for test generation.
    No cross-feature fallback is applied.
    """
    feature_key = _normalize_feature_key(forced_feature_key) if forced_feature_key else \
        resolve_feature_key(summary, feature_prefix, extra_text)
    if not feature_key:
        return {"feature_key": "", "chunks": []}

    query = f"{summary} {feature_key} {extra_text[:500]} product knowledge"
    docs = rag_query_filtered(
        query,
        top_k=top_k_each,
        doc_domain_eq="product_knowledge",
        feature_key_eq=feature_key,
        path_contains="product_knowledge",
    )
    if not docs:
        docs = _docstore_feature_chunks(
            feature_key=feature_key,
            doc_domain="product_knowledge",
            path_contains="product_knowledge",
            max_items=top_k_each,
            query_hint=f"{summary} {extra_text[:300]}",
        )
    if not docs:
        return {"feature_key": feature_key, "chunks": []}

    return {
        "feature_key": feature_key,
        "chunks": _compact_chunks(docs, max_items=top_k_each, max_chars=500),
    }


@st.cache_data(show_spinner=False, ttl=1800)
def get_product_knowledge_context(
    summary: str,
    feature_prefix: str,
    extra_text: str = "",
    forced_feature_key: str = "",
    top_k_each: int = 6,
) -> str:
    bundle = get_product_knowledge_chunks(
        summary,
        feature_prefix,
        extra_text,
        forced_feature_key,
        top_k_each,
    )
    snippets = bundle.get("chunks", [])
    if not snippets:
        return ""
    return "\n\n".join(
        f"[{s.get('path', 'unknown')}]\n{s.get('snippet', '')}" for s in snippets
    )


@st.cache_data(show_spinner="Retrieving automation framework context…", ttl=1800)
def get_automation_context(
    summary: str,
    case_titles: tuple,
    feature_prefix: str,
    case_context_text: str = "",
    forced_feature_key: str = "",
    top_k_each: int = 5,
) -> dict:
    query = summary
    if case_titles:
        query = f"{summary} " + " | ".join(case_titles[:8])
    if case_context_text:
        query = f"{query} {case_context_text[:500]}"

    feature_ctx = get_feature_context_chunks(
        summary,
        feature_prefix,
        case_context_text,
        forced_feature_key,
        top_k_each=top_k_each,
    )

    spec_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="automation_spec")
    spec_docs = _exclude_guidelines_docs(spec_docs)
    if not spec_docs:
        spec_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="cypress_spec")
        spec_docs = _exclude_guidelines_docs(spec_docs)

    po_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="automation_page_object")
    po_docs = _exclude_guidelines_docs(po_docs)
    if not po_docs:
        po_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="cypress_page_object")
        po_docs = _exclude_guidelines_docs(po_docs)

    cmd_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="automation_command")
    cmd_docs = _exclude_guidelines_docs(cmd_docs)
    if not cmd_docs:
        cmd_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="cypress_command")
        cmd_docs = _exclude_guidelines_docs(cmd_docs)

    data_docs = rag_query_filtered(query, top_k=top_k_each, type_prefix="automation_data")
    data_docs = _exclude_guidelines_docs(data_docs)
    if not data_docs:
        data_docs = rag_query_filtered(query, top_k=top_k_each, type_eq="automation_fixture")
        data_docs = _exclude_guidelines_docs(data_docs)

    return {
        "feature_key": feature_ctx.get("feature_key", ""),
        "feature_context": feature_ctx.get("chunks", []),
        "similar_specs": _compact_chunks(spec_docs),
        "page_objects": _compact_chunks(po_docs),
        "custom_commands": _compact_chunks(cmd_docs),
        "test_data_patterns": _compact_chunks(data_docs),
    }


def _normalize_automation_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {
            "spec_file": {"path": "", "content": ""},
            "page_object_updates": [],
            "command_suggestions": [],
            "patch_blocks": [],
            "grounding_evidence": [],
            "similar_spec_style_guide": {
                "style_rules": [],
                "must_reuse_patterns": [],
                "cautions": [],
            },
        }

    spec_file = payload.get("spec_file") or {}
    if not isinstance(spec_file, dict):
        spec_file = {"path": "", "content": str(spec_file)}

    return {
        "spec_file": {
            "path": spec_file.get("path", ""),
            "content": spec_file.get("content", ""),
        },
        "page_object_updates": payload.get("page_object_updates", []) or [],
        "command_suggestions": payload.get("command_suggestions", []) or [],
        "patch_blocks": payload.get("patch_blocks", []) or [],
        "grounding_evidence": payload.get("grounding_evidence", []) or [],
        "feature_context_application": payload.get("feature_context_application", []) or [],
        "similar_spec_style_guide": payload.get("similar_spec_style_guide", {
            "style_rules": [],
            "must_reuse_patterns": [],
            "cautions": [],
        }) or {
            "style_rules": [],
            "must_reuse_patterns": [],
            "cautions": [],
        },
    }


def generate_automation_code(
    story_key: str,
    summary: str,
    feature_prefix: str,
    selected_cases_json: str,
    automation_context_json: str,
    guidelines_text: str,
) -> dict:
    def _has_naked_locators(spec_text: str) -> bool:
        """
        Specs should avoid raw selectors directly in test bodies.
        Locators must be routed via page-object methods/variables.
        """
        if not spec_text:
            return True
        return bool(re.search(r"\bcy\.get\s*\(", spec_text))

    def _filter_command_suggestions_data_only(candidate: dict) -> dict:
        """
        Keep only data-lifecycle/API custom command suggestions.
        UI-flow commands belong in page objects and should be removed.
        """
        cmds = candidate.get("command_suggestions", []) or []
        kept = []
        dropped = 0

        api_keywords = (
            "api", "request", "endpoint", "post", "put", "delete", "get",
            "create", "seed", "cleanup", "teardown", "fixture", "data",
            "book", "entity", "record", "reset", "remove",
        )
        ui_keywords = (
            "click", "hover", "type", "press", "open", "close", "select", "drag",
            "dropdown", "button", "modal", "tooltip", "toolbar", "navigate", "tab",
            "ui", "screen", "page interaction", "render", "visible",
        )

        for cmd in cmds:
            if not isinstance(cmd, dict):
                continue
            text = "\n".join([
                str(cmd.get("command", "") or ""),
                str(cmd.get("rationale", "") or ""),
                str(cmd.get("sample", "") or ""),
            ]).lower()

            has_api = any(k in text for k in api_keywords)
            has_ui = any(k in text for k in ui_keywords)

            # Keep only API/data-lifecycle suggestions; drop UI/local-flow helpers.
            if has_api and not has_ui:
                kept.append(cmd)
            elif has_api and has_ui:
                # If both appear, keep only when rationale is explicitly data lifecycle.
                if any(k in text for k in ("data creation", "data cleanup", "setup", "teardown", "seed")):
                    kept.append(cmd)
                else:
                    dropped += 1
            else:
                dropped += 1

        candidate["command_suggestions"] = kept
        if dropped:
            candidate.setdefault("_meta", {})
            candidate["_meta"]["dropped_ui_custom_command_suggestions"] = dropped
        return candidate

    def _drop_existing_page_object_implementation_updates(candidate: dict) -> dict:
        """
        Safety filter: if a page object file already exists in the repo, do not
        keep suggestions that ask to implement/create that page object.
        """
        updates = candidate.get("page_object_updates", []) or []
        kept = []
        dropped = 0
        for upd in updates:
            if not isinstance(upd, dict):
                continue
            rel_path = str(upd.get("path", "") or "").strip().replace("\\", "/")
            summary = str(upd.get("summary", "") or "")
            patch = str(upd.get("patch", "") or "")

            abs_path = ""
            if rel_path:
                if os.path.isabs(rel_path):
                    abs_path = rel_path
                elif AUTOMATION_REPO_ROOT:
                    abs_path = os.path.join(AUTOMATION_REPO_ROOT, rel_path.replace("/", os.sep))

            exists = bool(abs_path and os.path.exists(abs_path))
            text = f"{summary}\n{patch}".lower()
            asks_implement = any(
                kw in text for kw in (
                    "implement",
                    "create page object",
                    "new page object",
                    "create class",
                    "define class",
                    "add page object",
                )
            )

            if exists and asks_implement:
                dropped += 1
                continue
            kept.append(upd)

        candidate["page_object_updates"] = kept
        if dropped:
            candidate.setdefault("_meta", {})
            candidate["_meta"]["dropped_existing_po_implementation_updates"] = dropped
        return candidate

    def _derive_spec_style_guide(context_payload: dict) -> dict:
        """
        Additional LLM pass: review similar spec chunks only and derive a
        concrete style guide to follow during code generation.
        """
        similar_specs = context_payload.get("similar_specs", []) or []
        if not similar_specs:
            return {
                "style_rules": [],
                "must_reuse_patterns": [],
                "cautions": [],
            }

        spec_samples = []
        for item in similar_specs[:4]:
            spec_samples.append({
                "path": item.get("path", ""),
                "snippet": (item.get("snippet", "") or "")[:900],
            })

        style_prompt = f"""
You are reviewing existing Cypress SPEC files only (not page objects, not custom commands) to extract authoring style.

Similar spec samples:
{json.dumps(spec_samples, ensure_ascii=True)}

Return ONLY valid JSON with keys:
{{
  "style_rules": ["clear style rules to follow in new spec"],
  "must_reuse_patterns": ["specific patterns to mirror from the sampled specs"],
  "cautions": ["anti-patterns or mistakes to avoid based on samples"]
}}
"""
        try:
            style_res = client.chat.completions.create(
                model=st.session_state.selected_model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": style_prompt}],
                temperature=0.0,
                max_tokens=1200,
            )
            raw_style = (style_res.choices[0].message.content or "{}").strip()
            out = json.loads(raw_style)
            if not isinstance(out, dict):
                return {"style_rules": [], "must_reuse_patterns": [], "cautions": []}
            return {
                "style_rules": out.get("style_rules", []) or [],
                "must_reuse_patterns": out.get("must_reuse_patterns", []) or [],
                "cautions": out.get("cautions", []) or [],
            }
        except Exception:
            return {
                "style_rules": [],
                "must_reuse_patterns": [],
                "cautions": [],
            }

    def _extract_must_apply_items(context_payload: dict, max_items: int = 10) -> list:
        """
        Pull concise actionable lines from feature-context chunks so the model
        has an explicit checklist to apply.
        """
        items = []
        for chunk in context_payload.get("feature_context", []) or []:
            snippet = (chunk.get("snippet") or "").strip()
            if not snippet:
                continue
            for line in snippet.splitlines():
                s = line.strip().lstrip("- ").strip()
                if len(s) < 12:
                    continue
                if s.lower().startswith(("#", "##", "###", "purpose", "scope")):
                    continue
                items.append(s)
                if len(items) >= max_items:
                    return items
        return items

    def _looks_basic(candidate: dict, selected_cases_count: int) -> bool:
        spec = ((candidate.get("spec_file") or {}).get("content") or "").strip()
        if not spec:
            return True

        it_count = len(re.findall(r"\bit\s*\(", spec))
        has_setup = bool(re.search(r"\bbefore(?:Each)?\s*\(", spec))
        has_cleanup = bool(re.search(r"\bafter(?:Each)?\s*\(", spec))
        has_assert = ("expect(" in spec) or ("should(" in spec)
        has_intercept = ("cy.intercept(" in spec) or ("@" in spec and "wait(" in spec)
        fc_usage = candidate.get("feature_context_application", []) or []

        # If we selected multiple cases but generated only one/no tests, force refinement.
        if selected_cases_count >= 2 and it_count < 2:
            return True
        if not has_setup or not has_cleanup or not has_assert:
            return True
        # At least one network assertion/wait should exist for most robust e2e specs.
        if not has_intercept:
            return True
        if len(fc_usage) < 2:
            return True
        if _has_naked_locators(spec):
            return True
        return False

    try:
        _ctx_obj = json.loads(automation_context_json)
    except Exception:
        _ctx_obj = {}

    _spec_style_guide = _derive_spec_style_guide(_ctx_obj)
    _must_apply_items = _extract_must_apply_items(_ctx_obj)
    _similar_specs = _ctx_obj.get("similar_specs", []) or []
    _similar_spec_paths = [s.get("path", "") for s in _similar_specs if s.get("path")]
    _existing_po_paths = [
        p.get("path", "") for p in (_ctx_obj.get("page_objects", []) or []) if p.get("path")
    ]

    try:
        _selected_count = len(json.loads(selected_cases_json))
    except Exception:
        _selected_count = 1

    sys_prompt = (
        "You are a Senior Cypress automation engineer for this repository. "
        "Generate code grounded in provided context only. Do not invent custom commands, "
        "page object methods, fixture names, or APIs. If context is missing, emit explicit TODOs. "
        "Never use naked cy.get(...) locators inside spec tests."
    )

    user_prompt = f"""
Generate production-grade Cypress automation artifacts from selected test cases.

Do not return a toy/basic script. The output must be framework-realistic and maintainable.

QUALITY BAR (mandatory):
- Cover each selected manual test case with explicit traceability (in comments or test titles).
- Use robust setup and cleanup hooks (before/beforeEach/after) aligned to project patterns.
- Use page objects and custom commands from provided context where applicable.
- Include deterministic waits with intercept aliases when network dependencies exist.
- Add strong assertions for UI state + data/persistence outcomes.
- Avoid hardcoded brittle waits; prefer intercept/waits by alias.
- Keep selectors and command names grounded to provided context only.
- If a required method/command is unknown, add explicit TODO with source gap note.
- Do not use naked selectors in spec tests (for example cy.get('[data-cy="..."]')).
- Place selectors in page objects as wrapped methods/functions or page-object variables.
- Reuse existing locator wrappers first by checking:
    1) commonPageObjectsAndUtils.cy.js
    2) the current feature page object file (for example contentTypePage.cy.js)
    Only add a new page-object locator wrapper when no suitable existing one is found.

MANDATORY FEATURE CONTEXT UTILIZATION:
- Review and apply all relevant items from the feature-context checklist below.
- If any checklist item is not applied, add a reason in feature_context_application.

Feature-context checklist (apply where relevant):
{json.dumps(_must_apply_items, ensure_ascii=True)}

Similar spec paths:
{json.dumps(_similar_spec_paths, ensure_ascii=True)}

Existing page object files (already implemented — DO NOT ask to implement these):
{json.dumps(_existing_po_paths, ensure_ascii=True)}

SPEC AUTHORING STYLE GUIDE (derived from similar specs — must follow):
{json.dumps(_spec_style_guide, ensure_ascii=True)}

Story: {story_key}
Summary: {summary}
Feature Prefix: {feature_prefix}

Selected Test Cases JSON:
{selected_cases_json}

Automation RAG Context JSON:
{automation_context_json}

Mandatory framework instructions (follow strictly):
{guidelines_text}

Return strict JSON object with keys:
1) spec_file: {{ path: string, content: string }}
2) page_object_updates: [{{ path: string, summary: string, patch: string }}]
3) command_suggestions: [{{ command: string, rationale: string, sample: string }}]
4) grounding_evidence: [{{ artifact: string, source_path: string, reason: string }}]
5) feature_context_application: [{{ context_item: string, applied_in: string, note: string }}]

Output expectations:
- Prefer one spec file in spec_file that is runnable in this framework.
- Use Given/When/Then style comments only when already used by nearby specs.
- Reuse existing command and page-object naming from context.
- Include setup/cleanup where context indicates required data lifecycle.
- Keep code complete and syntactically valid JavaScript/TypeScript based on context.
- Include multiple it(...) blocks when multiple selected test cases are provided.
- Ensure each it(...) has at least one assertion.
- Include a short traceability mapping comment block at top of spec.
- Match describe/it/hook/assertion style to the similar specs style guide above.
- If a page object file already exists, do NOT output an implementation task for it in page_object_updates.
- For existing page objects, reuse methods in spec or propose minimal patch only when strictly necessary.
- Do not write cy.get(...) directly inside it(...) test bodies.
- If a selector is needed, expose it in page object first (method/function or variable per repository pattern), then call that abstraction in spec.
- command_suggestions must include only API-based data setup/cleanup helpers (create/delete/seed/reset).
- Do NOT suggest UI interaction custom commands; UI/local-flow helpers belong in page objects/specs.
"""

    res = client.chat.completions.create(
        model=st.session_state.selected_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=5000,
    )
    raw = (res.choices[0].message.content or "{}").strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    normalized = _normalize_automation_payload(data)
    normalized = _drop_existing_page_object_implementation_updates(normalized)
    normalized = _filter_command_suggestions_data_only(normalized)

    if _looks_basic(normalized, _selected_count):
        improve_prompt = f"""
Refine this generated automation payload so it meets senior QA automation standards.

Story: {story_key}
Summary: {summary}
Feature Prefix: {feature_prefix}
Selected test cases count: {_selected_count}

Selected Test Cases JSON:
{selected_cases_json}

Automation RAG Context JSON:
{automation_context_json}

Mandatory framework instructions:
{guidelines_text}

Spec authoring style guide derived from similar specs:
{json.dumps(_spec_style_guide, ensure_ascii=True)}

Current payload to improve:
{json.dumps(normalized, ensure_ascii=True)}

Improve it with these non-negotiables:
1. Non-basic spec with realistic setup, execution, and teardown.
2. Explicit coverage for selected cases.
3. Intercepts/alias waits where applicable.
4. Strong assertions in each test.
5. Grounded commands/page-object methods only.
6. Explicit feature_context_application with actionable usage (or reason not used).
7. Never propose implementing a page object that already exists; only reuse or minimally patch.
8. Remove all naked cy.get(...) usage from spec test bodies.
9. Reuse existing locator wrappers from commonPageObjectsAndUtils.cy.js and current feature page object first; add only minimal new page-object wrappers when missing.

Return strict JSON with the same schema keys only.
"""
        retry = client.chat.completions.create(
            model=st.session_state.selected_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": improve_prompt},
            ],
            temperature=0.05,
            max_tokens=5500,
        )
        retry_raw = (retry.choices[0].message.content or "{}").strip()
        try:
            retry_data = json.loads(retry_raw)
            normalized = _normalize_automation_payload(retry_data)
            normalized = _drop_existing_page_object_implementation_updates(normalized)
            normalized = _filter_command_suggestions_data_only(normalized)
        except Exception:
            pass

    normalized["similar_spec_style_guide"] = _spec_style_guide

    return normalized


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
    # top_k=15: narrow the candidate set to reduce semantically-similar-but-unrelated cases.
    docs = rag_query(f"{story_key} {summary}", top_k=15)

    # Aggregate ALL chunks per case (cases can be split across multiple 800-char chunks)
    case_chunks: dict = {}   # case_id → list of content strings
    for rank, doc in enumerate(docs):
        doc_id = doc.get("id", "")
        if not doc_id.startswith("testrail_"):
            continue
        content = doc.get("content", "")
        # Accept only if: (a) story key appears in the indexed content (definite link),
        # OR (b) it is in the top 5 semantic results (high-confidence similarity).
        # This filters out loosely-related cases from unrelated stories.
        if story_key not in content and rank >= 5:
            continue
        m = re.search(r'testrail_(\d+)', doc_id)
        case_id = f"C{m.group(1)}" if m else doc_id
        # Strip HTML inline
        clean = re.sub(r'<br\s*/?>', '\n', content)
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


@st.cache_data(show_spinner=False, ttl=3600)
def get_role_context(summary: str, feature_prefix: str) -> str:
    """
    Retrieve role-permission context from the RAG index for this feature area.
    Queries for:
      1. The universal role rules section (always included)
      2. The feature-specific role section (matched by summary + feature prefix)

    The role-permissions.md doc is split by heading, so each section is
    a separate FAISS chunk.  We filter to docs sourced from that file and
    cap the total at ~1200 chars so it doesn't bloat the generation prompt.
    """
    # Build a query that targets both universal rules and the specific feature
    query = f"role permissions {feature_prefix} {summary}"
    docs  = rag_query(query, top_k=30)

    universal_chunk   = None
    access_level_chunk = None
    feature_chunk     = None
    seen_ids: set     = set()

    for doc in docs:
        src     = doc.get("source", "")
        content = doc.get("content", "").strip()
        doc_id  = doc.get("id", "")
        if doc_id in seen_ids:
            continue
        # Only use docs from the role-permissions markdown
        if "role-permissions" not in src.lower():
            continue
        seen_ids.add(doc_id)

        heading = doc.get("heading", content[:60]).lower()
        if "universal" in heading:
            universal_chunk = content[:700]
        elif "object-level" in heading or "manage access" in heading or "owner access" in heading:
            access_level_chunk = content[:700]
        elif not feature_chunk:
            # Only accept as feature-specific if the feature prefix or at least one
            # meaningful word from the summary appears in the chunk heading or content.
            # This prevents a high-ranking but wrong section (e.g. Gallery) from being
            # used as context for a Calendar or Canvas feature.
            summary_keywords = {
                w.lower() for w in re.split(r'\W+', summary) if len(w) > 3
            }
            prefix_keywords  = {w.lower() for w in re.split(r'\W+', feature_prefix) if w}
            candidate_text   = (heading + " " + content[:600]).lower()
            if prefix_keywords & set(re.split(r'\W+', candidate_text)) or \
               summary_keywords & set(re.split(r'\W+', candidate_text)):
                feature_chunk = content[:400]

    parts = []
    if universal_chunk:
        parts.append(universal_chunk)
    if access_level_chunk:
        parts.append(access_level_chunk)
    if feature_chunk:
        parts.append(feature_chunk)

    return "\n\n".join(parts)


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
        r'^(definition of done|notes?:|out of scope|assumptions?|dependencies|steps to reproduce)',
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
    extract_acceptance_criteria._gherkin_buf = []  # reset per-call scenario buffer
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

        # ── Gherkin keywords → accumulate into a full scenario, one AC per Given block
        # Each Given…When…Then…And…But block = ONE scenario = ONE AC item.
        # Individual keyword lines are NOT separate requirements.
        if _gherkin.match(s):
            # If this is a new 'Given', flush any in-progress scenario first
            if re.match(r'^Given\b', s, re.IGNORECASE):
                if hasattr(extract_acceptance_criteria, '_gherkin_buf') and extract_acceptance_criteria._gherkin_buf:
                    scenario = " / ".join(extract_acceptance_criteria._gherkin_buf)
                    ac.append(f"{current_group}: {scenario}" if current_group else scenario)
                extract_acceptance_criteria._gherkin_buf = [s]
            else:
                if not hasattr(extract_acceptance_criteria, '_gherkin_buf'):
                    extract_acceptance_criteria._gherkin_buf = []
                extract_acceptance_criteria._gherkin_buf.append(s)
            continue

        # ── Horizontal rule — skip without stopping or adding as AC item ────────
        # '---' starts with '-' so _bullet_start would match it and produce
        # a spurious '--' AC item, inflating ac_count and confusing GPT coverage.
        if re.match(r'^-{2,}$', s):
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

    # Flush any trailing Gherkin scenario that didn't hit a boundary
    if extract_acceptance_criteria._gherkin_buf:
        scenario = " / ".join(extract_acceptance_criteria._gherkin_buf)
        ac.append(f"{current_group}: {scenario}" if current_group else scenario)
        extract_acceptance_criteria._gherkin_buf = []

    return ac


def extract_steps_to_reproduce(content: str) -> list:
    """Extract Steps to Reproduce lines from structured story content."""
    steps, in_steps = [], False
    _stop_sections = re.compile(
        r'^(#{1,4}\s|acceptance criteria|definition of done|notes?:|out of scope)',
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


def normalize_ticket(
    story_key: str,
    summary: str,
    description: str,
    ac_list: tuple,
    str_list: tuple,
    comments: str,
    ticket_type: str = "Story",
) -> dict:
    """
    Convert raw Jira fields into a canonical schema before LLM processing.
    Applies Kapost conventions:
      Story: AC → requirements, Description → dev notes/context
      Bug:   STR → test flow, Description → root cause hints
    Returns a dict that is stable, hashable-friendly, and passed to LLM steps.
    """
    ac    = list(ac_list)
    steps = list(str_list)

    # Determine primary source following the same priority as generate_test_cases
    if ac:
        primary_source = "ac"
        requirements   = ac
    elif steps:
        primary_source = "str"
        requirements   = steps
    elif description.strip():
        primary_source = "description"
        requirements   = [
            re.sub(r'^[-*•]\s+|^\d+\.\s+', '', ln.strip()).strip()
            for ln in description.splitlines()
            if len(re.sub(r'^[-*•]\s+|^\d+\.\s+', '', ln.strip()).strip()) > 15
        ]
    else:
        primary_source = "none"
        requirements   = []

    feature_prefix = detect_feature_prefix(summary)
    feature_key = resolve_feature_key(
        summary,
        feature_prefix,
        f"{description} {' '.join(ac)} {' '.join(steps)} {comments}",
    )

    return {
        "ticket_key":     story_key,
        "ticket_type":    ticket_type,
        "summary":        summary,
        "feature_key":    feature_key,
        "primary_source": primary_source,   # "ac" | "str" | "description" | "none"
        "requirements":   requirements,     # authoritative list, source-agnostic
        "steps_to_reproduce": steps,        # always preserved separately
        "description_notes":  description.strip(),
        "comments":           comments.strip(),
    }


@st.cache_data(show_spinner=False, ttl=3600)
def extract_requirements(
    ticket_json: str,   # JSON-serialised normalised ticket (hashable for cache)
    cypress_context: str,
    existing_tcs_json: str,
    role_context: str = "",  # role-permission context from RAG
) -> dict:
    """
    Pipeline Step 1 — LLM analyses the normalised ticket and returns:
      - functional_requirements: refined, unambiguous requirement statements
      - edge_cases:              boundary / unexpected input scenarios
      - negative_scenarios:      invalid inputs, unauthorised access, missing data
      - validation_rules:        field rules, format rules, state constraints
      - api_interactions:        any API/integration touch points mentioned
      - qa_gaps:                 missing information that should have been in the ticket
                                 (e.g. 'Error message text not defined',
                                       'Permission rules for contributor role unclear')
    """
    ticket = json.loads(ticket_json)
    reqs   = ticket["requirements"]
    source_label = {
        "ac":          "Acceptance Criteria",
        "str":         "Steps to Reproduce",
        "description": "Description (no AC provided)",
        "none":        "Summary only (no structured requirements)",
    }[ticket["primary_source"]]

    req_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(reqs)) or "Not provided."
    str_block = "\n".join(f"{i+1}. {s}" for i, s in enumerate(ticket["steps_to_reproduce"], 1)) or "Not provided."
    # Strip base64 blobs (inline images pasted into Jira descriptions) before sending to LLM.
    # They consume tokens silently without adding any testable information.
    _raw_desc  = ticket["description_notes"] or ""
    _raw_desc  = re.sub(r'[A-Za-z0-9+/]{100,}={0,2}', '[image-removed]', _raw_desc)
    desc_block = _raw_desc[:3000] or "Not provided."
    comments_block = ticket["comments"] or "Not provided."

    existing_snippet = existing_tcs_json[:1200] if existing_tcs_json else "None"
    cypress_snippet  = cypress_context[:800]    if cypress_context     else "None"
    role_section     = (
        f"\nRole Permission Context (use when identifying permission-related edge cases and QA gaps):\n{role_context}\n"
        if role_context.strip() else ""
    )

    prompt = f"""You are a senior QA architect analysing a Jira ticket before test case generation.

Ticket: {ticket['ticket_key']} ({ticket['ticket_type']}) — {ticket['summary']}

Primary requirements source: {source_label}
Requirements:
{req_block}

Steps to Reproduce:
{str_block}

Background / Dev Notes:
{desc_block}

Comments (BA/PO clarifications):
{comments_block}
{role_section}
Existing TestRail cases (for gap awareness):
{existing_snippet}

Existing Cypress patterns (for automation awareness):
{cypress_snippet}

════════════════════════════════════════════
TASK
════════════════════════════════════════════
Analyse the ticket above and extract a comprehensive test planning brief.

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "functional_requirements": [
    "Clear, unambiguous restatement of each requirement. One sentence per item."
  ],
  "edge_cases": [
    "Generate edge cases ONLY when directly applicable to the requirement.
        Do not invent:
        - performance tests
        - unsupported browser tests
        - offline tests
        - concurrency tests
        - stress tests
    unless explicitly mentioned in requirements, acceptance criteria, comments, or story context."
    "IMPORTANT: For any search, filter, or list feature also include: zero-results / no-match state (valid query that returns no results), single-result state, and maximum-results state."
  ],
  "negative_scenarios": [
    "Invalid inputs, unauthorised access, missing required fields, wrong data types.",
        "IMPORTANT: For search/filter features also include: query that matches nothing (no results found), query that partially matches, query with only whitespace.",
        "Do NOT include network/API failure, timeout, offline, server-error, concurrency, performance, or browser-compatibility scenarios unless explicitly stated in requirements, AC, STR, comments, or description."
  ],
  "validation_rules": [
    "Field-level rules, format constraints, state machine rules, dependent field logic."
  ],
  "api_interactions": [
    "API endpoints, payloads, or integration points implied by the requirements. Empty list if none."
  ],
  "test_design_techniques": [
    "Name the specific QA techniques applicable: Boundary Value Analysis, Equivalence Partitioning, State Transition, Decision Table, etc."
  ],
  "qa_gaps": [
    "Missing information that a tester needs but the ticket does not provide.",
    "Examples: 'Error message text not specified', 'Permission rules for contributor role unclear', 'Expected API response not defined'.",
    "Return empty list if ticket is complete."
  ]
}}"""

    resp = client.chat.completions.create(
        model=st.session_state.selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2000,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    out = json.loads(raw)
    if isinstance(out, dict) and not out.get("feature_key"):
        out["feature_key"] = ticket.get("feature_key", "")
    return out


def _resequence_case_ids(cases: list, feature_prefix: str) -> list:
    resequenced = []
    for idx, case in enumerate(cases, 1):
        updated = dict(case)
        updated["tc_id"] = f"{feature_prefix}-{idx:03d}"
        resequenced.append(updated)
    return resequenced


def _drop_unstated_scenarios(cases: list, story_evidence_text: str) -> tuple[list, int]:
    """Drop generated cases for scenarios not explicitly present in story evidence."""
    evidence = (story_evidence_text or "").lower()
    if not cases:
        return [], 0

    guard_terms = {
        "network_failure": [
            "network failure", "network error", "connection lost", "offline",
            "server error", "api failure", "timeout", "service unavailable",
            "500", "502", "503", "504",
        ],
        "concurrency": ["concurrent", "simultaneous", "race condition", "parallel edit", "conflict"],
        "performance": ["performance", "load time", "stress", "high load", "latency"],
        "browser": ["unsupported browser", "cross-browser", "browser compatibility"],
    }

    kept, dropped = [], 0
    for case in cases:
        text = "\n".join([
            str(case.get("title", "") or ""),
            str(case.get("preconditions", "") or ""),
            str(case.get("steps", "") or ""),
            str(case.get("expected_result", "") or ""),
        ]).lower()

        unsupported = False
        for terms in guard_terms.values():
            if any(term in text for term in terms) and not any(term in evidence for term in terms):
                unsupported = True
                break

        if unsupported:
            dropped += 1
            continue
        kept.append(case)

    return kept, dropped


@st.cache_data(show_spinner=False, ttl=3600)
def refine_generated_cases(
    cases_json: str,
    requirements_json: str,
    feature_prefix: str,
    critique_json: str = "{}",
) -> list:
    """Principal-QA final review pass using requirements and optional critique findings."""
    # Format critique findings as explicit action items so the model receives
    # concrete instructions rather than a raw JSON blob.
    _critique_section = ""
    try:
        _crit = json.loads(critique_json) if critique_json and critique_json != "{}" else {}
    except Exception:
        _crit = {}
    if _crit:
        _crit_lines = ["====================================================",
                       "MANDATORY FIXES FROM PREVIOUS CRITIQUE PASS",
                       "You MUST address every item below before returning the final suite.",
                       "===================================================="]
        _missing = _crit.get("missing_coverage", [])
        if _missing:
            _crit_lines.append("\nMISSING COVERAGE — add test cases for each of these:")
            for _m in _missing:
                _crit_lines.append(f"  ✗ {_m}")
        _dups = _crit.get("duplicate_pairs", [])
        if _dups:
            _crit_lines.append("\nDUPLICATE PAIRS — merge or remove one from each pair:")
            for _pair in _dups:
                _crit_lines.append(f"  ✗ {' ↔ '.join(_pair) if isinstance(_pair, list) else _pair}")
        _suggestions = _crit.get("improvement_suggestions", [])
        if _suggestions:
            _crit_lines.append("\nIMPROVEMENT SUGGESTIONS — apply each one:")
            for _s in _suggestions:
                _crit_lines.append(f"  ✗ {_s}")
        _crit_lines.append("\nDo not return the suite until all items above are resolved.\n")
        _critique_section = "\n".join(_crit_lines)

    prompt = f"""You are a Principal QA Engineer performing a FINAL QUALITY REVIEW of AI-generated test cases.

IMPORTANT:
Do NOT blindly accept the generated test cases.

Your job is to act as a QA reviewer and improve the test suite before it is returned.

You may:
- Rewrite test cases
- Split test cases
- Merge test cases
- Remove test cases
- Add missing test cases

Your goal is to produce a high-quality, non-overlapping, realistic, and executable test suite.

Requirements Brief (source of truth):
{requirements_json}

IMPORTANT:

Use the requirements brief as the source of truth.

For every test case ask:

1. Can this test case be directly traced to a requirement,
   edge case, validation rule, or negative scenario?

2. Is any requirement missing coverage?

3. Is this test case inventing behavior not present in
   the requirements?

If a test case cannot be traced to a requirement,
remove it.

Current Generated Cases:
{cases_json}

{_critique_section}
====================================================
QUALITY CHECKS
====================================================

1. DUPLICATE COVERAGE DETECTION
- Detect overlapping scenarios.
- Merge test cases that validate the same workflow, UI area, or acceptance criteria.
- Avoid separate test cases when preconditions, steps, and expected outcomes substantially overlap.
- Keep the most complete version when duplicates exist.

Rule:
Every requirement should ideally be tested once unless different user workflows require separate validation.

2. REMOVE ARTIFICIAL EDGE CASES
- Remove unrealistic or AI-invented scenarios.
- Do not keep impossible user actions (for example: simultaneous hovering/clicking of multiple controls).

Allowed edge cases include only realistic ones such as:
- Empty/null/invalid values
- Maximum/minimum limits
- Unsupported file types
- Permission restrictions
- Browser refresh / save and reload
- User cancellation flows
- Realistic user mistakes

3. REMOVE GENERIC EXPECTED RESULTS
- Expected results must be explicit, measurable, and independently verifiable.
- Forbidden vague phrases include:
  - Works correctly
  - Behaves as expected
  - Validation works
  - Displays properly
  - No errors occur
  - Functionality succeeds
  - System handles correctly

4. EXPECTED RESULTS MUST ALWAYS BE NUMBERED
- expected_result must always be numbered lines:
  1. ...
  2. ...
  3. ...
- Never return expected results as a paragraph.

5. VERIFY TESTABILITY
- Every expected result must be objectively verifiable.
- A tester must be able to determine PASS or FAIL.

6. SPLIT OVERSIZED TEST CASES
- If one test case validates more than 5 independent behaviors, split it.
- Keep cases focused so one failing requirement does not invalidate unrelated checks.

7. REMOVE UNSUPPORTED ASSUMPTIONS
- Do not invent behavior not supported by available information.
- If behavior is not defined, use neutral, verifiable assertions rather than product guesses.

8. REQUIREMENT TRACEABILITY REVIEW
- Verify coverage_refs are actually covered by the case steps and expected results.
- Remove incorrect refs and add clearly applicable missing refs.

9. ADD MISSING HIGH-VALUE TESTS WHEN APPLICABLE
- Save/reload persistence
- Edit/update/delete existing content
- Copy/paste behavior
- End-to-end workflow completion
- Undo/redo (only if indicated in generated suite context)

10. AUTOMATION FRIENDLY OUTPUT
- Keep language objective and observable (UI state, data state, persistence state).
- Output should be suitable for both manual and automation implementation.

11. REQUIREMENT-CENTRIC VALIDATION
- For every test case, ask: "Can I directly trace this test case to a requirement?"
- If NO, remove the test case.
- Do not invent the following unless explicitly mentioned in requirements:
    - Offline scenarios
    - Unsupported browser scenarios
    - Performance scenarios
    - Concurrency scenarios
    - Stress scenarios

12. EXPECTED RESULT COMPLETENESS
    -Reject expected results that merely repeat the action.

        Bad:

        a. Image uploads successfully.

        b. Link is created successfully.

        Good:

        a. Image is inserted into the editor.
        b. Image is rendered correctly.
        c. Image persists after save.
        d. Image remains after page reload.

        Good:

        a. Hyperlink formatting is applied.
        b. URL is associated with selected text.
        c. Clicking the link opens the configured URL.
        d. Link persists after save and reload.

- For every expected result, verify it must answers:
    - What UI changes?
    - What data changes?
    - What validation occurs?
    - What persists after save/reload?

    when applicable.

- If expected results only restate the action, rewrite them.

13. EXPECTED RESULT COVERAGE THRESHOLD
- Every expected result MUST verify at least TWO of the following states:
  - UI state (what is now visible, enabled, disabled, or changed on screen?)
  - Data state (what was saved, updated, or deleted in the database?)
  - Validation state (what error, warning, or success message appeared?)
  - Persistence state (does the change survive a page reload or re-login?)
  - Integration state (was an API called? was an external system updated?)
- Expected results that verify only one state must be rewritten to include a second.

====================================================
SELF REVIEW
====================================================
Note: The SELF REVIEW score is an internal reasoning step only.
Do NOT include scores or review commentary in the JSON output.
Before final output, score the suite:
- Duplicate Coverage Score (0-10)
- Expected Result Quality Score (0-10)
- Realism Score (0-10)
- Traceability Score (0-10)
- Automation Readiness Score (0-10)

If any score is below 8, perform another internal review pass before returning final suite.

====================================================
OUTPUT FORMAT
====================================================
Return ONLY the final improved test suite as a valid JSON array.
For every case include:
- tc_id
- title
- preconditions
- steps
- expected_result (numbered lines)
- priority
- type
- test_data
- automation_status
- roles_covered
- coverage_refs

Remove duplicate, unrealistic, unverifiable, and low-value test cases.
Final output should resemble senior QA design-review quality."""

    resp = client.chat.completions.create(
        model=st.session_state.selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4000,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    cases = json.loads(raw)
    return _resequence_case_ids(cases, feature_prefix)


@st.cache_data(show_spinner=False, ttl=3600)
def critique_test_cases(
    cases_json: str,    # JSON string of generated test cases
    requirements_json: str,  # JSON string of extracted requirements brief
) -> dict:
    """
    Pipeline Step 3 — LLM self-critique pass.
    Reviews generated test cases against the requirements brief and returns:
      - case_scores: per-case confidence score + reason
      - overall_score: 0.0–1.0
      - missing_coverage: scenarios not covered by any generated case
      - duplicate_pairs: pairs of cases covering the same scenario
      - improvement_suggestions: concrete rewrites or additions
    """
    prompt = f"""You are a senior QA lead reviewing a set of generated test cases.

Requirements Brief (what should be covered):
{requirements_json}

Generated Test Cases:
{cases_json}

════════════════════════════════════════════
TASK
════════════════════════════════════════════
Review the generated test cases against the requirements brief.

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "duplicate_score": 0.9,
  "traceability_score": 0.8,
  "expected_result_score": 0.6,
  "realism_score": 0.9,
  "overall_score": 0.8,
  "overall_reason": "One-sentence summary of coverage quality.",
  "case_scores": [
    {{
      "tc_id": "TC-FEATURE-001",
      "score": 0.90,
      "reason": "Clear steps, correct expected result, maps to FR-1."
    }}
  ],
  "missing_coverage": [
    "Scenario not covered by any generated test case."
  ],
  "duplicate_pairs": [
    ["TC-FEATURE-003", "TC-FEATURE-007"]
  ],
  "improvement_suggestions": [
    "Add a test case for empty filter value (edge case EC-2 not covered)."
  ]
}}"""

    resp = client.chat.completions.create(
        model=st.session_state.selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2000,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


@st.cache_data(show_spinner=False, ttl=3600)
def generate_test_cases(
    story_key: str,
    summary: str,
    description: str,     # full description text
    ac_list: tuple,       # tuple so it's hashable for cache key
    str_list: tuple,
    comments: str,        # pre-fetched comment text ('' if disabled)
    cypress_context: str, # relevant Cypress patterns from RAG ('' if none)
    product_knowledge_context: str,  # feature-scoped product docs context ('' if none)
    existing_tcs: tuple,
    selected_roles: tuple,
    feature_prefix: str,
) -> list:
    """
    Pipeline Step 2 — generate test cases using the structured requirements brief
    produced by extract_requirements() (Step 1) as the primary input.
    Falls back gracefully if the brief is unavailable.
    """
    # ── Build clean existing-case titles block ────────────────────────────────
    existing_titles = []
    for tc in existing_tcs:
        try:
            raw_content = json.loads(tc).get("content", "")
        except (json.JSONDecodeError, TypeError):
            raw_content = tc if isinstance(tc, str) else ""
        title_match = re.search(r'Title:\s*(.+)', raw_content)
        if title_match:
            existing_titles.append(title_match.group(1).strip()[:120])
    existing_block = "\n".join(f"- {t}" for t in existing_titles) or "None"

    # ── Normalise ticket and run Step 1 (requirement extraction) ─────────────
    ticket_type = "Bug" if any(
        kw in summary.lower() for kw in ("bug", "fix", "defect", "regression", "broken", "error", "fail")
    ) else "Story"
    ticket = normalize_ticket(
        story_key, summary, description, ac_list, str_list, comments, ticket_type
    )
    ticket_json = json.dumps(ticket, sort_keys=True)

    existing_tcs_json = json.dumps(existing_titles[:20])  # cap for token budget
    role_ctx  = get_role_context(summary, feature_prefix)
    brief     = extract_requirements(ticket_json, cypress_context, existing_tcs_json, role_ctx)

    # ── Build prompt blocks from the requirements brief ───────────────────────
    fr_block   = "\n".join(f"FR-{i:02d}: {r}" for i, r in enumerate(brief.get("functional_requirements", ticket["requirements"]), 1))
    ec_block   = "\n".join(f"EC-{i:02d}: {e}" for i, e in enumerate(brief.get("edge_cases", []), 1)) or "None identified."
    neg_block  = "\n".join(f"NS-{i:02d}: {n}" for i, n in enumerate(brief.get("negative_scenarios", []), 1)) or "None identified."
    val_block  = "\n".join(f"VR-{i:02d}: {v}" for i, v in enumerate(brief.get("validation_rules", []), 1)) or "None identified."
    api_block  = "\n".join(f"- {a}" for a in brief.get("api_interactions", [])) or "None identified."
    tech_block = ", ".join(brief.get("test_design_techniques", [])) or "Standard functional testing."
    str_block  = "\n".join(f"{i}. {s}" for i, s in enumerate(str_list, 1)) or "Not provided."

    fr_count = len(brief.get("functional_requirements", ticket["requirements"])) or 1

    # Strip base64 blobs from description before injecting into Step 2 prompt
    _desc_clean = re.sub(r'[A-Za-z0-9+/]{100,}={0,2}', '[image-removed]', description)
    _desc_clean = _desc_clean.strip()[:3000] or "Not provided."

    roles_block = ", ".join(selected_roles) or "admin, editor, contributor, consumer"
    comments_section = (
        f"\nComments (BA/PO clarifications):\n{comments.strip()}\n"
        if comments.strip() else ""
    )
    cypress_section = (
        f"\nExisting Cypress Automation Patterns (inform automation_status):\n{cypress_context[:600]}\n"
        if cypress_context.strip() else ""
    )
    product_knowledge_section = (
        f"\nFeature-Scoped Product Knowledge (same feature only):\n"
        f"{product_knowledge_context[:1800]}\n"
        if product_knowledge_context.strip() else
        "\nFeature-Scoped Product Knowledge: none found for this feature. "
        "Do not infer behavior from other features.\n"
    )
    role_context_section = (
        f"\nRole Permission Context (use to write precise preconditions, scope negative role cases,\n"
        f"and decide whether a behaviour change per role is expected for this feature):\n{role_ctx}\n"
        if role_ctx.strip() else ""
    )

    item_tag = "SC" if ticket["primary_source"] == "str" else "FR"
    source_note = (
        "Requirements were derived from Steps to Reproduce (no formal AC provided)."
        if ticket["primary_source"] == "str"
        else "Requirements sourced from Acceptance Criteria."
        if ticket["primary_source"] == "ac"
        else "Requirements inferred from Description (no AC or STR provided)."
    )

    prompt = f"""You are a senior QA engineer with 10+ years experience following Kapost testing standards.
The platform is a B2B content marketing SaaS with 4 user roles: admin, editor, contributor, consumer.

Jira {ticket_type}: {story_key} — {summary}
{source_note}

════════════ REQUIREMENTS BRIEF ════════════
Functional Requirements ({fr_count} items — ALL must be covered by at least one positive test case):
{fr_block}

Edge Cases (must be covered):
{ec_block}

Negative Scenarios (must be covered):
{neg_block}

Validation Rules (apply to relevant test cases):
{val_block}

API / Integration Touch Points:
{api_block}

Test Design Techniques to apply: {tech_block}

Steps to Reproduce (use as test execution steps):
{str_block}
{comments_section}
Background / Dev Notes (context only — not requirements):
{_desc_clean}
{product_knowledge_section}
{role_context_section}{cypress_section}
Existing TestRail Test Cases (do NOT duplicate):
{existing_block}

Roles to cover: {roles_block}
Feature prefix for TC IDs: {feature_prefix}

══════════════════════════════════════════════════════
COVERAGE MANDATE
══════════════════════════════════════════════════════
There are {fr_count} functional requirements above ({item_tag}-01 … {item_tag}-{fr_count:02d}).

STEP 1 — SCENARIO-LEVEL POSITIVE CASES:
    Generate business-scenario test cases, not one case per individual requirement or UI control.
    A single positive case may cover multiple related requirements when they are validated in the same workflow,
    screen area, or user interaction sequence.
    Prefer grouping when setup, navigation, and pass/fail intent are shared.

    MERGE these kinds of checks into one test case when they belong to the same scenario:
    - Multiple related toolbar options or tooltips in the same toolbar walkthrough
    - Multiple formatting actions validated in one formatting workflow
    - Related UI presence, availability, state, and hover/tooltip checks on the same component
    - Closely related validations that would otherwise repeat the same setup and steps

    Example grouping:
    - Bold tooltip + Italic tooltip + Underline tooltip -> one case: verify formatting toolbar options and tooltips
    - Bold + Italic + Underline + Strikethrough formatting -> one case: verify formatting actions from the toolbar
    - Toolbar visibility + option availability + tooltip placement -> one UI validation case

    Keep separate test cases only when:
    - Preconditions differ significantly
    - Different business workflows are involved
    - Failure reporting would become unclear if merged
    - The functionality is independently automatable or operationally distinct

    Usually keep these as separate scenarios when present:
    - Link behavior
    - Image upload behavior
    - Date picker behavior
    - Data persistence/save behavior
    - Suspension/reactivation or major role-state transitions

    Tag each title with the dominant coverage area, for example "[{item_tag}-01/{item_tag}-02] ..." when one case covers multiple requirements.

STEP 2 — EDGE & BOUNDARY CASES:
  Cover all Edge Cases (EC-01…) using Boundary Value Analysis and Equivalence Partitioning.
  For any search, filter, or list feature ALWAYS include:
    - A case where the query/filter returns ZERO results (no-match / empty results state)
    - A case where the query returns exactly one result
    Group related edge validations when they belong to the same workflow and can be executed together without losing clarity.
    Tag: "[EC-XX] <boundary or edge being tested>"

STEP 3 — NEGATIVE CASES:
  Cover all Negative Scenarios (NS-01…) and Validation Rules.
  For search/filter features ALWAYS include a case for a valid query that matches nothing.
    Merge closely related invalid-input checks into one negative scenario when they share the same form, dialog, or workflow.
    Tag: "[{item_tag}-XX – Negative] <what fails or is invalid>"

STEP 4 — SUPPLEMENTARY:
    - Role-permission cases only when explicitly required by story evidence.
    - Do not add generic error/network/concurrency cases unless explicitly stated in story evidence.

QUALITY TARGET:
    Group test cases ONLY when all of these hold:
    - Same user workflow
    - Same business objective
    - Same pass/fail outcome
    Do NOT merge unrelated validations simply to reduce test count.
    Favor maintainability over minimizing number of test cases.
    Minimise repeated setup steps while preserving clear pass/fail reporting.
    Do NOT create separate cases only because different UI elements or tooltips are being checked.
    Do NOT stop until every {item_tag}-01 through {item_tag}-{fr_count:02d} AND every EC and NS is covered by at least one case.
══════════════════════════════════════════════════════

STRICT REALISM RULES:
- Only generate test cases that are explicitly supported by this Jira story content (Requirements, AC, STR, comments, description).
- If a scenario is not present in story evidence, do NOT create a test case for it.
- Specifically forbidden unless explicitly mentioned in story evidence:
    - Network/API failure, server errors, timeouts, offline behavior
    - Concurrency/race-condition scenarios
    - Performance/load/stress scenarios
    - Unsupported-browser/cross-browser scenarios
- If uncertain, add it as a QA gap/question rather than a test case.

Return ONLY a valid JSON array — no markdown fences, no explanation:
[
  {{
    "tc_id":             "{feature_prefix}-001",
        "title":             "[{item_tag}-XX/{item_tag}-YY] [Scenario] verifies [Expected Outcome]",
    "priority":          "Critical|High|Medium|Low",
    "type":              "Functional|Regression|Smoke|Integration|Negative|Edge",
    "preconditions":     "Role required, existing data state, feature flags if any",
    "steps":             "1. First step\\n2. Second step\\n3. Third step",
    "expected_result":   "Observable, verifiable outcome after all steps",
    "test_data":         "CY_Test | specific values, or 'N/A'",
    "automation_status": "Automated|Manual|Candidate",
        "roles_covered":     ["admin"],
        "coverage_refs":     ["{item_tag}-01", "{item_tag}-02", "EC-01"]
  }}
]

Rules:
- Sequential IDs: {feature_prefix}-001, {feature_prefix}-002, etc.
- Priority: Critical = core/data-loss, High = main flows, Medium = edge/negative cases, Low = cosmetic
- automation_status: Candidate = stable repeatable, Manual = exploratory, Automated = maps to Cypress
- Always prefix test data with "CY_Test |"
- coverage_refs must list every FR/SC/EC/NS/VR item materially covered by that test case
- ROLE SCOPING RULE

    Generate role-based test cases ONLY when:

    1. Requirements explicitly mention roles.
    2. Acceptance criteria differ by role.
    3. Permissions affect feature visibility.
    4. Access control is part of the story.

    Otherwise:

    Do not generate contributor, consumer, editor, or admin specific tests.

    Use a single generic positive workflow."""

    resp = client.chat.completions.create(
        model=st.session_state.selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=16000,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    _story_evidence_text = "\n".join([
        fr_block,
        ec_block,
        neg_block,
        val_block,
        api_block,
        str_block,
        comments or "",
        _desc_clean,
        product_knowledge_context or "",
        cypress_context or "",
    ])

    # Recover from truncated JSON — trim to last complete object
    try:
        cases = json.loads(raw)
        cases, dropped = _drop_unstated_scenarios(cases, _story_evidence_text)
        if dropped:
            st.warning(
                f"⚠️ Removed {dropped} generated test case(s) not explicitly supported by Jira story evidence.",
                icon="⚠️",
            )
        return cases
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
                cases, dropped = _drop_unstated_scenarios(cases, _story_evidence_text)
                st.warning(
                    f"⚠️ GPT response was truncated — recovered {len(cases)} of the generated "
                    "test cases. Consider re-generating or splitting into smaller stories.",
                    icon="⚠️",
                )
                if dropped:
                    st.warning(
                        f"⚠️ Removed {dropped} generated test case(s) not explicitly supported by Jira story evidence.",
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
        "You are a senior QA engineer following Kapost testing standards.\n"
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
        "Generate a unified, deduplicated, scenario-based test suite covering ALL of the following:\n"
        "1. Happy-path business scenarios across all stories\n"
        "2. Cross-story integration flows (where story A creates something story B uses)\n"
        "3. Negative / validation scenarios (invalid data, missing required fields, wrong format)\n"
        "4. Role-based access for the feature as a whole\n"
        "5. Edge cases: empty state, dependency deletion, concurrent edits, mid-flow reload\n"
        "6. Regression risk areas most likely to break if any story changes\n\n"
        "SCENARIO GROUPING RULES:\n"
        "- Group closely related UI checks into one test case when they share setup and workflow.\n"
        "- Do not create separate cases only for individual toolbar buttons, tooltips, or nearby formatting controls.\n"
        "- Keep separate cases only when workflows, preconditions, or failure reporting differ materially.\n"
        "- Preserve traceability by listing all covered AC items in coverage_refs for each case.\n"
        "- Target fewer, broader cases; for a medium feature, prefer roughly 10-15 strong cases over dozens of micro-cases.\n\n"
        "STRICT REALISM RULES:\n"
        "- Generate only scenarios explicitly supported by the provided stories (AC, STR, description, comments).\n"
        "- Do NOT invent test cases for network/API failure, server errors, timeouts, offline behavior, concurrency/race conditions, performance/load, or browser-compatibility unless explicitly mentioned in the stories.\n"
        "- If not explicitly described in stories, treat it as a QA question/gap, not a test case.\n\n"
        "AC TYPE CLASSIFICATION — apply this per-AC when deciding coverage:\n"
        "  TYPE A (Explicit functional): AC describes exact UI action and measurable outcome → cover in one or more scenario cases\n"
        "  TYPE B (Rule/constraint): AC describes a business rule, permission, or limit → cover via in-bounds + boundary/limit scenarios\n"
        "  TYPE C (Non-functional): AC covers error messages, performance, UX, or display only → group with the nearest relevant user scenario when practical\n"
        "You MUST ensure every AC item (AC-01 .. AC-N) is covered, but multiple AC items may map to the same scenario-based test case.\n\n"
        "Return ONLY a valid JSON array — no markdown fences, no explanation:\n"
        "[\n"
        "  {\n"
        f'    \"tc_id\":             \"{feature_prefix}-001\",\n'
        '    \"jira_ref\":          \"STUD-XXXX or General\",\n'
        '    \"title\":             \"[Scenario] verifies [Expected Outcome]\",\n'
        '    \"priority\":          \"Critical|High|Medium|Low\",\n'
        '    \"type\":              \"Functional|Regression|Smoke|Integration|Negative\",\n'
        '    \"preconditions\":     \"Role required, existing data state, feature flags if any\",\n'
        '    \"steps\":             \"1. First step\\\\n2. Second step\",\n'
        '    \"expected_result\":   \"Observable, verifiable outcome after all steps\",\n'
        '    \"test_data\":         \"CY_Test | specific values, or N/A\",\n'
        '    \"automation_status\": \"Automated|Manual|Candidate\",\n'
        '    \"roles_covered\":     [\"admin\"],\n'
        '    \"coverage_refs\":     [\"AC-01\", \"AC-02\"]\n'
        "  }\n"
        "]\n\n"
        "Rules:\n"
        f"- Sequential IDs: {feature_prefix}-001, {feature_prefix}-002, etc.\n"
        "- jira_ref: the story key this test primarily validates, or \"General\" for cross-story tests\n"
        "- Priority: Critical = core/data-loss flows, High = main flows, Medium = edge cases, Low = cosmetic\n"
        "- automation_status: \"Candidate\" for stable repeatable flows, \"Manual\" for exploratory, "
        "\"Automated\" for clear Cypress pattern matches\n"
        "- Always prefix test data with \"CY_Test |\"\n"
        "- coverage_refs must list every AC / edge / negative item materially covered by that case\n"
        "- Do not produce one-case-per-AC if multiple ACs belong to the same user scenario\n"
        "- Do NOT generate duplicate test cases across stories\n"
        "- ROLE SCOPING RULE:\n"
        "  Generate role-based tests ONLY IF:\n"
        "    - 1. Requirements mention permissions\n"
        "    - 2. Story mentions roles\n"
        "    - 3. Feature visibility differs by role\n"
        "    - 4. Existing behavior varies by role\n\n"
        "      Otherwise generate no role-specific tests.\n"
        "  Generate FULL additional role-specific flows ONLY when:\n"
        "    a) A story explicitly names a role (e.g. 'admin can...', 'editor should not...'), OR\n"
        "    b) The feature clearly behaves differently between the listed roles.\n"
        "  Do NOT duplicate the full happy-path flow per role — role cases must focus on access-control\n"
        "  boundaries (403 / permission denied / feature hidden). When in doubt, use admin for positive flows."
    )

    resp = client.chat.completions.create(
        model=st.session_state.selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    cases = json.loads(raw)
    cases, dropped = _drop_unstated_scenarios(cases, stories_block)
    if dropped:
        st.warning(
            f"⚠️ Removed {dropped} generated test case(s) not explicitly supported by Jira story evidence.",
            icon="⚠️",
        )
    return cases


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

        # Normalise step separators: GPT often encodes newlines as literal \n in
        # the JSON string value. json.loads() keeps them as the two-char sequence
        # "\n" rather than a real newline, so splitlines() sees one long line.
        raw_steps = raw_steps.replace("\\n", "\n")

        # P3-fix: parse "Step N: … \n  Expected: …" pairs and assign per-step
        # expected results instead of dumping everything on the last step.
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

        # Build plain-text steps string for sections using the "Test Case (Text)" template.
        # TestRail silently ignores custom_steps_separated when the section template is
        # "Test Case (Text)" — sending custom_steps as well ensures steps are always saved.
        plain_steps = "\n".join(
            f"{i}. {obj['content']}" + (f"\n   Expected: {obj['expected']}" if obj.get("expected") else "")
            for i, obj in enumerate(step_objs, 1)
        )

        payload = {
            "title":                  case["title"],
            "type_id":                2,
            "priority_id":            TESTRAIL_PRIORITY.get(case.get("priority", "Medium"), 2),
            "custom_preconds":        case.get("preconditions", ""),
            "custom_steps_separated": step_objs,   # for "Test Case (Steps)" template
            "custom_steps":           plain_steps,  # for "Test Case (Text)" template
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

# Initialize session state for model selection
if "selected_model" not in st.session_state:
    st.session_state.selected_model = OPENAI_MODEL
if "show_export_confirm" not in st.session_state:
    st.session_state.show_export_confirm = False
if "pending_export" not in st.session_state:
    st.session_state.pending_export = None

# Sidebar model selector
with st.sidebar:
    st.subheader("⚙️ Settings")
    st.session_state.selected_model = st.selectbox(
        "Select LLM Model",
        ["gpt-4o", "gpt-4-turbo"],
        index=0 if st.session_state.selected_model != "gpt-4-turbo" else 1,
        help="Choose which OpenAI model to use for test case generation",
    )
    st.divider()

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
                f"test suite with {st.session_state.selected_model}…"
            ):
                try:
                    _bulk_cypress = get_cypress_patterns(
                        " ".join(s["summary"] for s in bulk_stories)
                    )
                    _cases = generate_bulk_test_cases(
                        _stories_tuple, _ex_json, _bulk_cypress,
                        tuple(sorted(selected_roles)), feature_prefix,
                    )
                    with st.spinner("Refining generated feature suite to remove overlap and tighten expected results…"):
                        try:
                            _bulk_refinement_brief = {
                                "stories": [
                                    {
                                        "key": _d["key"],
                                        "summary": _d["summary"],
                                        "ac_list": _d.get("ac_list", []),
                                        "str_list": _d.get("str_list", []),
                                    }
                                    for _d in _loaded_stories.values()
                                ]
                            }
                            _cases = refine_generated_cases(
                                json.dumps(_cases, sort_keys=True),
                                json.dumps(_bulk_refinement_brief, sort_keys=True),
                                feature_prefix,
                            )
                        except Exception as _refine_err:
                            st.warning(f"Refinement step skipped: {_refine_err}")
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

                _bulk_pending_key = f"bulk_pending_export_{bulk_sig}"
                _n_sel = len(_all_selected)
                _col1, _col2 = st.columns([3, 1])
                with _col1:
                    _export_btn = st.button(
                        f"📤 Export {_n_sel} Case(s) to TestRail",
                        disabled=(_n_sel == 0),
                        type="primary",
                        key="bulk_export_btn",
                        use_container_width=True,
                    )
                if _export_btn:
                    st.session_state[_bulk_pending_key] = {
                        "selected_indices": list(_all_selected),
                        "suite_id": int(_suite_id),
                        "section_id": int(_sec_id),
                        "suite_label": _suite_label if _suites else f"Suite ID {_suite_id}",
                        "section_label": _sec_label if _suites and _sections else f"Section ID {_sec_id}",
                    }
                    st.rerun()

                _bulk_pending = st.session_state.get(_bulk_pending_key)
                if _bulk_pending:
                    with _col2:
                        st.warning(
                            f"⚠️ Export {len(_bulk_pending['selected_indices'])} case(s) to "
                            f"{_bulk_pending['suite_label']} / {_bulk_pending['section_label']}?"
                        )
                    _col_confirm_yes, _col_confirm_no = st.columns(2)
                    with _col_confirm_yes:
                        if st.button("✅ Yes, Export", type="primary", use_container_width=True, key="bulk_confirm_yes"):
                            _to_export = [
                                _get_edited(_bulk_generated[_i], f"bulk_edit_{bulk_sig}_{_i}")
                                for _i in _bulk_pending["selected_indices"]
                            ]
                            with st.spinner(f"Exporting {len(_to_export)} test case(s)…"):
                                _results = export_to_testrail(
                                    _to_export,
                                    _bulk_pending["suite_id"],
                                    _bulk_pending["section_id"],
                                )
                            st.session_state.pop(_bulk_pending_key, None)
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
                    with _col_confirm_no:
                        if st.button("❌ Cancel", use_container_width=True, key="bulk_confirm_no"):
                            st.session_state.pop(_bulk_pending_key, None)
                            st.info("Export cancelled.")

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
tab1, tab2, tab3, tab4 = st.tabs([
    "📄 Story Details & AC",
    "✅ Existing Test Cases",
    "🤖 Generate & Export",
    "💻 Generate Automation Code",
])

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

        # ── QA Intelligence: run Step 1 and surface ticket gaps ──────────────
        st.divider()
        with st.spinner("🔬 Analysing ticket quality…"):
            try:
                _ticket_type = "Bug" if any(
                    kw in selected["summary"].lower()
                    for kw in ("bug", "fix", "defect", "regression", "broken", "error", "fail")
                ) else "Story"
                _ticket = normalize_ticket(
                    selected["key"], selected["summary"], desc,
                    tuple(ac_list), tuple(str_list), "", _ticket_type,
                )
                _ticket_json = json.dumps(_ticket, sort_keys=True)
                _role_ctx    = get_role_context(selected["summary"], feature_prefix)
                _brief       = extract_requirements(_ticket_json, "", "", _role_ctx)
                st.session_state[f"brief_{selected['key']}"] = _brief
                st.session_state[f"story_feature_key_{selected['key']}"] = (
                    (_brief or {}).get("feature_key")
                    or (_ticket or {}).get("feature_key", "")
                )

                _qa_gaps = _brief.get("qa_gaps", [])
                if _qa_gaps:
                    with st.expander(
                        f"⚠️ QA Intelligence — {len(_qa_gaps)} ticket gap(s) detected",
                        expanded=True,
                    ):
                        st.caption(
                            "These are missing details a tester needs but the ticket doesn't provide. "
                            "Consider clarifying with the author before generating test cases."
                        )
                        for gap in _qa_gaps:
                            st.markdown(f"⚠️ {gap}")
                else:
                    st.success("✅ QA Intelligence — ticket looks complete, no obvious gaps detected.")

                _fr_count = len(_brief.get("functional_requirements", _ticket["requirements"]))
                _ec_count = len(_brief.get("edge_cases", []))
                _ns_count = len(_brief.get("negative_scenarios", []))
                _techs    = ", ".join(_brief.get("test_design_techniques", [])) or "—"
                with st.expander("📊 Requirements Brief (used for generation)", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Functional Requirements", _fr_count)
                    c2.metric("Edge Cases identified", _ec_count)
                    c3.metric("Negative Scenarios", _ns_count)
                    st.caption(f"**Test design techniques:** {_techs}")
                    if _brief.get("functional_requirements"):
                        st.markdown("**Functional Requirements:**")
                        for i, fr in enumerate(_brief["functional_requirements"], 1):
                            st.markdown(f"{i}. {fr}")
                    if _brief.get("edge_cases"):
                        st.markdown("**Edge Cases:**")
                        for i, ec in enumerate(_brief["edge_cases"], 1):
                            st.markdown(f"{i}. {ec}")
                    if _brief.get("negative_scenarios"):
                        st.markdown("**Negative Scenarios:**")
                        for i, ns in enumerate(_brief["negative_scenarios"], 1):
                            st.markdown(f"{i}. {ns}")
                    if _brief.get("validation_rules"):
                        st.markdown("**Validation Rules:**")
                        for i, vr in enumerate(_brief["validation_rules"], 1):
                            st.markdown(f"{i}. {vr}")
                    if _brief.get("api_interactions") and any(_brief["api_interactions"]):
                        st.markdown("**API / Integration Touch Points:**")
                        for api in _brief["api_interactions"]:
                            st.markdown(f"- {api}")
            except Exception as _e:
                st.caption(f"ℹ️ QA Intelligence analysis unavailable: {_e}")
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
    state_pk_chunks = f"product_ctx_chunks_{selected['key']}"
    state_pk_feature = f"product_ctx_feature_{selected['key']}"

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

    _pk_chunks = st.session_state.get(state_pk_chunks, [])
    _pk_feature = st.session_state.get(state_pk_feature, "")
    if _pk_chunks:
        with st.expander(
            f"📚 Product Knowledge Chunks Used (feature: {_pk_feature or 'unknown'})",
            expanded=False,
        ):
            for i, ch in enumerate(_pk_chunks, 1):
                st.markdown(f"**{i}. {ch.get('path', 'unknown')}**")
                st.code(ch.get("snippet", ""), language=None)

    if gen_clicked:
        content  = get_story_content(selected["key"], selected.get("content", ""))
        ac_list  = extract_acceptance_criteria(content)
        str_list = extract_steps_to_reproduce(content)
        desc     = extract_description(content)
        _live_cmt = fetch_jira_comments(selected["key"]) if include_comments else ""
        comments  = _live_cmt or (extract_comments(content) if include_comments else "")
        ex_tcs      = get_existing_test_cases(selected["key"], selected["summary"])
        cypress_ctx = get_cypress_patterns(selected["summary"])
        _story_feature_key = st.session_state.get(f"story_feature_key_{selected['key']}", "")
        _pk_extra = "\n".join([
            selected.get("summary", ""),
            desc or "",
            " ".join(ac_list[:8]),
            " ".join(str_list[:8]),
            comments[:600],
        ])
        _pk_bundle = get_product_knowledge_chunks(
            selected["summary"],
            feature_prefix,
            _pk_extra,
            forced_feature_key=_story_feature_key,
        )
        st.session_state[state_pk_chunks] = _pk_bundle.get("chunks", [])
        st.session_state[state_pk_feature] = _pk_bundle.get("feature_key", "")
        product_ctx = "\n\n".join(
            f"[{s.get('path', 'unknown')}]\n{s.get('snippet', '')}"
            for s in _pk_bundle.get("chunks", [])
        )
        with st.spinner(f"Step 2/3: Generating test cases with {st.session_state.selected_model}…"):
            try:
                cases = generate_test_cases(
                    selected["key"], selected["summary"],
                    desc,
                    tuple(ac_list), tuple(str_list),
                    comments,
                    cypress_ctx,
                    product_ctx,
                    tuple(json.dumps(t, sort_keys=True) for t in ex_tcs),
                    tuple(sorted(selected_roles)), feature_prefix,
                )
                with st.spinner("Step 3/4: Consolidating overlapping cases and tightening expected results…"):
                    try:
                        _brief_for_refinement = st.session_state.get(
                            f"brief_{selected['key']}",
                            {},
                        )

                        cases = refine_generated_cases(
                            json.dumps(cases, sort_keys=True),
                            json.dumps(_brief_for_refinement, sort_keys=True),
                            feature_prefix,
                        )
                    except Exception as _refine_err:
                        st.warning(f"Refinement step skipped: {_refine_err}")
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

                # ── Step 4: Self-critique pass ────────────────────────────
                with st.spinner("🔍 Running self-critique and scoring confidence…"):
                    try:
                        _brief_for_critique = st.session_state.get(f"brief_{selected['key']}", {})
                        _critique = critique_test_cases(
                            json.dumps(cases, sort_keys=True),
                            json.dumps(_brief_for_critique, sort_keys=True),
                        )
                        _dim_scores = {
                            k: float(_critique.get(k, 1) or 1)
                            for k in ("duplicate_score", "traceability_score",
                                      "expected_result_score", "realism_score")
                        }
                        _needs_second_pass = (
                            float(_critique.get("overall_score", 0) or 0) < 0.85
                            or any(v < 0.8 for v in _dim_scores.values())
                            or bool(_critique.get("missing_coverage"))
                            or bool(_critique.get("duplicate_pairs"))
                            or bool(_critique.get("improvement_suggestions"))
                        )

                        if _needs_second_pass:
                            with st.spinner("Step 4/4: Applying critique-driven refinement pass…"):
                                cases = refine_generated_cases(
                                    json.dumps(cases, sort_keys=True),
                                    json.dumps(_brief_for_critique, sort_keys=True),
                                    feature_prefix,
                                    json.dumps(_critique, sort_keys=True),
                                )
                            _critique = critique_test_cases(
                                json.dumps(cases, sort_keys=True),
                                json.dumps(_brief_for_critique, sort_keys=True),
                            )

                        st.session_state[f"critique_{selected['key']}"] = _critique

                        # Recompute near-duplicates after critique-driven refinement.
                        dup_indices = set()
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

                        st.session_state[state_sel] = [
                            i for i in range(len(cases)) if i not in dup_indices
                        ]

                        # Attach per-case scores back onto the case dicts
                        _score_map = {
                            s["tc_id"]: s
                            for s in _critique.get("case_scores", [])
                            if "tc_id" in s
                        }
                        for case in cases:
                            tc_id = case.get("tc_id", "")
                            if tc_id in _score_map:
                                case["_score"]        = _score_map[tc_id].get("score", None)
                                case["_score_reason"] = _score_map[tc_id].get("reason", "")
                        st.session_state[state_cases] = cases
                    except Exception:
                        pass  # critique is optional — don't block generation
            except Exception as e:
                st.error(f"Generation failed: {e}")

    generated = st.session_state[state_cases]

    if generated:
        # ── Critique / coverage summary banner ───────────────────────────────
        _critique = st.session_state.get(f"critique_{selected['key']}")
        if _critique:
            _overall  = _critique.get("overall_score", 0)
            _reason   = _critique.get("overall_reason", "")
            _missing  = _critique.get("missing_coverage", [])
            _dups     = _critique.get("duplicate_pairs", [])
            _suggests = _critique.get("improvement_suggestions", [])
            _score_pct = int(_overall * 100)
            _score_emoji = "🟢" if _overall >= 0.80 else "🟡" if _overall >= 0.60 else "🔴"
            st.info(
                f"{_score_emoji} **Coverage Score: {_score_pct}/100** — {_reason}",
                icon="📊",
            )
            if _missing or _dups or _suggests:
                with st.expander(
                    f"🔍 Self-Critique — "
                    f"{len(_missing)} gap(s), {len(_dups)} duplicate pair(s), "
                    f"{len(_suggests)} suggestion(s)",
                    expanded=(_overall < 0.80),
                ):
                    if _missing:
                        st.markdown("**Missing Coverage:**")
                        for m in _missing:
                            st.markdown(f"⚠️ {m}")
                    if _dups:
                        st.markdown("**Potential Duplicate Pairs:**")
                        for pair in _dups:
                            st.markdown(f"🔁 {' ↔ '.join(pair)}")
                    if _suggests:
                        st.markdown("**Improvement Suggestions:**")
                        for s in _suggests:
                            st.markdown(f"💡 {s}")

        st.subheader(f"Generated {len(generated)} Test Case(s)")
        st.caption("Select cases to review and export to TestRail:")

        selected_indices = []
        for i, tc in enumerate(generated):
            pri  = tc.get("priority", "Medium")
            typ  = tc.get("type", "Functional")
            auto = tc.get("automation_status", "Manual")

            _score = tc.get("_score")
            _score_badge = (
                f"  |  {'🟢' if _score >= 0.8 else '🟡' if _score >= 0.6 else '🔴'} {int(_score*100)}"
                if _score is not None else ""
            )
            _dup_tag = " ⚠️ NEAR-DUPLICATE" if tc.get("_duplicate_of") else ""
            checked = st.checkbox(
                f"**[{tc.get('tc_id', f'{feature_prefix}-{i+1:03d}')}]** "
                f"{PRIORITY_MAP.get(pri, '')} {pri}  |  "
                f"{TYPE_MAP.get(typ, '')} {typ}  |  "
                f"🤖 {auto}{_score_badge}  —  {tc['title']}{_dup_tag}",
                value=(i in st.session_state[state_sel]),
                key=f"chk_{selected['key']}_{i}",
            )
            if checked:
                selected_indices.append(i)

            with st.expander("✏️ Edit Details", expanded=False):
                if _score is not None:
                        st.caption(f"**Confidence:** {'🟢' if _score >= 0.8 else '🟡' if _score >= 0.6 else '🔴'} {int(_score*100)}/100 — {tc.get('_score_reason', '')}")
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

            pending_export_key = f"pending_export_{selected['key']}"
            n_selected = len(selected_indices)
            col1, col2 = st.columns([3, 1])
            with col1:
                export_btn = st.button(
                    f"📤 Export {n_selected} Case(s) to TestRail",
                    disabled=(n_selected == 0),
                    type="primary",
                    use_container_width=True,
                )
            if export_btn:
                st.session_state[pending_export_key] = {
                    "selected_indices": list(selected_indices),
                    "suite_id": int(suite_id),
                    "section_id": int(section_id),
                    "suite_label": suite_label if suites else f"Suite ID {suite_id}",
                    "section_label": section_label if suites and sections else f"Section ID {section_id}",
                }
                st.rerun()

            pending_export = st.session_state.get(pending_export_key)
            if pending_export:
                with col2:
                    st.warning(
                        f"⚠️ Export {len(pending_export['selected_indices'])} case(s) to "
                        f"{pending_export['suite_label']} / {pending_export['section_label']}?"
                    )
                col_confirm_yes, col_confirm_no = st.columns(2)
                with col_confirm_yes:
                    if st.button("✅ Yes, Export", type="primary", use_container_width=True):
                        cases_to_export = [
                            _get_edited(generated[i], f"edit_{selected['key']}_{i}")
                            for i in pending_export["selected_indices"]
                        ]
                        with st.spinner(f"Exporting {len(cases_to_export)} test case(s)…"):
                            results = export_to_testrail(
                                cases_to_export,
                                pending_export["suite_id"],
                                pending_export["section_id"],
                            )
                        st.session_state.pop(pending_export_key, None)

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
                with col_confirm_no:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.pop(pending_export_key, None)
                        st.info("Export cancelled.")
    else:
        st.info("Click **Generate Test Cases** to analyse coverage gaps and generate structured test cases for this story.")


# ── Tab 4: Generate Automation Code ─────────────────────────────────────────
with tab4:
    st.subheader("💻 Generate Automation Code")
    st.caption(
        "Generate Cypress automation artifacts from selected generated test cases. "
        "Output is grounded in RAG context and automation guidelines."
    )

    state_cases = f"gen_cases_{selected['key']}"
    state_auto_sel = f"auto_sel_idx_{selected['key']}"
    state_auto_out = f"auto_codegen_{selected['key']}"
    state_auto_feature_chunks = f"auto_feature_ctx_chunks_{selected['key']}"
    state_auto_feature_key = f"auto_feature_key_{selected['key']}"
    generated = st.session_state.get(state_cases, [])

    if state_auto_sel not in st.session_state:
        st.session_state[state_auto_sel] = []
    if state_auto_out not in st.session_state:
        st.session_state[state_auto_out] = {}

    if not generated:
        st.info("Generate test cases in the Generate & Export tab first, then select cases here for automation code generation.")
    else:
        st.markdown("**Select generated test cases as automation input:**")

        selected_auto_indices = []
        for i, tc in enumerate(generated):
            _label = (
                f"[{tc.get('tc_id', f'{feature_prefix}-{i+1:03d}')}] "
                f"{tc.get('title', '')}"
            )
            checked = st.checkbox(
                _label,
                value=(i in st.session_state[state_auto_sel]),
                key=f"auto_chk_{selected['key']}_{i}",
            )
            if checked:
                selected_auto_indices.append(i)

        st.session_state[state_auto_sel] = selected_auto_indices

        col_gen, col_clear = st.columns([3, 1])
        with col_gen:
            auto_gen_clicked = st.button(
                f"💻 Generate Automation Code ({len(selected_auto_indices)} selected)",
                type="primary",
                disabled=(len(selected_auto_indices) == 0),
                use_container_width=True,
            )
        with col_clear:
            if st.button("🗑️ Clear Output", use_container_width=True):
                st.session_state[state_auto_out] = {}

        _af_chunks = st.session_state.get(state_auto_feature_chunks, [])
        _af_key = st.session_state.get(state_auto_feature_key, "")
        if _af_chunks:
            with st.expander(
                f"📚 Automation Feature Context Chunks Used (feature: {_af_key or 'unknown'})",
                expanded=False,
            ):
                for i, ch in enumerate(_af_chunks, 1):
                    st.markdown(f"**{i}. {ch.get('path', 'unknown')}**")
                    st.code(ch.get("snippet", ""), language=None)
        else:
            st.caption("ℹ️ No feature-context chunks found for this run yet.")

        if auto_gen_clicked:
            selected_cases = [
                _get_edited(generated[i], f"edit_{selected['key']}_{i}")
                for i in selected_auto_indices
            ]
            selected_cases_json = json.dumps(selected_cases, sort_keys=True)
            case_titles = tuple(tc.get("title", "") for tc in selected_cases if tc.get("title"))
            _case_context_text = "\n".join(
                f"title={tc.get('title', '')}; pre={tc.get('preconditions', '')}; "
                f"steps={tc.get('steps', '')}; expected={tc.get('expected_result', '')}"
                for tc in selected_cases
            )
            _story_feature_key = st.session_state.get(f"story_feature_key_{selected['key']}", "")

            with st.spinner("Loading automation guidelines and RAG framework context…"):
                guidelines = load_automation_guidelines()
                automation_context = get_automation_context(
                    selected["summary"],
                    case_titles,
                    feature_prefix,
                    _case_context_text,
                    forced_feature_key=_story_feature_key,
                )
                st.session_state[state_auto_feature_chunks] = automation_context.get("feature_context", [])
                st.session_state[state_auto_feature_key] = automation_context.get("feature_key", "")

            if not guidelines:
                st.error("Could not load automation guidelines. Ensure rag/docs/automation/automation-guidelines.md exists.")
            else:
                with st.spinner(f"Generating Cypress artifacts with {st.session_state.selected_model}…"):
                    try:
                        auto_payload = generate_automation_code(
                            selected["key"],
                            selected["summary"],
                            feature_prefix,
                            selected_cases_json,
                            json.dumps(automation_context, sort_keys=True),
                            guidelines,
                        )
                        auto_payload["_meta"] = {
                            "selected_case_count": len(selected_cases),
                            "selected_case_ids": [
                                tc.get("tc_id", "") for tc in selected_cases
                            ],
                        }
                        st.session_state[state_auto_out] = auto_payload
                    except Exception as e:
                        st.error(f"Automation code generation failed: {e}")

        auto_out = st.session_state.get(state_auto_out, {})
        if auto_out:
            spec_file = auto_out.get("spec_file", {}) or {}
            po_updates = auto_out.get("page_object_updates", []) or []
            cmd_suggestions = auto_out.get("command_suggestions", []) or []
            grounding = auto_out.get("grounding_evidence", []) or []
            fc_applied = auto_out.get("feature_context_application", []) or []
            spec_style = auto_out.get("similar_spec_style_guide", {}) or {}

            st.divider()
            with st.expander("🧭 Similar Spec Style Guide Used", expanded=False):
                _rules = spec_style.get("style_rules", []) or []
                _reuse = spec_style.get("must_reuse_patterns", []) or []
                _cautions = spec_style.get("cautions", []) or []
                if _rules:
                    st.markdown("**Style Rules**")
                    for r in _rules:
                        st.markdown(f"- {r}")
                if _reuse:
                    st.markdown("**Must-Reuse Patterns**")
                    for p in _reuse:
                        st.markdown(f"- {p}")
                if _cautions:
                    st.markdown("**Cautions**")
                    for c in _cautions:
                        st.markdown(f"- {c}")
                if not (_rules or _reuse or _cautions):
                    st.caption("No style guide extracted from similar specs for this run.")

            st.divider()
            st.markdown("**Generated Spec File**")
            _spec_path = spec_file.get("path", "cypress/e2e/generated/generated.spec.cy.js")
            _spec_content = spec_file.get("content", "")
            st.text_input("Spec Path", value=_spec_path, key=f"auto_spec_path_{selected['key']}")
            st.code(_spec_content or "", language="javascript")
            st.download_button(
                "⬇️ Download Spec",
                data=_spec_content or "",
                file_name=os.path.basename(_spec_path) or "generated.spec.cy.js",
                mime="text/plain",
                use_container_width=True,
            )

            st.divider()
            st.markdown("**Page Object Updates**")
            if po_updates:
                for i, upd in enumerate(po_updates, 1):
                    with st.expander(f"{i}. {upd.get('path', 'Page Object')}", expanded=False):
                        st.caption(upd.get("summary", ""))
                        st.code(upd.get("patch", ""), language="diff")
            else:
                st.caption("No page object updates suggested.")

            st.divider()
            st.markdown("**Custom Command Suggestions**")
            if cmd_suggestions:
                for i, cmd in enumerate(cmd_suggestions, 1):
                    with st.expander(f"{i}. cy.{cmd.get('command', 'newCommand')}", expanded=False):
                        st.caption(cmd.get("rationale", ""))
                        st.code(cmd.get("sample", ""), language="javascript")
            else:
                st.caption("No custom command additions suggested.")

            if grounding:
                st.divider()
                with st.expander("🔎 Grounding Evidence", expanded=False):
                    for item in grounding:
                        st.markdown(
                            f"- **{item.get('artifact', 'artifact')}** from `{item.get('source_path', 'unknown')}`: "
                            f"{item.get('reason', '')}"
                        )

            st.divider()
            st.markdown("**📚 Feature Context Utilization Review**")
            if fc_applied:
                for i, item in enumerate(fc_applied, 1):
                    st.markdown(
                        f"{i}. **{item.get('context_item', 'Context item')}**\n"
                        f"   - Applied In: {item.get('applied_in', 'N/A')}\n"
                        f"   - Note: {item.get('note', '')}"
                    )
            else:
                st.caption("No feature-context utilization mapping returned.")

