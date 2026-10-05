"""Cypress generation context and guarded spec-file creation."""
import json
import re
from pathlib import Path
from typing import Literal

from . import config, retrieval
from .feature_resolver import canonical_feature_key, load_feature_aliases, resolve_feature_key
from .jira_client import JiraError, fetch_issue
from .parsing import detect_feature_prefix
from .testrail_client import TestRailError, fetch_case

_FEATURE_CONTEXT_DIR = config.RAG_DIR / "docs" / "automation" / "feature-context"
_GUIDELINES_PATH = config.RAG_DIR / "docs" / "automation" / "automation-guidelines.md"
_ALLOWED_SPEC_ROOTS = ("cypress/e2e/parallel/", "cypress/e2e/smoke/", "cypress/e2e/kapost/")
_SPEC_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.cy\.js$")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:password|token|api[_-]?token|access[_-]?token|secret|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*)(['\"`])[^'\"`]*\2"
)
_LITERAL_LOGIN_RE = re.compile(r"(?i)(cy\.login\(\s*)(['\"`])[^'\"`]+\2")
_IMPORT_RE = re.compile(
    r"(?m)^\s*import\s+(?:[^'\";]*?\s+from\s*)?['\"]([^'\"]+)['\"]"
    r"|^\s*export\s+[^'\";]*?\s+from\s*['\"]([^'\"]+)['\"]"
    r"|^\s*(?:(?:const|let|var)\s+[\w$]+\s*=\s*)?require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)


class AutomationError(RuntimeError):
    pass


def _feature_doc(feature_key: str) -> tuple[str, str]:
    canonical = canonical_feature_key(feature_key)
    if not canonical or not _FEATURE_CONTEXT_DIR.is_dir():
        return "", ""
    for path in sorted(_FEATURE_CONTEXT_DIR.glob("*-feature-context.md")):
        stem_key = canonical_feature_key(path.name.removesuffix("-feature-context.md"))
        if stem_key == canonical:
            return path.read_text(encoding="utf-8", errors="ignore"), str(path)
    return "", ""


def _spec_directory_from_feature_doc(text: str, repo_root: Path) -> str:
    repo_root = repo_root.resolve()
    match = re.search(r"(?ims)^##\s+Spec Map\s*(.*?)(?=^##\s|\Z)", text)
    section = match.group(1) if match else text[:3000]
    candidates = re.findall(r"cypress/e2e/[A-Za-z0-9_./-]+", section)
    for candidate in candidates:
        relative = candidate.rstrip(".,:;`)").rstrip("/")
        if not relative.startswith(_ALLOWED_SPEC_ROOTS):
            continue
        target = (repo_root / Path(relative.replace("/", "\\"))).resolve()
        if target.is_relative_to(repo_root) and target.is_dir():
            return relative
    return ""


def feature_target_directory(feature_key: str) -> str:
    """Use the directory declared by that feature's execution-context document."""
    if not config.AUTOMATION_REPO_ROOT or not config.AUTOMATION_REPO_ROOT.is_dir():
        raise AutomationError("AUTOMATION_REPO_ROOT is not configured to an existing Cypress repository.")
    text, source = _feature_doc(feature_key)
    if not text:
        raise AutomationError(f"No feature automation context document found for '{feature_key}'.")
    directory = _spec_directory_from_feature_doc(text, config.AUTOMATION_REPO_ROOT)
    if not directory:
        raise AutomationError(
            f"The feature context at {source} does not identify an existing approved Cypress spec directory."
        )
    return directory


def _sanitize_source(text: str) -> str:
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1'<REDACTED>'", text)
    return _LITERAL_LOGIN_RE.sub(r"\1'<REDACTED>'", text)


def _resolve_indexed_source(doc: dict, repo_root: Path) -> tuple[Path, str] | None:
    repo_root = repo_root.resolve()
    raw = str(doc.get("repo_path") or doc.get("source") or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(repo_root) or not resolved.is_file():
        return None
    relative = resolved.relative_to(repo_root).as_posix()
    if not relative.startswith("cypress/"):
        return None
    if resolved.name.lower() in {"cypress.config.js", "cypress.config.ts", ".env", ".env.local"}:
        return None
    return resolved, relative


def _compact_feature_context(
    text: str,
    page_objects: list[str],
    spec_paths: list[str] | None = None,
    max_chars: int = 4200,
) -> str:
    headings = (
        "Purpose", "Scope", "Spec Map", "Page Object Map", "Custom Command Usage",
        "Test Data Lifecycle", "Reusable Authoring Pattern", "Risks and Gaps",
    )
    pieces = []
    for heading in headings:
        section = _section(text, heading).strip()
        if not section:
            continue
        if heading == "Page Object Map":
            selected_lines = []
            collecting = False
            for line in section.splitlines():
                paths = re.findall(r"cypress/e2e/[A-Za-z0-9_./-]+", line)
                if paths:
                    collecting = paths[0].rstrip(".,:;`/") in page_objects
                if collecting:
                    selected_lines.append(line)
            section = "\n".join(selected_lines).strip()
            if not section:
                continue
        if heading == "Spec Map" and spec_paths:
            basenames = {Path(path).name.lower() for path in spec_paths}
            folders = {str(Path(path).parent).replace("\\", "/").lower() for path in spec_paths}
            kept = []
            for line in section.splitlines():
                low = line.lower().replace("\\", "/")
                if any(name in low for name in basenames) or any(folder in low for folder in folders):
                    kept.append(line)
            section = "\n".join(kept).strip()
            if not section:
                continue
        pieces.append(f"## {heading}\n{section}")
    compact = "\n\n".join(pieces)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit("\n", 1)[0] + "\n[feature context truncated]"


def _compact_general_guidelines(text: str, max_chars: int = 4600) -> str:
    priorities = (
        "Authentication Patterns", "Environment Variables", "Test Data",
        "Key Custom Commands", "API Intercept Pattern", "Page Object Structure",
        "Authoring Expectations", "Security", "Locator Priority", "File Structure",
        "Page Object Usage", "Setup Data",
    )
    matches = list(re.finditer(r"(?m)^#{1,4}\s+(.+)$", text))
    sections = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match.group(1).strip().lower()] = f"{match.group(0)}\n{text[match.end():end].strip()}"
    pieces = []
    for heading in priorities:
        section = next((
            value for key, value in sections.items()
            if key == heading.lower() or key.startswith(heading.lower() + " ")
        ), None)
        if not section:
            continue
        remaining = max_chars - sum(len(piece) + 2 for piece in pieces)
        if remaining <= 0:
            break
        pieces.append(section[:remaining])
    return _sanitize_source("\n\n".join(pieces) if pieces else text[:max_chars])


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*(.*?)(?=^##\s|\Z)", text
    )
    return match.group(1) if match else ""


def _module_imports(source: str) -> list[str]:
    return [next((part for part in match.groups() if part), "") for match in _IMPORT_RE.finditer(source)]


def _resolve_module_path(importer: Path, module: str, repo_root: Path) -> Path | None:
    if not module.startswith("."):
        return None
    base = (importer.parent / Path(module.replace("/", "\\"))).resolve()
    candidates = [base]
    if base.suffix.lower() not in {".js", ".jsx", ".ts", ".tsx"}:
        candidates.extend(Path(str(base) + suffix) for suffix in (".js", ".cy.js", ".ts", ".tsx", ".jsx"))
    candidates.extend(base / f"index{suffix}" for suffix in (".js", ".ts", ".tsx"))
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and resolved.is_relative_to(repo_root):
            return resolved
    return None


def _specs_importing_page_objects(
    repo_root: Path, page_object_paths: list[str], query: str, max_specs: int = 4
) -> tuple[list[dict], list[str]]:
    """Find specs with static imports of the feature's documented Page Objects, ranked by case relevance."""
    repo_root = repo_root.resolve()
    page_objects: dict[Path, str] = {}
    for relative in page_object_paths:
        resolved = (repo_root / Path(relative.replace("/", "\\"))).resolve()
        if resolved.is_file() and resolved.is_relative_to(repo_root):
            page_objects[resolved] = resolved.relative_to(repo_root).as_posix()
    if not page_objects:
        return [], []

    e2e_root = repo_root / "cypress" / "e2e"
    if not e2e_root.is_dir():
        return [], []

    query_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", query) if len(token) > 3}
    matches = []
    for pattern in ("*.cy.js", "*.cy.ts", "*.cy.jsx", "*.cy.tsx"):
        for spec_path in e2e_root.rglob(pattern):
            relative = spec_path.relative_to(repo_root).as_posix()
            if "/pageobjects/" in relative.lower() or "/spec-verification/" in relative.lower():
                continue
            try:
                spec_source = spec_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            imported = set()
            resolved_modules = set()
            for module in _module_imports(spec_source):
                resolved_import = _resolve_module_path(spec_path, module, repo_root)
                if resolved_import:
                    resolved_modules.add(resolved_import)
                if resolved_import in page_objects:
                    imported.add(resolved_import)
            if not imported:
                continue
            token_text = f"{relative} {spec_source}".lower()
            score = sum(1 for token in query_tokens if token in token_text)
            selected_page_objects = sorted(page_objects[path] for path in imported)
            imported_module_paths = sorted(
                path.relative_to(repo_root).as_posix() for path in resolved_modules
            )
            matches.append((score, relative, selected_page_objects, imported_module_paths))

    matches.sort(key=lambda item: (-item[0], item[1].lower()))
    specs = [
        {
            "path": relative,
            "imports_feature_page_objects": imported_paths,
            "resolved_import_paths": module_paths,
            "relevance_score": score,
        }
        for score, relative, imported_paths, module_paths in matches[:max_specs]
    ]
    used_page_objects = sorted({path for item in specs for path in item["imports_feature_page_objects"]})
    return specs, used_page_objects


_PO_QUERY_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "user", "users",
    "test", "tests", "case", "cases", "verify", "verifies", "should", "when",
    "then", "into", "click", "open", "page", "button", "notes", "feature",
    "content", "type", "types", "application", "options", "option", "dropdown",
    "displayed", "display", "using", "expected", "result", "step", "steps",
    "not", "none", "without", "does", "appear", "appears", "is", "are",
}


