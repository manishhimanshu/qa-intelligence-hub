"""MCP server exposing QA Intelligence Hub context and guarded artifact tools to Copilot CLI.

Copilot's model does the analysis and generation; stdout is reserved for MCP transport.
"""
import json
import logging
import os
import sys
import uuid
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from core.automation import (  # noqa: E402
    AutomationError,
    build_automation_context,
    build_testrail_automation_context,
    create_spec_file,
    create_testrail_spec_file,
    save_cypress_preview as _save_cypress_preview,
    _sanitize_source,
)
from core import config, jira_client, retrieval  # noqa: E402
from core.markdown import render_gap_analysis, render_test_cases  # noqa: E402
from core.schemas import (  # noqa: E402
    GAP_SECTIONS,
    GapAnalysis,
    TestCaseSuite,
    check_source_evidence,
    check_traceability,
    find_exact_duplicates,
    unsupported_categories,
)
from core.story_context import build_story_context, evidence_text  # noqa: E402
from core.testrail_client import TestRailError  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
log = logging.getLogger("qa-hub-mcp")

mcp = FastMCP("qa-intelligence-hub")

_context_cache: dict[str, dict] = {}
_story_context_cache: OrderedDict[str, dict] = OrderedDict()
_STORY_CONTEXT_CACHE_LIMIT = 8
_STORY_CONTEXT_FOLLOWUP_LIMIT = 2
_STORY_CONTEXT_PAGE_SIZE = 2
_story_context_followup_calls: dict[str, dict[str, int]] = {}
_automation_context_cache: OrderedDict[str, dict] = OrderedDict()
_AUTOMATION_CONTEXT_CACHE_LIMIT = 8
_AUTOMATION_FILE_CHUNK_FOLLOWUP_LIMIT = 2
_automation_file_chunk_followups: dict[str, dict[str, int]] = {}
_AUTOMATION_CONTEXT_SECTIONS = (
    "test_case",
    "general_guidelines",
    "feature_context",
    "product_knowledge",
    "role_permissions",
    "existing_specs",
    "page_objects",
    "custom_commands",
    "data_helpers",
    "automation_scope",
)


def _context(key: str) -> dict:
    if key not in _context_cache:
        _context_cache[key] = build_story_context(key)
    return _context_cache[key]


def _write(path: Path, content: str) -> str:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _error(message: str) -> dict:
    return {"ok": False, "error": message}


def _cache_automation_context(context: dict) -> str:
    context_id = uuid.uuid4().hex
    _automation_context_cache[context_id] = context
    _automation_context_cache.move_to_end(context_id)
    _automation_file_chunk_followups[context_id] = {}
    while len(_automation_context_cache) > _AUTOMATION_CONTEXT_CACHE_LIMIT:
        expired_id, _ = _automation_context_cache.popitem(last=False)
        _automation_file_chunk_followups.pop(expired_id, None)
    return context_id


def _cache_story_context(context: dict) -> str:
    context_id = uuid.uuid4().hex
    _story_context_cache[context_id] = deepcopy(context)
    _story_context_cache.move_to_end(context_id)
    _story_context_followup_calls[context_id] = {}
    while len(_story_context_cache) > _STORY_CONTEXT_CACHE_LIMIT:
        expired_id, _ = _story_context_cache.popitem(last=False)
        _story_context_followup_calls.pop(expired_id, None)
    return context_id


def _automation_context_sections(context: dict) -> dict:
    return {
        "test_case": context.get("selected_test_cases", []),
        "general_guidelines": context.get("general_guidelines", ""),
        "feature_context": context.get("feature_context", ""),
        "product_knowledge": context.get("product_knowledge", []),
        "role_permissions": context.get("role_permissions", ""),
        "existing_specs": context.get("existing_specs", []),
        "page_objects": context.get("page_objects", []),
        "custom_commands": context.get("custom_commands", []),
        "data_helpers": context.get("data_helpers", []),
        "automation_scope": context.get("automation_scope", []),
    }


def _automation_context_manifest(context: dict) -> dict:
    manifest = {}
    for name, value in _automation_context_sections(context).items():
        if isinstance(value, str):
            manifest[name] = {"kind": "text", "characters": len(value)}
        else:
            manifest[name] = {
                "kind": "items",
                "count": len(value),
                "characters": sum(len(json.dumps(item, ensure_ascii=False)) for item in value),
            }
    return manifest


