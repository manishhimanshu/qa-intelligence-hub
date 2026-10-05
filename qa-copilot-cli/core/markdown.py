from datetime import datetime

from .schemas import GAP_SECTIONS, GapAnalysis, TestCaseSuite


def _bullets(items: list[str], empty: str = "*None.*") -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def _numbered(tag: str, items: list[str]) -> str:
    return "\n".join(f"- **{tag}-{i:02d}:** {v}" for i, v in enumerate(items, 1)) if items else "*None.*"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def render_test_cases(
    story: dict,
    suite: TestCaseSuite,
    warnings: list[str],
    grounding_flags: list[dict],
    duplicate_candidates: list[dict] | None = None,
) -> str:
    brief, critique = suite.requirements_brief, suite.critique
    duplicate_candidates = duplicate_candidates or []
    req_tag = "SC" if story.get("primary_source") == "str" else "FR"
    out = [
        f"# Test Cases: {story['key']} — {story['summary']}",
        "",
        f"*Generated {_timestamp()} via Copilot CLI · Feature: `{story.get('feature_key') or 'unresolved'}` · "
        f"Requirements source: {story.get('primary_source', 'unknown')}*",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Test cases | {len(suite.test_cases)} |",
        f"| Overall quality score | {critique.overall_score:.2f} |",
        f"| Traceability warnings | {len(warnings)} |",
        f"| Cases flagged for grounding review | {len(grounding_flags)} |",
        f"| Exact-title duplicate candidates | {len(duplicate_candidates)} |",
        "",
        "## Requirements Brief",
        "",
        "### Functional Requirements",
        _numbered(req_tag, brief.functional_requirements),
        "",
        "### Edge Cases",
        _numbered("EC", brief.edge_cases),
        "",
        "### Negative Scenarios",
        _numbered("NS", brief.negative_scenarios),
        "",
        "### Validation Rules",
        _numbered("VR", brief.validation_rules),
        "",
        "### Source Evidence",
        "\n".join(
            f"- **{ref}** ({citation.source}): \"{citation.quote}\""
            for ref, citations in brief.source_evidence.items()
            for citation in citations
        ) or "*No source citations supplied.*",
        "",
        "## Test Cases",
        "",
    ]
    for tc in suite.test_cases:
        out += [
            f"### {tc.tc_id}: {tc.title}",
            "",
            f"**Priority:** {tc.priority} · **Type:** {tc.type} · **Automation:** {tc.automation_status} · "
            f"**Covers:** {', '.join(tc.coverage_refs)}",
            "",
            f"**Preconditions:** {tc.preconditions or 'None'}",
            "",
            "**Steps:**",
            "",
            tc.steps,
            "",
            f"**Expected Result:** {tc.expected_result}",
            "",
            f"**Test Data:** {tc.test_data}",
            "",
        ]
        if tc.roles_covered:
            out += [f"**Roles:** {', '.join(tc.roles_covered)}", ""]

    out += [
        "## Self-Critique",
        "",
        critique.overall_reason or "",
        "",
        "### Missing Coverage",
        _bullets(critique.missing_coverage),
        "",
        "### Possible Duplicates",
        _bullets([" ↔ ".join(p) for p in critique.duplicate_pairs]),
        "",
        "### Suggestions",
        _bullets(critique.improvement_suggestions),
        "",
        "## QA Gaps (questions for the PO)",
        _bullets(brief.qa_gaps),
        "",
    ]
    if warnings:
        out += ["## Traceability Warnings", _bullets(warnings), ""]
    if grounding_flags:
        out += [
            "## Grounding Review Flags",
            "*These cases mention scenario categories not found in the authoritative Jira evidence. "
            "They are retained for QA review, not automatically removed.*",
            _bullets([
                f"{item.get('tc_id', 'Gap item')}: {item.get('title') or item.get('item', '')} "
                f"({', '.join(item.get('categories', []))})"
                for item in grounding_flags
            ]),
            "",
        ]
    if duplicate_candidates:
        out += [
            "## Exact-title Duplicate Candidates",
            "*Review before accepting; candidates are not automatically removed.*",
            _bullets([
                f"{d['generated_tc_id']} may duplicate TestRail {d['existing_case_id']}: {d['title']}"
                for d in duplicate_candidates
            ]),
            "",
        ]
    return "\n".join(out)


def render_gap_analysis(story: dict, gap: GapAnalysis, grounding_flags: list[dict]) -> str:
    out = [
        f"# Gap Analysis: {story['key']} — {story['summary']}",
        "",
        f"*Generated {_timestamp()} via Copilot CLI · Feature: `{story.get('feature_key') or 'unresolved'}`*",
        "",
        "## 1. Requirement Summary",
        _bullets(gap.requirement_summary),
        "",
        "## 2. Identified Gaps",
    ]
    for title, key in GAP_SECTIONS:
        out += ["", f"### {title}", _bullets(getattr(gap, key), "*No gaps identified.*")]
    out += ["", "## 3. Questions for the Product Owner", _bullets(gap.po_questions), ""]
    if grounding_flags:
        out += [
            "",
            "## Grounding Review Flags",
            "*Retained for review; flagged because the item mentions a scenario category absent from authoritative Jira evidence.*",
            _bullets([
                f"{item['section']}: {item['item']} ({', '.join(item['categories'])})"
                for item in grounding_flags
            ]),
        ]
    return "\n".join(out)