def _code_tokens(text: str) -> set[str]:
    expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    tokens = {word.lower() for word in re.findall(r"[A-Za-z]+", expanded) if len(word) > 2}
    stems = set()
    for token in tokens:
        if token.endswith("ied") and len(token) > 5:
            stems.add(token[:-3] + "y")
        elif token.endswith("ed") and len(token) > 5:
            stem = token[:-2]
            stems.add(stem + "e" if stem.endswith(("v", "t", "c", "g")) else stem)
        elif token.endswith("s") and len(token) > 4:
            stems.add(token[:-1])
    tokens |= stems
    return tokens


def _feature_page_object_paths(
    feature_doc: str, query: str, repo_root: Path, focus_text: str = ""
) -> list[str]:
    """Choose case-matching Page Objects using feature-map descriptions, then source as secondary evidence."""
    section = _section(feature_doc, "Page Object Map")
    lines = section.splitlines()
    primary_text = focus_text or query[:1000]
    query_terms = _code_tokens(primary_text) - _PO_QUERY_STOPWORDS
    if not query_terms:
        query_terms = _code_tokens(query[:1000]) - _PO_QUERY_STOPWORDS

    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        matches = re.findall(r"cypress/e2e/[A-Za-z0-9_./-]+", line)
        if not matches:
            continue
        relative = matches[0].rstrip(".,:;`/")
        if "/pageobjects/" not in relative.lower():
            continue
        block_lines = [line]
        for following in lines[index + 1:]:
            if re.search(r"cypress/e2e/[A-Za-z0-9_./-]+", following):
                break
            block_lines.append(following)
        target = (repo_root.resolve() / Path(relative.replace("/", "\\"))).resolve()
        if not target.is_relative_to(repo_root.resolve()) or not target.is_file():
            continue
        try:
            source = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        doc_tokens = _code_tokens(" ".join(block_lines))
        source_tokens = _code_tokens(source)
        path_tokens = _code_tokens(relative)
        documented_matches = query_terms & doc_tokens
        source_matches = query_terms & source_tokens
        path_matches = query_terms & path_tokens
        score = 5 * len(documented_matches) + 2 * len(path_matches) + len(source_matches)
        if documented_matches or path_matches:
            candidates.append((score, relative))

    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    return list(dict.fromkeys(path for _, path in candidates))