def _read_automation_context_page(
    context_id: str, section: str, offset: int = 0, limit: int = 2, max_chars: int = 1800
) -> dict:
    context = _automation_context_cache.get(context_id)
    if context is None:
        return _error("Automation context expired or is unknown. Fetch automation context again.")
    if section not in _AUTOMATION_CONTEXT_SECTIONS:
        return _error(f"Unknown context section. Allowed: {', '.join(_AUTOMATION_CONTEXT_SECTIONS)}")
    if offset < 0:
        return _error("offset must be zero or greater.")

    value = _automation_context_sections(context)[section]
    if isinstance(value, str):
        page_size = min(max(int(max_chars), 1), 1800)
        page = value[offset:offset + page_size]
        next_offset = offset + len(page) if offset + len(page) < len(value) else None
        result = {
            "section": section,
            "offset": offset,
            "content": page,
            "total_characters": len(value),
            "next_offset": next_offset,
        }
    else:
        page_size = min(max(int(limit), 1), 2)
        page = value[offset:offset + page_size]
        next_offset = offset + len(page) if offset + len(page) < len(value) else None
        result = {
            "section": section,
            "offset": offset,
            "items": page,
            "total_items": len(value),
            "next_offset": next_offset,
        }
    _automation_context_cache.move_to_end(context_id)
    return {"ok": True, **result}


@mcp.tool()
def check_setup() -> dict:
    """Check configuration, the FAISS index and Jira connectivity. Never returns credential values."""
    status = {
        "jira_configured": bool(config.JIRA_URL and config.JIRA_USER and config.JIRA_TOKEN),
        "faiss_index_present": (config.FAISS_INDEX_DIR / "index.faiss").exists(),
        "feature_aliases_present": config.FEATURE_ALIASES_PATH.exists(),
        "automation_repo_configured": bool(
            config.AUTOMATION_REPO_ROOT and config.AUTOMATION_REPO_ROOT.is_dir()
        ),
        "testrail_configured": bool(
            config.TESTRAIL_URL and config.TESTRAIL_USER and config.TESTRAIL_TOKEN
        ),
        "output_dir": str(config.OUTPUT_DIR),
    }
    try:
        ac_id, str_id = jira_client.get_field_ids()
        status["jira_reachable"] = True
        status["acceptance_criteria_field_found"] = bool(ac_id)
        status["steps_to_reproduce_field_found"] = bool(str_id)
    except jira_client.JiraError as e:
        status["jira_reachable"] = False
        status["jira_error"] = str(e)
    return status


@mcp.tool()
def get_story_context(issue_key: str, refresh: bool = False) -> dict:
    """Fetch a Jira story plus feature-scoped product knowledge, role permissions and related
    existing TestRail cases. Call this first for any analysis or test generation. Returns a
    context_id for optional bounded follow-up with get_more_story_context."""
    try:
        key = config.validate_issue_key(issue_key)
        if refresh:
            _context_cache.pop(key, None)
        context = _context(key)
        context_id = _cache_story_context(context)
        return {"ok": True, "context_id": context_id, **context}
    except (ValueError, jira_client.JiraError, retrieval.RetrievalError) as e:
        return _error(str(e))


