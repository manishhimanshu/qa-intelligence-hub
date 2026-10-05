import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_TC_ID_RE = re.compile(r"^TC-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3}$")
_REF_RE = re.compile(r"^(FR|SC|EC|NS|VR)-\d{2}$")

# Mirrors _drop_unstated_scenarios in the Streamlit generator.
GUARD_TERMS = {
    "network_failure": [
        "network failure", "network error", "connection lost", "offline",
        "server error", "api failure", "timeout", "service unavailable",
        "500", "502", "503", "504",
    ],
    "concurrency": ["concurrent", "simultaneous", "race condition", "parallel edit", "conflict"],
    "performance": ["performance", "load time", "stress", "high load", "latency"],
    "browser": ["unsupported browser", "cross-browser", "browser compatibility"],
}


def unsupported_by_evidence(text: str, evidence: str) -> bool:
    text_l, evidence_l = text.lower(), evidence.lower()
    for terms in GUARD_TERMS.values():
        if any(t in text_l for t in terms) and not any(t in evidence_l for t in terms):
            return True
    return False


def unsupported_categories(text: str, evidence: str) -> list[str]:
    """Return scenario categories that appear without evidence, without deciding whether to discard them."""
    text_l, evidence_l = text.lower(), evidence.lower()
    return [
        category
        for category, terms in GUARD_TERMS.items()
        if any(term in text_l for term in terms) and not any(term in evidence_l for term in terms)
    ]


class EvidenceCitation(BaseModel):
    source: Literal["acceptance_criteria", "steps_to_reproduce", "description", "comments", "summary"]
    quote: str = Field(min_length=8)


class RequirementsBrief(BaseModel):
    functional_requirements: list[str] = Field(min_length=1)
    edge_cases: list[str] = []
    negative_scenarios: list[str] = []
    validation_rules: list[str] = []
    api_interactions: list[str] = []
    test_design_techniques: list[str] = []
    qa_gaps: list[str] = []
    source_evidence: dict[str, list[EvidenceCitation]] = Field(default_factory=dict)


class TestCase(BaseModel):
    tc_id: str
    title: str = Field(min_length=5)
    priority: Literal["Critical", "High", "Medium", "Low"]
    type: Literal["Functional", "Regression", "Smoke", "Integration", "Negative", "Edge"]
    preconditions: str = ""
    steps: str = Field(min_length=5)
    expected_result: str = Field(min_length=5)
    test_data: str = "N/A"
    automation_status: Literal["Automated", "Manual", "Candidate"] = "Manual"
    roles_covered: list[str] = []
    coverage_refs: list[str] = Field(min_length=1)

    @field_validator("tc_id")
    @classmethod
    def _tc_id_format(cls, v: str) -> str:
        if not _TC_ID_RE.match(v):
            raise ValueError("tc_id must look like TC-FEATURE-001")
        return v

    @field_validator("steps")
    @classmethod
    def _steps_numbered(cls, v: str) -> str:
        if not re.match(r"^\s*1\.", v):
            raise ValueError("steps must be a numbered list starting with '1.'")
        return v

    @field_validator("coverage_refs")
    @classmethod
    def _refs_format(cls, v: list[str]) -> list[str]:
        bad = [r for r in v if not _REF_RE.match(r)]
        if bad:
            raise ValueError(f"invalid coverage_refs {bad}; use FR-01, SC-01, EC-01, NS-01 or VR-01")
        return v