def get_cypress_repository_context(
    feature_key: str,
    query: str,
    feature_doc: str = "",
    per_kind: int = 3,
    focus_text: str = "",
) -> dict:
    """Retrieve relevant indexed Cypress files, then read bounded source from the configured repo."""
    if not config.AUTOMATION_REPO_ROOT or not config.AUTOMATION_REPO_ROOT.is_dir():
        raise AutomationError("AUTOMATION_REPO_ROOT is not configured to an existing Cypress repository.")

    root = config.AUTOMATION_REPO_ROOT.resolve()
    feature_pages = _feature_page_object_paths(
        feature_doc, query, config.AUTOMATION_REPO_ROOT, focus_text
    )
    if not feature_pages:
        raise AutomationError(
            f"No Page Object in feature '{feature_key}' matched this case's behavior. "
            "Update the feature map or request locator discovery; refusing to use unrelated Page Objects."
        )
    mapped_spec_directory = _spec_directory_from_feature_doc(feature_doc, root) if feature_doc else ""
    spec_graph, imported_page_objects = _specs_importing_page_objects(
        root, feature_pages, focus_text or query[:1200]
    )
    if not spec_graph and mapped_spec_directory:
        raise AutomationError(
            f"No Cypress specs importing the documented Page Objects were found for feature '{feature_key}'. "
            "Update the feature map or repo index; refusing to use unrelated feature specs."
        )

    selected_page_objects = imported_page_objects or feature_pages
    common_page_object = "cypress/e2e/kapost/pageObjects/commonObjectsAndUtilities/commonObjectsAndUtils.cy.js"
    commands_path = "cypress/support/commands.js"
    selected_specs = [item["path"] for item in spec_graph]
    helper_paths = []
    for spec in spec_graph:
        for relative in spec.get("resolved_import_paths", []):
            lower = relative.lower()
            if (
                ("/support/" in lower or "/fixtures/" in lower or "/helpers/" in lower)
                and not lower.endswith("/commands.js")
                and not lower.endswith("commonobjectsandutils.cy.js")
                and relative not in selected_page_objects
            ):
                helper_paths.append(relative)
    helper_paths = list(dict.fromkeys(helper_paths))[:2]

    required_paths = list(dict.fromkeys(
        selected_specs + selected_page_objects + [common_page_object, commands_path]
    ))
    requested_paths = list(dict.fromkeys(required_paths + helper_paths))
    indexed = retrieval.get_indexed_cypress_chunks(
        root,
        requested_paths,
        focus_text or query,
        chunks_per_path=2,
        max_chars_per_chunk=850,
    )
    missing_required = [path for path in indexed["missing_paths"] if path in set(required_paths)]
    if missing_required:
        raise AutomationError(
            "The FAISS index is missing required Cypress chunks for these exact files: "
            f"{missing_required}. Rebuild the automation index; direct source fallback is disabled."
        )

    grouped: dict[str, list[dict]] = {
        "specs": [], "page_objects": [], "custom_commands": [], "data_helpers": []
    }
    category_for_path = {
        **{path: "specs" for path in selected_specs},
        **{path: "page_objects" for path in selected_page_objects},
        common_page_object: "page_objects",
        commands_path: "custom_commands",
        **{path: "data_helpers" for path in helper_paths},
    }
    for chunk in indexed["chunks"]:
        category = category_for_path.get(chunk["path"])
        if not category:
            continue
        grouped[category].append({
            "path": chunk["path"],
            "chunk_id": chunk["id"],
            "type": chunk["type"],
            "content": _sanitize_source(chunk["snippet"]),
            "relevance_score": chunk["relevance_score"],
            "retrieval_source": "faiss-exact-repo-path",
        })

    grouped["scope"] = [{
        "feature_page_objects_matching_case": feature_pages,
        "page_objects_imported_by_selected_specs": imported_page_objects,
        "selected_spec_count": len(selected_specs),
        "indexed_chunk_count": len(indexed["chunks"]),
        "missing_optional_helper_chunks": [path for path in indexed["missing_paths"] if path in helper_paths],
        "content_source": "FAISS chunks matching exact repository paths; no source-file content fallback",
        "shared_context": [common_page_object, "cypress/support/commands.js"],
        "spec_selection": "static imports of feature-mapped Page Objects; ranked within that set using case relevance",
    }]
    return grouped