@mcp.tool()
def get_more_story_context(context_id: str, source: str) -> dict:
    """Fetch the next bounded batch from one supporting source in a Jira story context.
    Sources: product_knowledge, automation_context, qa_guidance, existing_testrail_cases.
    At most two follow-up pages of two items are available per source."""
    context = _story_context_cache.get(context_id)
    if context is None:
        return _error("Story context expired or is unknown. Call get_story_context again.")
    _story_context_cache.move_to_end(context_id)
    source = str(source or "").strip().lower()
    allowed_sources = {
        "product_knowledge", "automation_context", "qa_guidance", "existing_testrail_cases"
    }
    if source not in allowed_sources:
        return _error(f"Unsupported source. Choose one of: {', '.join(sorted(allowed_sources))}.")

    followups = _story_context_followup_calls.setdefault(context_id, {})
    used = followups.get(source, 0)
    if used >= _STORY_CONTEXT_FOLLOWUP_LIMIT:
        return _error(
            f"Follow-up limit reached for {source}: at most "
            f"{_STORY_CONTEXT_FOLLOWUP_LIMIT} additional pages per source."
        )

    story = context.get("story", {})
    source_text = context.get("source_text", {})
    summary = str(story.get("summary", ""))
    evidence = " ".join(
        str(source_text.get(field, ""))
        for field in ("description", "acceptance_criteria", "steps_to_reproduce")
    )
    feature_key = str(story.get("feature_key", ""))
    offset = len(context.get(source, []))
    try:
        if source == "product_knowledge":
            items = retrieval.get_product_knowledge(
                feature_key, summary, evidence, top_k=_STORY_CONTEXT_PAGE_SIZE, offset=offset
            )
        elif source == "automation_context":
            items = retrieval.get_automation_feature_context(
                feature_key, summary, evidence, top_k=_STORY_CONTEXT_PAGE_SIZE, offset=offset
            )
        elif source == "qa_guidance":
            items = retrieval.get_qa_guidance(
                summary, evidence, top_k=_STORY_CONTEXT_PAGE_SIZE, offset=offset
            )
        else:
            items = retrieval.get_existing_testrail_cases(
                str(story.get("key", "")), summary, feature_key,
                top_k=_STORY_CONTEXT_PAGE_SIZE, offset=offset,
            )
    except retrieval.RetrievalError as e:
        return _error(str(e))

    followups[source] = used + 1
    context.setdefault(source, []).extend(items)
    source_role = (
        "Use only for duplicate detection or as examples of coverage for Jira-supported behavior."
        if source == "existing_testrail_cases"
        else "Supporting context only; do not treat this source as a Jira requirement."
    )
    return {
        "ok": True,
        "source": source,
        "offset": offset,
        "items": items,
        "may_have_more": len(items) == _STORY_CONTEXT_PAGE_SIZE,
        "followup_pages_remaining": _STORY_CONTEXT_FOLLOWUP_LIMIT - used - 1,
        "source_role": source_role,
    }


@mcp.tool()
def get_epic_children(epic_key: str) -> dict:
    """List the child issues of a Jira epic (key, summary, status, type)."""
    try:
        key = config.validate_issue_key(epic_key)
        children = jira_client.fetch_epic_children(key)
        return {"ok": True, "epic": key, "count": len(children), "children": children}
    except (ValueError, jira_client.JiraError) as e:
        return _error(str(e))


@mcp.tool()
def get_automation_context(issue_key: str, case_ids: list[str] | None = None) -> dict:
    """Prepare selected saved manual cases for Cypress generation with feature docs and real repository patterns.
    With no case_ids, returns available saved cases for user selection. Otherwise returns the
    feature-approved spec directory and exact-path FAISS chunks for selected specs, page objects,
    shared commands, and helpers. Raw repository source is not included as an index fallback."""
    try:
        key = config.validate_issue_key(issue_key)
        context = _context(key)
        automation_context = build_automation_context(key, context, case_ids or [])
        if not case_ids:
            return {"ok": True, **automation_context}

        context_id = _cache_automation_context(automation_context)
        return {
            "ok": True,
            "context_id": context_id,
            "issue_key": key,
            "story": automation_context["story"],
            "target_spec_directory": automation_context["target_spec_directory"],
            "sections": _automation_context_manifest(automation_context),
            "page_tool": "get_automation_context_page",
            "limits": {"max_items_per_page": 2, "max_text_chars_per_page": 1800},
        }
    except (ValueError, jira_client.JiraError, retrieval.RetrievalError, AutomationError) as e:
        return _error(str(e))


@mcp.tool()
def create_cypress_spec(
    issue_key: str,
    filename: str,
    content: str,
    case_ids: list[str],
    user_approved: bool = False,
) -> dict:
    """Create a NEW Cypress spec in the feature's mapped folder only after the user approves its preview.
    Existing files are never overwritten; Page Objects and custom commands are never modified."""
    try:
        key = config.validate_issue_key(issue_key)
        context = _context(key)
        feature_key = context["story"].get("feature_key", "")
        if not feature_key:
            return _error("No feature key was resolved; refusing to choose a Cypress destination.")
        return create_spec_file(
            key, feature_key, filename, content, case_ids, user_approved
        )
    except (ValueError, jira_client.JiraError, retrieval.RetrievalError, AutomationError) as e:
        return _error(str(e))