class Critique(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    overall_reason: str = ""
    duplicate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    traceability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_result_score: float | None = Field(default=None, ge=0.0, le=1.0)
    realism_score: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_coverage: list[str] = []
    duplicate_pairs: list[list[str]] = []
    improvement_suggestions: list[str] = []


class TestCaseSuite(BaseModel):
    requirements_brief: RequirementsBrief
    test_cases: list[TestCase] = Field(min_length=1)
    critique: Critique


class GapAnalysis(BaseModel):
    requirement_summary: list[str] = Field(min_length=1)
    functional_gaps: list[str] = []
    role_permission_gaps: list[str] = []
    data_validation_gaps: list[str] = []
    state_edge_case_gaps: list[str] = []
    integration_gaps: list[str] = []
    non_functional_gaps: list[str] = []
    po_questions: list[str] = []


GAP_SECTIONS = [
    ("Functional Gaps", "functional_gaps"),
    ("Role & Permission Gaps", "role_permission_gaps"),
    ("Data Validation Gaps", "data_validation_gaps"),
    ("State & Edge Case Gaps", "state_edge_case_gaps"),
    ("Integration Gaps", "integration_gaps"),
    ("Non-Functional Gaps", "non_functional_gaps"),
]


def check_traceability(suite: TestCaseSuite, primary_source: str) -> tuple[list[str], list[str]]:
    """Return (errors for refs pointing at non-existent items, warnings for uncovered requirements)."""
    brief = suite.requirements_brief
    req_tag = "SC" if primary_source == "str" else "FR"
    valid = {f"{req_tag}-{i:02d}" for i in range(1, len(brief.functional_requirements) + 1)}
    valid |= {f"EC-{i:02d}" for i in range(1, len(brief.edge_cases) + 1)}
    valid |= {f"NS-{i:02d}" for i in range(1, len(brief.negative_scenarios) + 1)}
    valid |= {f"VR-{i:02d}" for i in range(1, len(brief.validation_rules) + 1)}

    errors, covered = [], set()
    ids = [tc.tc_id for tc in suite.test_cases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"Duplicate tc_id values: {dupes}")
    for tc in suite.test_cases:
        unknown = [r for r in tc.coverage_refs if r not in valid]
        if unknown:
            errors.append(f"{tc.tc_id}: coverage_refs {unknown} do not exist in the requirements brief")
        covered.update(tc.coverage_refs)

    must_cover = sorted(r for r in valid if not r.startswith("VR-"))
    warnings = [f"{r} is not covered by any test case" for r in must_cover if r not in covered]
    return errors, warnings


def _normalise_quote(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def check_source_evidence(
    suite: TestCaseSuite, primary_source: str, source_text: dict[str, str]
) -> list[str]:
    """Require each generated requirement to cite an exact, allowed Jira-source excerpt."""
    brief = suite.requirements_brief
    req_tag = "SC" if primary_source == "str" else "FR"
    refs = {
        **{f"{req_tag}-{i:02d}": v for i, v in enumerate(brief.functional_requirements, 1)},
        **{f"EC-{i:02d}": v for i, v in enumerate(brief.edge_cases, 1)},
        **{f"NS-{i:02d}": v for i, v in enumerate(brief.negative_scenarios, 1)},
        **{f"VR-{i:02d}": v for i, v in enumerate(brief.validation_rules, 1)},
    }
    allowed_sources = {
        "ac": {"acceptance_criteria", "comments"},
        "str": {"steps_to_reproduce", "comments"},
        "description": {"description", "comments"},
        "none": {"summary", "comments"},
    }.get(primary_source, {"comments"})
    citations = brief.source_evidence
    errors = []

    for ref in sorted(set(citations) - set(refs)):
        errors.append(f"Source evidence references unknown requirement {ref}.")

    for ref in refs:
        items = citations.get(ref, [])
        if not items:
            errors.append(f"{ref} has no Jira source_evidence citation.")
            continue
        valid_citation = False
        for item in items:
            if item.source not in allowed_sources:
                errors.append(f"{ref} cites {item.source}, which is not authoritative for primary source '{primary_source}'.")
                continue
            quote = _normalise_quote(item.quote)
            source = _normalise_quote(source_text.get(item.source, ""))
            if len(quote) < 8 or quote not in source:
                errors.append(f"{ref} citation does not exactly match its Jira source excerpt.")
            else:
                valid_citation = True
        if not valid_citation and not any(f"{ref} " in e or e.startswith(f"{ref}:") for e in errors):
            errors.append(f"{ref} has no valid Jira source_evidence citation.")

    return errors


def find_exact_duplicates(test_cases: list[TestCase], existing_cases: list[dict]) -> list[dict]:
    """Flag exact normalized title matches; semantic similarity remains a human/agent review task."""
    def normalise_title(title: str) -> str:
        title = re.sub(r"^\[[^]]+\]\s*", "", title or "")
        return " ".join(re.findall(r"[a-z0-9]+", title.lower()))

    existing_by_title: dict[str, list[dict]] = {}
    for case in existing_cases:
        title = normalise_title(case.get("title", ""))
        if title:
            existing_by_title.setdefault(title, []).append(case)

    matches = []
    for case in test_cases:
        title = normalise_title(case.title)
        for match in existing_by_title.get(title, []):
            matches.append({"generated_tc_id": case.tc_id, "existing_case_id": match.get("id", ""), "title": match.get("title", "")})
    return matches