def build_automation_context(issue_key: str, context: dict, case_ids: list[str]) -> dict:
    """Load saved manual cases, project patterns, feature instructions, and a safe target folder."""
    if not config.AUTOMATION_REPO_ROOT or not config.AUTOMATION_REPO_ROOT.is_dir():
        raise AutomationError("AUTOMATION_REPO_ROOT is not configured to an existing Cypress repository.")
    artifact_path = config.OUTPUT_DIR / f"{issue_key}-test-cases.json"
    try:
        import json
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AutomationError(f"No readable generated test-case JSON found at {artifact_path}.") from e

    cases_by_id = {str(case.get("tc_id", "")): case for case in artifact.get("test_cases", [])}
    if not case_ids:
        return {
            "issue_key": issue_key,
            "story": context["story"],
            "case_selection_required": True,
            "available_test_cases": [
                {
                    "tc_id": case_id,
                    "title": case.get("title", ""),
                    "priority": case.get("priority", ""),
                }
                for case_id, case in cases_by_id.items()
            ],
        }
    missing = [case_id for case_id in case_ids if case_id not in cases_by_id]
    if missing:
        raise AutomationError(f"Test case IDs were not found in the saved artifact: {missing}")
    selected_cases = [cases_by_id[case_id] for case_id in dict.fromkeys(case_ids)]

    story = context["story"]
    feature_doc, feature_doc_path = _feature_doc(story.get("feature_key", ""))
    target_directory = feature_target_directory(story.get("feature_key", ""))
    guidelines = _GUIDELINES_PATH.read_text(encoding="utf-8", errors="ignore") if _GUIDELINES_PATH.exists() else ""
    if not guidelines:
        raise AutomationError(f"Automation guidelines are missing at {_GUIDELINES_PATH}.")
    guidelines = _compact_general_guidelines(guidelines)

    query = "\n".join(
        f"{case.get('title', '')} {case.get('preconditions', '')} {case.get('steps', '')} {case.get('expected_result', '')}"
        for case in selected_cases
    )
    focus_text = "\n".join(
        f"{case.get('title', '')} {case.get('preconditions', '')} "
        f"{str(case.get('steps', '')).splitlines()[:8]} {case.get('expected_result', '')}"
        for case in selected_cases
    )
    patterns = get_cypress_repository_context(
        story.get("feature_key", ""), query, feature_doc=feature_doc, focus_text=focus_text
    )
    return {
        "issue_key": issue_key,
        "story": story,
        "selected_test_cases": selected_cases,
        "general_guidelines": guidelines,
        "feature_context": _compact_feature_context(
            feature_doc,
            [item["path"] for item in patterns["page_objects"] if item["path"] != "cypress/e2e/kapost/pageObjects/commonObjectsAndUtilities/commonObjectsAndUtils.cy.js"],
            [item["path"] for item in patterns["specs"]],
        ),
        "feature_context_path": feature_doc_path,
        "target_spec_directory": target_directory,
        "existing_specs": patterns["specs"],
        "page_objects": patterns["page_objects"],
        "custom_commands": patterns["custom_commands"],
        "data_helpers": patterns["data_helpers"],
        "automation_scope": patterns["scope"],
    }