@mcp.tool()
def get_testrail_automation_context(case_id: str, feature_key: str = "") -> dict:
    """Fetch a TestRail case and prepare a paged Cypress context. Returns a small manifest/context_id;
    call get_testrail_automation_context_page to retrieve bounded sections. Feature ambiguity fails closed.
    Cypress code sections contain only exact-path FAISS chunks. An optional feature_key must be known and consistent."""
    try:
        context = build_testrail_automation_context(case_id, feature_key)
        context_id = _cache_automation_context(context)
        return {
            "ok": True,
            "context_id": context_id,
            "source_kind": "testrail",
            "source_case": context["source_case"],
            "story": context["story"],
            "target_spec_directory": context["target_spec_directory"],
            "warnings": context["warnings"],
            "sections": _automation_context_manifest(context),
            "page_tool": "get_testrail_automation_context_page",
            "limits": {"max_items_per_page": 2, "max_text_chars_per_page": 1800},
        }
    except (AutomationError, TestRailError) as e:
        return _error(str(e))


@mcp.tool()
def get_automation_file_chunks(context_id: str, file_path: str) -> dict:
    """Fetch up to two more indexed Cypress chunks from one exact file in this automation context.
    Only paths already returned by the context are allowed; at most two follow-up pages per file."""
    context = _automation_context_cache.get(context_id)
    if context is None:
        return _error("Automation context expired or is unknown. Fetch automation context again.")

    requested = str(file_path or "").strip().replace("\\", "/").lower()
    groups = ("existing_specs", "page_objects", "custom_commands", "data_helpers")
    path_items = [
        (section, item)
        for section in groups
        for item in context.get(section, [])
        if str(item.get("path", "")).replace("\\", "/").lower() == requested
    ]
    if not requested or not path_items:
        return _error("file_path must exactly match a file already included in this automation context.")

    followups = _automation_file_chunk_followups.setdefault(context_id, {})
    used = followups.get(requested, 0)
    if used >= _AUTOMATION_FILE_CHUNK_FOLLOWUP_LIMIT:
        return _error(
            f"Follow-up limit reached for {file_path}: at most "
            f"{_AUTOMATION_FILE_CHUNK_FOLLOWUP_LIMIT} additional pages per file."
        )
    if not config.AUTOMATION_REPO_ROOT or not config.AUTOMATION_REPO_ROOT.is_dir():
        return _error("AUTOMATION_REPO_ROOT is not configured to an existing Cypress repository.")

    seen_ids = {
        str(item.get("chunk_id", ""))
        for section in groups
        for item in context.get(section, [])
        if str(item.get("path", "")).replace("\\", "/").lower() == requested
        and item.get("chunk_id")
    }
    canonical_path = str(path_items[0][1]["path"])
    try:
        result = retrieval.get_indexed_cypress_file_chunks(
            config.AUTOMATION_REPO_ROOT,
            canonical_path,
            exclude_chunk_ids=sorted(seen_ids),
            limit=2,
        )
    except retrieval.RetrievalError as e:
        return _error(str(e))

    followups[requested] = used + 1
    chunks = [{
        "path": chunk["path"],
        "chunk_id": chunk["id"],
        "type": chunk["type"],
        "content": _sanitize_source(chunk["snippet"]),
        "relevance_score": chunk["relevance_score"],
        "retrieval_source": "faiss-exact-repo-path-followup",
    } for chunk in result["chunks"]]
    context[path_items[0][0]].extend(chunks)
    return {
        "ok": True,
        "file_path": canonical_path,
        "chunks": chunks,
        "total_chunks": result["total_chunks"],
        "has_more": result["remaining_chunks"] > len(chunks),
        "followup_pages_remaining": _AUTOMATION_FILE_CHUNK_FOLLOWUP_LIMIT - used - 1,
    }


@mcp.tool()
def get_automation_context_page(
    context_id: str,
    section: str,
    offset: int = 0,
    limit: int = 2,
    max_chars: int = 1800,
) -> dict:
    """Read one bounded page from a Jira or TestRail automation context manifest.
    List sections return up to 2 items; text sections return up to 1800 characters."""
    return _read_automation_context_page(context_id, section, offset, limit, max_chars)


@mcp.tool()
def get_testrail_automation_context_page(
    context_id: str,
    section: str,
    offset: int = 0,
    limit: int = 2,
    max_chars: int = 1800,
) -> dict:
    """Compatibility alias for paging TestRail automation-context manifests."""
    return _read_automation_context_page(context_id, section, offset, limit, max_chars)