def _resolve_testrail_case_feature(case: dict, requested_feature_key: str = "") -> tuple[str, list[str]]:
    evidence = "\n".join([
        case.get("title", ""),
        case.get("section_name", ""),
        case.get("preconditions", ""),
        case.get("legacy_expected_result", ""),
        "\n".join(
            f"{step.get('action', '')} {step.get('expected', '')}"
            for step in case.get("steps", [])
        ),
    ])
    discovered = set()
    from_case = resolve_feature_key(case.get("title", ""), extra_text=evidence)
    if from_case:
        discovered.add(canonical_feature_key(from_case))

    jira_features = set()
    jira_warnings = []
    for issue_key in case.get("references", []):
        try:
            issue = fetch_issue(issue_key)
        except JiraError as e:
            jira_warnings.append(f"Could not verify linked Jira issue {issue_key}: {e}")
            continue
        key = resolve_feature_key(
            issue.get("summary", ""),
            extra_text=f"{issue.get('description', '')} {case.get('title', '')}",
        )
        if key:
            jira_features.add(canonical_feature_key(key))

    if len(jira_features) > 1:
        raise AutomationError(
            f"TestRail case {case['case_id']} references Jira issues from multiple features: {sorted(jira_features)}. "
            "Choose a single case or correct its references."
        )
    if jira_features:
        discovered.update(jira_features)

    requested = canonical_feature_key(requested_feature_key) if requested_feature_key else ""
    known_features = set(load_feature_aliases())
    if requested and requested not in known_features:
        raise AutomationError(
            f"Unknown feature key '{requested_feature_key}'. Use one of: {', '.join(sorted(known_features))}."
        )
    if requested:
        discovered.add(requested)
    if len(discovered) > 1:
        raise AutomationError(
            f"Feature evidence conflicts for TestRail case {case['case_id']}: {sorted(discovered)}. "
            "Resolve the case title/references or provide corrected source data; refusing to guess."
        )
    if not discovered:
        detail = f" Linked Jira lookup notes: {'; '.join(jira_warnings)}" if jira_warnings else ""
        raise AutomationError(
            f"Could not confidently resolve a feature for TestRail case {case['case_id']}. "
            "Add a feature alias to the case title/section or pass an explicit known feature key." + detail
        )
    return next(iter(discovered)), jira_warnings


def build_testrail_automation_context(case_id: str, feature_key: str = "") -> dict:
    """Build Cypress context directly from one live TestRail case ID."""
    case = fetch_case(case_id)
    resolved_feature, warnings = _resolve_testrail_case_feature(case, feature_key)
    feature_doc, feature_doc_path = _feature_doc(resolved_feature)
    if not feature_doc:
        raise AutomationError(
            f"No feature automation context exists for '{resolved_feature}'; refusing to generate ungrounded Cypress code."
        )
    target_directory = feature_target_directory(resolved_feature)
    if not _GUIDELINES_PATH.is_file():
        raise AutomationError(f"Automation guidelines are missing at {_GUIDELINES_PATH}.")
    guidelines = _GUIDELINES_PATH.read_text(encoding="utf-8", errors="ignore")
    if not guidelines.strip():
        raise AutomationError("General Cypress automation guidelines are empty.")
    guidelines = _compact_general_guidelines(guidelines)

    step_text = "\n".join(
        f"{index}. {step.get('action') or '[Action not specified]'}"
        + (f"\n   Expected: {step['expected']}" if step.get("expected") else "")
        for index, step in enumerate(case["steps"], 1)
    )
    if not step_text.strip():
        raise AutomationError(
            f"TestRail case {case['case_id']} has no usable steps; add steps before generating automation."
        )

    pseudo_case = {
        "tc_id": case["case_id"],
        "title": case["title"],
        "priority": "Medium",
        "type": "Functional",
        "preconditions": case["preconditions"],
        "steps": step_text,
        "expected_result": case["legacy_expected_result"] or "See expected results paired with the steps above.",
        "test_data": "N/A",
        "automation_status": "Candidate",
        "roles_covered": [],
        "coverage_refs": case["references"],
    }
    query = f"{case['title']} {case['preconditions']} {step_text} {case['legacy_expected_result']}"
    focus_text = "\n".join([
        case["title"], case["section_name"], case["preconditions"],
        "\n".join(
            f"{step.get('action', '')} {step.get('expected', '')}"
            for step in case["steps"][:8]
        ),
        case["legacy_expected_result"],
    ])
    patterns = get_cypress_repository_context(
        resolved_feature, query, feature_doc=feature_doc, focus_text=focus_text
    )
    product_knowledge = retrieval.get_product_knowledge(
        resolved_feature, case["title"], query, top_k=3
    )
    role_permissions = retrieval.get_role_context(
        case["title"], detect_feature_prefix(case["title"])
    )
    return {
        "source_kind": "testrail",
        "source_id": case["case_id"],
        "source_case": {
            "case_id": case["case_id"],
            "title": case["title"],
            "section_name": case["section_name"],
            "references": case["references"],
            "step_count": len(case["steps"]),
        },
        "story": {
            "key": case["case_id"],
            "summary": case["title"],
            "feature_key": resolved_feature,
            "feature_prefix": detect_feature_prefix(case["title"]),
            "linked_jira_issues": case["references"],
        },
        "selected_test_cases": [pseudo_case],
        "general_guidelines": guidelines,
        "feature_context": _compact_feature_context(
            feature_doc,
            [item["path"] for item in patterns["page_objects"] if item["path"] != "cypress/e2e/kapost/pageObjects/commonObjectsAndUtilities/commonObjectsAndUtils.cy.js"],
            [item["path"] for item in patterns["specs"]],
        ),
        "feature_context_path": feature_doc_path,
        "product_knowledge": product_knowledge,
        "role_permissions": role_permissions,
        "target_spec_directory": target_directory,
        "existing_specs": patterns["specs"],
        "page_objects": patterns["page_objects"],
        "custom_commands": patterns["custom_commands"],
        "data_helpers": patterns["data_helpers"],
        "automation_scope": patterns["scope"],
        "warnings": warnings,
    }