@mcp.tool()
def create_cypress_spec_from_testrail(
    case_id: str,
    filename: str,
    content: str,
    user_approved: bool = False,
    feature_key: str = "",
) -> dict:
    """Create a new Cypress spec sourced from a live TestRail case after explicit user approval.
    The source case ID must appear in the spec. Existing files are never overwritten."""
    try:
        return create_testrail_spec_file(
            case_id, filename, content, user_approved, feature_key
        )
    except (AutomationError, TestRailError) as e:
        return _error(str(e))


@mcp.tool()
def save_cypress_preview(
    source_type: str,
    source_id: str,
    filename: str,
    content: str,
    case_ids: list[str],
    user_approved: bool = False,
    feature_key: str = "",
) -> dict:
    """Save an approved Cypress preview to qa-copilot-cli/output/automation/ without changing the external Cypress repo.
    Supports source_type 'jira' with generated test case IDs or 'testrail' with the live TestRail case ID."""
    return _save_cypress_preview(
        source_type, source_id, filename, content, case_ids, user_approved, feature_key
    )


@mcp.tool()
def save_gap_analysis(issue_key: str, analysis: GapAnalysis) -> dict:
    """Save a Markdown analysis and flag unsupported scenario categories for human review."""
    try:
        key = config.validate_issue_key(issue_key)
        ctx = _context(key)
    except (ValueError, jira_client.JiraError, retrieval.RetrievalError) as e:
        return _error(str(e))

    evidence = evidence_text(ctx)
    grounding_flags = []
    for _, field in GAP_SECTIONS + [("PO Questions", "po_questions")]:
        for item in getattr(analysis, field):
            categories = unsupported_categories(item, evidence)
            if categories:
                grounding_flags.append({"section": field, "item": item, "categories": categories})

    path = _write(
        config.OUTPUT_DIR / f"{key}-analysis.md",
        render_gap_analysis(ctx["story"], analysis, grounding_flags),
    )
    return {
        "ok": True,
        "markdown_path": path,
        "grounding_review_flags": grounding_flags,
    }


@mcp.tool()
def save_test_cases(issue_key: str, suite: TestCaseSuite) -> dict:
    """Validate generated test cases (schema, traceability, realism guard) and save JSON + Markdown.
    Returns ok=false with errors to fix instead of saving when traceability is broken."""
    try:
        key = config.validate_issue_key(issue_key)
        ctx = _context(key)
    except (ValueError, jira_client.JiraError, retrieval.RetrievalError) as e:
        return _error(str(e))

    evidence = evidence_text(ctx)
    grounding_flags = []
    for tc in suite.test_cases:
        text = "\n".join([tc.title, tc.preconditions, tc.steps, tc.expected_result])
        categories = unsupported_categories(text, evidence)
        if categories:
            grounding_flags.append({"tc_id": tc.tc_id, "title": tc.title, "categories": categories})

    errors, warnings = check_traceability(suite, ctx["story"]["primary_source"])
    errors.extend(check_source_evidence(
        suite,
        ctx["story"]["primary_source"],
        ctx.get("source_text", {}),
    ))
    if errors:
        return {"ok": False, "errors": errors, "hint": "Fix these and call save_test_cases again."}

    duplicate_candidates = find_exact_duplicates(
        suite.test_cases, ctx.get("existing_testrail_cases", [])
    )

    payload = {
        "source": "copilot-cli",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "story": ctx["story"],
        **suite.model_dump(),
        "traceability_warnings": warnings,
        "grounding_review_flags": grounding_flags,
        "exact_duplicate_candidates": duplicate_candidates,
    }
    json_path = _write(config.OUTPUT_DIR / f"{key}-test-cases.json", json.dumps(payload, indent=2))
    md_path = _write(
        config.OUTPUT_DIR / f"{key}-test-cases.md",
        render_test_cases(ctx["story"], suite, warnings, grounding_flags, duplicate_candidates),
    )
    return {
        "ok": True,
        "markdown_path": md_path,
        "json_path": json_path,
        "test_case_count": len(suite.test_cases),
        "traceability_warnings": warnings,
        "grounding_review_flags": grounding_flags,
        "exact_duplicate_candidates": duplicate_candidates,
    }


if __name__ == "__main__":
    # On Windows, numpy/torch imports deadlock once the stdio reader thread holds stdin,
    # so load and exercise the whole retrieval path before mcp.run().
    try:
        retrieval.search("warm up", top_k=1)
    except retrieval.RetrievalError as e:
        log.warning("Retrieval unavailable: %s", e)
    mcp.run()