def validate_spec_content(content: str, selected_case_ids: list[str]) -> list[str]:
    errors = []
    if not content.strip():
        errors.append("Spec content is empty.")
    if not re.search(r"\bdescribe\s*\(", content):
        errors.append("Spec must contain a Cypress describe() block.")
    if not re.search(r"\bit\s*\(", content):
        errors.append("Spec must contain at least one it() test.")
    if re.search(r"\bcy\.get\s*\(", content):
        errors.append("Spec contains cy.get(); selectors must use existing page-object methods or wrappers.")
    missing_ids = [case_id for case_id in selected_case_ids if case_id not in content]
    if missing_ids:
        errors.append(f"Spec does not include traceability IDs for selected cases: {missing_ids}")
    if re.search(r"(?i)\b(?:password|api[_-]?token|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"`][^'\"`]{6,}['\"`]", content):
        errors.append("Spec appears to contain a hard-coded credential; use Cypress.env() instead.")
    return errors


def create_spec_file(
    issue_key: str,
    feature_key: str,
    filename: str,
    content: str,
    selected_case_ids: list[str],
    user_approved: bool,
) -> dict:
    """Create one new Cypress spec in its mapped folder. Existing files are never overwritten."""
    if not user_approved:
        return {"ok": False, "error": "Ask the user to approve the exact target path and preview before saving."}
    if not _SPEC_FILENAME_RE.fullmatch(filename or ""):
        return {"ok": False, "error": "Filename must be a simple .cy.js basename without directories."}
    artifact_path = config.OUTPUT_DIR / f"{issue_key}-test-cases.json"
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"Could not verify the saved test-case artifact: {artifact_path}"}
    saved_ids = {str(case.get("tc_id", "")) for case in artifact.get("test_cases", [])}
    unknown_ids = [case_id for case_id in selected_case_ids if case_id not in saved_ids]
    if unknown_ids:
        return {"ok": False, "error": f"Case IDs are not in the saved artifact: {unknown_ids}"}
    errors = validate_spec_content(content, selected_case_ids)
    if errors:
        return {"ok": False, "errors": errors}
    try:
        directory = feature_target_directory(feature_key)
    except AutomationError as e:
        return {"ok": False, "error": str(e)}

    repo_root = config.AUTOMATION_REPO_ROOT.resolve()
    target_dir = (repo_root / Path(directory.replace("/", "\\"))).resolve()
    if not target_dir.is_relative_to(repo_root) or not any(directory.startswith(prefix) for prefix in _ALLOWED_SPEC_ROOTS):
        return {"ok": False, "error": "Resolved destination is outside the approved Cypress spec directories."}
    target = target_dir / filename
    try:
        with target.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content.rstrip() + "\n")
    except FileExistsError:
        return {"ok": False, "error": f"Refusing to overwrite existing spec: {target.relative_to(repo_root).as_posix()}"}
    except OSError as e:
        return {"ok": False, "error": f"Could not create spec file: {e}"}
    return {"ok": True, "created_path": str(target), "relative_path": target.relative_to(repo_root).as_posix()}


def create_testrail_spec_file(
    case_id: str,
    filename: str,
    content: str,
    user_approved: bool,
    feature_key: str = "",
) -> dict:
    """Create a spec from a live TestRail case after revalidating feature and traceability."""
    if not user_approved:
        return {"ok": False, "error": "Ask the user to approve the exact target path and preview before saving."}
    try:
        case = fetch_case(case_id)
        resolved_feature, _ = _resolve_testrail_case_feature(case, feature_key)
    except (TestRailError, AutomationError) as e:
        return {"ok": False, "error": str(e)}
    errors = validate_spec_content(content, [case["case_id"]])
    if errors:
        return {"ok": False, "errors": errors}
    if not _SPEC_FILENAME_RE.fullmatch(filename or ""):
        return {"ok": False, "error": "Filename must be a simple .cy.js basename without directories."}
    try:
        directory = feature_target_directory(resolved_feature)
    except AutomationError as e:
        return {"ok": False, "error": str(e)}
    if not config.AUTOMATION_REPO_ROOT or not config.AUTOMATION_REPO_ROOT.is_dir():
        return {"ok": False, "error": "AUTOMATION_REPO_ROOT is not configured to an existing Cypress repository."}
    repo_root = config.AUTOMATION_REPO_ROOT.resolve()
    target_dir = (repo_root / Path(directory.replace("/", "\\"))).resolve()
    if not target_dir.is_relative_to(repo_root) or not any(directory.startswith(root) for root in _ALLOWED_SPEC_ROOTS):
        return {"ok": False, "error": "Resolved destination is outside the approved Cypress spec directories."}
    target = target_dir / filename
    try:
        with target.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content.rstrip() + "\n")
    except FileExistsError:
        return {"ok": False, "error": f"Refusing to overwrite existing spec: {target.relative_to(repo_root).as_posix()}"}
    except OSError as e:
        return {"ok": False, "error": f"Could not create spec file: {e}"}
    return {
        "ok": True,
        "source_case_id": case["case_id"],
        "feature_key": resolved_feature,
        "created_path": str(target),
        "relative_path": target.relative_to(repo_root).as_posix(),
    }


def save_cypress_preview(
    source_type: Literal["jira", "testrail"],
    source_id: str,
    filename: str,
    content: str,
    case_ids: list[str],
    user_approved: bool,
    feature_key: str = "",
) -> dict:
    """Save a reviewed Cypress preview under QA CLI output, never in the external automation repo."""
    if not user_approved:
        return {"ok": False, "error": "Ask the user to approve saving the preview under qa-copilot-cli/output/."}
    if not _SPEC_FILENAME_RE.fullmatch(filename or ""):
        return {"ok": False, "error": "Filename must be a simple .cy.js basename without directories."}
    if not case_ids:
        return {"ok": False, "error": "Provide at least one source case ID for traceability validation."}
    errors = validate_spec_content(content, case_ids)
    if errors:
        return {"ok": False, "errors": errors}

    source_folder = ""
    resolved_feature = ""
    if source_type == "jira":
        try:
            key = config.validate_issue_key(source_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        artifact_path = config.OUTPUT_DIR / f"{key}-test-cases.json"
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"ok": False, "error": f"Could not read the saved Jira test-case artifact for {key}."}
        saved = {str(case.get("tc_id", "")) for case in artifact.get("test_cases", [])}
        unknown = [case_id for case_id in case_ids if case_id not in saved]
        if unknown:
            return {"ok": False, "error": f"Case IDs are not in the saved Jira artifact: {unknown}"}
        resolved_feature = canonical_feature_key(
            feature_key or str((artifact.get("story") or {}).get("feature_key", ""))
        )
        if not resolved_feature:
            return {"ok": False, "error": "No feature key is available in the Jira artifact; refusing to save an unclassified preview."}
        source_folder = key
    elif source_type == "testrail":
        try:
            case = fetch_case(source_id)
            resolved_feature, _ = _resolve_testrail_case_feature(case, feature_key)
        except (TestRailError, AutomationError) as e:
            return {"ok": False, "error": str(e)}
        if case["case_id"] not in case_ids:
            return {"ok": False, "error": f"case_ids must include the source TestRail ID {case['case_id']} for traceability."}
        source_folder = case["case_id"]
    else:
        return {"ok": False, "error": "source_type must be 'jira' or 'testrail'."}

    destination = config.OUTPUT_DIR / "automation" / source_folder
    try:
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / filename
        with target.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content.rstrip() + "\n")
    except FileExistsError:
        return {"ok": False, "error": f"Refusing to overwrite existing preview: {target}"}
    except OSError as e:
        return {"ok": False, "error": f"Could not save preview under QA output: {e}"}

    return {
        "ok": True,
        "source_type": source_type,
        "source_id": source_folder,
        "feature_key": resolved_feature,
        "saved_path": str(target),
        "repo_modified": False,
    }
