import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config  # noqa: E402
from core import automation  # noqa: E402
from core import story_context  # noqa: E402
from core.feature_resolver import canonical_feature_key, resolve_feature_key  # noqa: E402
from core.markdown import render_gap_analysis, render_test_cases  # noqa: E402
from core import retrieval  # noqa: E402
from core.parsing import (  # noqa: E402
    adf_to_markdown,
    detect_feature_prefix,
    extract_acceptance_criteria,
    extract_steps_to_reproduce,
    normalize_ticket,
)
from core.testrail_client import TestRailError, fetch_case, normalize_case_id  # noqa: E402
from core.schemas import (  # noqa: E402
    GapAnalysis,
    TestCaseSuite,
    check_source_evidence,
    check_traceability,
    find_exact_duplicates,
    unsupported_by_evidence,
)
from pydantic import ValidationError  # noqa: E402


def _case(tc_id="TC-FEATURE-001", refs=("FR-01",), **overrides):
    case = {
        "tc_id": tc_id,
        "title": "[FR-01] Create a book verifies it appears in the book list",
        "priority": "High",
        "type": "Functional",
        "preconditions": "User is logged in",
        "steps": "1. Open Notes\n2. Click Add a Book",
        "expected_result": "A new book tab is displayed",
        "coverage_refs": list(refs),
    }
    case.update(overrides)
    return case


def _suite(cases, frs=("Users can create a book",), ecs=(), nss=()):
    return TestCaseSuite.model_validate({
        "requirements_brief": {
            "functional_requirements": list(frs),
            "edge_cases": list(ecs),
            "negative_scenarios": list(nss),
            "source_evidence": {
                f"FR-{i:02d}": [{"source": "acceptance_criteria", "quote": f"Requirement: {text}"}]
                for i, text in enumerate(frs, 1)
            },
        },
        "test_cases": cases,
        "critique": {"overall_score": 0.85, "overall_reason": "Good coverage."},
    })


class ParsingTests(unittest.TestCase):
    def test_adf_headings_and_lists(self):
        adf = {"type": "doc", "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Rules"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "One"}]}]},
            ]},
            {"type": "orderedList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First"}]}]},
            ]},
        ]}
        self.assertEqual(adf_to_markdown(adf), "## Rules\n- One\n1. First")

    def test_ac_groups_and_bullets(self):
        content = "## Acceptance Criteria\nSearch behavior:\n- Matches title\n- Matches body\n## Notes\n- ignored"
        self.assertEqual(
            extract_acceptance_criteria(content),
            ["Search behavior: Matches title", "Search behavior: Matches body"],
        )

    def test_ac_gherkin_one_item_per_scenario(self):
        content = (
            "Acceptance Criteria\nGiven a user\nWhen they archive\nThen it is hidden\n"
            "Given an admin\nWhen they restore\nThen it is visible"
        )
        self.assertEqual(extract_acceptance_criteria(content), [
            "Given a user / When they archive / Then it is hidden",
            "Given an admin / When they restore / Then it is visible",
        ])

    def test_ac_ignores_horizontal_rule(self):
        self.assertEqual(extract_acceptance_criteria("Acceptance Criteria\n---\n- Item"), ["Item"])

    def test_steps_to_reproduce(self):
        content = "## Steps to Reproduce\n1. Open Notes\n2. Type text\n## Other"
        self.assertEqual(extract_steps_to_reproduce(content), ["Open Notes", "Type text"])

    def test_normalize_prefers_ac_then_str(self):
        t = normalize_ticket("STUD-1", "s", "desc", ["ac"], ["step"], "", "Story", "notes")
        self.assertEqual((t["primary_source"], t["requirements"]), ("ac", ["ac"]))
        t = normalize_ticket("STUD-1", "s", "desc", [], ["step"], "", "Bug", "notes")
        self.assertEqual(t["primary_source"], "str")

    def test_normalize_strips_base64(self):
        blob = "A" * 150
        t = normalize_ticket("STUD-1", "s", f"see {blob}", [], [], "", "Story", "")
        self.assertIn("[image-removed]", t["description_notes"])
        self.assertNotIn(blob, t["description_notes"])


class FeatureAndKeyTests(unittest.TestCase):
    def test_resolves_notes_as_whole_token(self):
        self.assertEqual(resolve_feature_key("Notes: add checklist"), "notes")

    def test_does_not_match_substring(self):
        self.assertEqual(resolve_feature_key("Footnotes styling"), "")

    def test_resolves_multiword_alias(self):
        self.assertEqual(resolve_feature_key("Support archived content type filter"), "archive-content-type")

    def test_indexed_alias_maps_to_canonical_feature_key(self):
        self.assertEqual(canonical_feature_key("archived-content-type"), "archive-content-type")
        self.assertEqual(canonical_feature_key("notes"), "notes")

    def test_feature_test_case_prefixes(self):
        self.assertEqual(detect_feature_prefix("Notes: editor toolbar"), "TC-NOTES")
        self.assertEqual(detect_feature_prefix("Archive content type"), "TC-ARCHIVE-CONTENT-TYPE")

    def test_issue_key_validation(self):
        self.assertEqual(config.validate_issue_key(" stud-123 "), "STUD-123")
        for bad in ("../etc", "STUD-12; DROP", "123", "STUD-"):
            with self.assertRaises(ValueError):
                config.validate_issue_key(bad)


class SchemaTests(unittest.TestCase):
    def test_valid_suite(self):
        suite = _suite([_case()])
        errors, warnings = check_traceability(suite, "ac")
        self.assertEqual((errors, warnings), ([], []))

    def test_rejects_unnumbered_steps(self):
        with self.assertRaises(ValidationError):
            _suite([_case(steps="Open Notes then click")])

    def test_rejects_bad_tc_id_and_refs(self):
        with self.assertRaises(ValidationError):
            _suite([_case(tc_id="TC1")])
        with self.assertRaises(ValidationError):
            _suite([_case(refs=("REQ-1",))])

    def test_unknown_ref_and_duplicate_ids_are_errors(self):
        suite = _suite([_case(refs=("FR-01", "EC-03")), _case()])
        errors, _ = check_traceability(suite, "ac")
        self.assertTrue(any("EC-03" in e for e in errors))
        self.assertTrue(any("Duplicate tc_id" in e for e in errors))

    def test_uncovered_requirement_is_warning(self):
        suite = _suite([_case()], frs=("a", "b"))
        errors, warnings = check_traceability(suite, "ac")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, ["FR-02 is not covered by any test case"])

    def test_str_source_uses_sc_tag(self):
        suite = _suite([_case(refs=("SC-01",))])
        self.assertEqual(check_traceability(suite, "str"), ([], []))

    def test_realism_guard(self):
        self.assertTrue(unsupported_by_evidence("Verify behaviour when network error occurs", "Users create books"))
        self.assertFalse(unsupported_by_evidence("Autosave after network error", "Retry after a network error"))
        self.assertFalse(unsupported_by_evidence("Create a book", "Users create books"))

    def test_source_citation_must_match_authoritative_text(self):
        suite = _suite([_case()])
        errors = check_source_evidence(
            suite, "ac", {"acceptance_criteria": "Requirement: Users can create a book."}
        )
        self.assertEqual(errors, [])
        errors = check_source_evidence(
            suite, "ac", {"acceptance_criteria": "Users can rename a book."}
        )
        self.assertTrue(any("does not exactly match" in error for error in errors))

    def test_exact_duplicate_titles_are_flagged_not_removed(self):
        matches = find_exact_duplicates(
            _suite([_case(title="[FR-01] Create a book verifies it appears")]).test_cases,
            [{"id": "C123", "title": "Create a book verifies it appears"}],
        )
        self.assertEqual(matches, [{
            "generated_tc_id": "TC-FEATURE-001",
            "existing_case_id": "C123",
            "title": "Create a book verifies it appears",
        }])


class RenderTests(unittest.TestCase):
    story = {"key": "STUD-1", "summary": "Notes books", "feature_key": "notes", "primary_source": "ac"}

    def test_test_case_markdown(self):
        md = render_test_cases(self.story, _suite([_case()]), [], [{"tc_id": "TC-FEATURE-002", "title": "x"}])
        self.assertIn("# Test Cases: STUD-1", md)
        self.assertIn("### TC-FEATURE-001", md)
        self.assertIn("**FR-01:** Users can create a book", md)
        self.assertIn("### Source Evidence", md)
        self.assertIn("Grounding Review Flags", md)

    def test_gap_markdown(self):
        gap = GapAnalysis(requirement_summary=["Books can be created"], po_questions=["Q1: Max books?"])
        md = render_gap_analysis(self.story, gap, 0)
        self.assertIn("### Functional Gaps\n*No gaps identified.*", md)
        self.assertIn("- Q1: Max books?", md)


class StoryContextTests(unittest.TestCase):
    def test_story_context_defaults_to_no_comments_and_small_retrieval_window(self):
        issue = {
            "summary": "Notes: HTML editor",
            "issuetype": "Story",
            "status": "In Review",
            "priority": "Medium",
            "labels": [],
            "components": [],
            "acceptance_criteria_raw": "## Acceptance Criteria\n- Toolbar shows hover state",
            "steps_to_reproduce_raw": "## Steps to Reproduce\n1. Open editor",
            "description": "Background information",
        }

        with mock.patch.object(story_context.jira_client, "fetch_issue", return_value=issue), \
             mock.patch.object(story_context.jira_client, "fetch_comments") as fetch_comments, \
             mock.patch.object(story_context.retrieval, "get_product_knowledge", return_value=[{"path": "p", "snippet": "x"}], autospec=True) as get_product_knowledge, \
             mock.patch.object(story_context.retrieval, "get_automation_feature_context", return_value=[{"path": "a", "snippet": "y"}], autospec=True) as get_automation_feature_context, \
             mock.patch.object(story_context.retrieval, "get_qa_guidance", return_value=[{"path": "q", "snippet": "z"}], autospec=True) as get_qa_guidance, \
             mock.patch.object(story_context.retrieval, "get_role_context", return_value="role rules", autospec=True), \
             mock.patch.object(story_context.retrieval, "get_existing_testrail_cases", return_value=[], autospec=True):
            context = story_context.build_story_context("STUD-1")

        fetch_comments.assert_not_called()
        self.assertEqual(context["comments"], "")
        get_product_knowledge.assert_called_once_with("notes", "Notes: HTML editor", "Background information Toolbar shows hover state Open editor", top_k=2)
        get_automation_feature_context.assert_called_once_with("notes", "Notes: HTML editor", "Background information Toolbar shows hover state Open editor", top_k=2)
        get_qa_guidance.assert_called_once_with("Notes: HTML editor", "Background information Toolbar shows hover state Open editor", top_k=3)


class RetrievalTests(unittest.TestCase):
    def test_search_filtered_returns_the_next_feature_scoped_slice(self):
        docs = [
            {
                "id": f"product_{index}",
                "content": f"product chunk {index}",
                "feature_key": "notes" if index != 1 else "archive-content-type",
                "doc_domain": "product_knowledge",
                "source": "md",
                "relative_source_path": "rag/docs/product_knowledge/notes/notes.md",
            }
            for index in range(5)
        ]
        with mock.patch.object(retrieval, "search", return_value=docs) as search:
            page = retrieval.search_filtered(
                "notes editor", top_k=2, feature_key="notes",
                doc_domain="product_knowledge", path_contains="product_knowledge", offset=2,
            )
        self.assertEqual([doc["id"] for doc in page], ["product_3", "product_4"])
        self.assertGreaterEqual(search.call_args.kwargs["top_k"], 4)

    def test_product_knowledge_offset_keeps_ranked_prefix_stable(self):
        docs = [
            {
                "id": f"product_{index}",
                "content": f"Notes product chunk {index}",
                "relative_source_path": "rag/docs/product_knowledge/notes/notes.md",
                "heading": f"Section {index}",
            }
            for index in range(4)
        ]

        def ranked_prefix(query, top_k, **filters):
            return docs[:top_k]

        with mock.patch.object(retrieval, "search_filtered", side_effect=ranked_prefix) as search:
            page = retrieval.get_product_knowledge("notes", "Notes editor", top_k=2, offset=2)
        self.assertEqual([doc["id"] for doc in page], ["product_2", "product_3"])
        self.assertEqual(search.call_args.kwargs["top_k"], 4)

    def test_indexed_cypress_chunks_require_exact_repo_paths(self):
        class Doc:
            def __init__(self, doc_id, source, content):
                self.page_content = content
                self.metadata = {
                    "id": doc_id,
                    "source": str(source),
                    "type": "cypress_spec",
                }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "cypress/e2e/parallel/group-9/notes/notes.cy.js"
            unrelated = root / "cypress/e2e/parallel/group-9/ideas/ideas.cy.js"
            target.parent.mkdir(parents=True)
            unrelated.parent.mkdir(parents=True)

            class Store:
                docstore = type("DocStore", (), {"_dict": {
                    "1": Doc("notes0", target, "Notes Page Object import chunk"),
                    "2": Doc("ideas0", unrelated, "Ideas unrelated chunk"),
                }})()

            with mock.patch.object(retrieval, "load_vectorstore", return_value=Store()):
                result = retrieval.get_indexed_cypress_chunks(
                    root,
                    ["cypress/e2e/parallel/group-9/notes/notes.cy.js"],
                    "Notes page object",
                )
        self.assertEqual([chunk["path"] for chunk in result["chunks"]], [
            "cypress/e2e/parallel/group-9/notes/notes.cy.js"
        ])
        self.assertEqual(result["missing_paths"], [])

    def test_indexed_cypress_chunks_report_unindexed_required_paths(self):
        class Store:
            docstore = type("DocStore", (), {"_dict": {}})()

        with mock.patch.object(retrieval, "load_vectorstore", return_value=Store()):
            result = retrieval.get_indexed_cypress_chunks(
                Path("C:/automation"), ["cypress/support/commands.js"], "Notes API setup"
            )
        self.assertEqual(result["chunks"], [])
        self.assertEqual(result["missing_paths"], ["cypress/support/commands.js"])

    def test_cypress_file_followup_returns_only_unseen_chunks_from_exact_path(self):
        class Doc:
            def __init__(self, doc_id, path, content):
                self.page_content = content
                self.metadata = {"id": doc_id, "repo_path": path, "type": "page_object"}

        target = "cypress/e2e/kapost/pageObjects/crowdsourcingPage.cy.js"
        unrelated = "cypress/e2e/kapost/pageObjects/otherPage.cy.js"
        docs = {
            str(index): Doc(f"target_chunk{index}", target, f"target method {index}")
            for index in range(4)
        }
        docs["unrelated"] = Doc("other_chunk0", unrelated, "unrelated method")

        class Store:
            docstore = type("DocStore", (), {"_dict": docs})()

        with mock.patch.object(retrieval, "load_vectorstore", return_value=Store()):
            first = retrieval.get_indexed_cypress_file_chunks(
                Path("C:/automation"), target, exclude_chunk_ids=["target_chunk0"], limit=10
            )
            second = retrieval.get_indexed_cypress_file_chunks(
                Path("C:/automation"), target,
                exclude_chunk_ids=["target_chunk0", *[chunk["id"] for chunk in first["chunks"]]],
            )

        self.assertEqual([chunk["id"] for chunk in first["chunks"]], ["target_chunk1", "target_chunk2"])
        self.assertEqual(first["total_chunks"], 4)
        self.assertEqual(first["remaining_chunks"], 3)
        self.assertEqual([chunk["id"] for chunk in second["chunks"]], ["target_chunk3"])

    def test_search_deduplicates_repeated_faiss_document_ids(self):
        class Doc:
            page_content = "case chunk"
            metadata = {"id": "testrail_123_chunk0", "source": "testrail"}

        class Store:
            def similarity_search(self, query, k):
                return [Doc(), Doc()]

        with mock.patch.object(retrieval, "load_vectorstore", return_value=Store()):
            docs = retrieval.search("related test case", top_k=10)
        self.assertEqual(len(docs), 1)

    def test_existing_cases_are_reassembled_and_filtered_to_feature(self):
        chunks = {
            "C123": [
                {"id": "testrail_123_chunk0", "content": "TestRail Case: 123\nTitle: Notes editor saves a page\n"},
                {"id": "testrail_123_chunk1", "content": "Steps:\n1. Edit the note\nExpected Result:\nThe note is saved"},
            ],
            "C456": [
                {"id": "testrail_456_chunk0", "content": "TestRail Case: 456\nTitle: Archive a content type\nSteps:\n1. Archive it"},
            ],
        }
        hits = [
            {"id": "testrail_123_chunk1", "content": "step chunk"},
            {"id": "testrail_456_chunk0", "content": "archive chunk"},
        ]
        with (
            mock.patch.object(retrieval, "search_filtered", return_value=hits),
            mock.patch.object(retrieval, "_all_testrail_case_chunks", return_value=chunks),
        ):
            cases = retrieval.get_existing_testrail_cases("STUD-1", "Notes editor", "notes")
        self.assertEqual([case["id"] for case in cases], ["C123"])
        self.assertEqual(cases[0]["title"], "Notes editor saves a page")
        self.assertIn("The note is saved", cases[0]["content"])

    def test_existing_testrail_cases_support_offset_pages(self):
        hits = [
            {"id": f"testrail_{case_id}_chunk0", "content": "matched chunk"}
            for case_id in (123, 456, 789)
        ]
        chunks = {
            f"C{case_id}": [{
                "id": f"testrail_{case_id}_chunk0",
                "content": f"TestRail Case: {case_id}\nTitle: Notes editor behavior {case_id}\nSteps:\n1. Open Notes",
            }]
            for case_id in (123, 456, 789)
        }
        with (
            mock.patch.object(retrieval, "search_filtered", return_value=hits),
            mock.patch.object(retrieval, "_all_testrail_case_chunks", return_value=chunks),
        ):
            page = retrieval.get_existing_testrail_cases(
                "STUD-1", "Notes editor", "notes", top_k=1, offset=1
            )
        self.assertEqual([case["id"] for case in page], ["C456"])


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "output"
        self.out.mkdir()
        self.target_dir = self.root / "cypress" / "e2e" / "parallel" / "group-9" / "notes"
        self.target_dir.mkdir(parents=True)
        self.case_ids = ["TC-NOTES-001"]
        self.content = (
            "describe('Notes', () => {\n"
            "  // TC-NOTES-001\n"
            "  it('creates a book', () => {\n"
            "    notesPage.addBook()\n"
            "    cy.contains('New Book').should('be.visible')\n"
            "  })\n"
            "})\n"
        )
        self.artifact_path = self.out / "STUD-1-test-cases.json"
        self.artifact_path.write_text(
            json.dumps({"test_cases": [{"tc_id": self.case_ids[0]}]}), encoding="utf-8"
        )
        self.patches = [
            mock.patch.object(automation.config, "AUTOMATION_REPO_ROOT", self.root),
            mock.patch.object(automation.config, "OUTPUT_DIR", self.out),
            mock.patch.object(
                automation, "feature_target_directory", return_value="cypress/e2e/parallel/group-9/notes"
            ),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in self.patches:
            patcher.stop()
        self.tmp.cleanup()

    def test_spec_validation_requires_tests_traceability_and_pom_selectors(self):
        self.assertEqual(automation.validate_spec_content(self.content, self.case_ids), [])
        errors = automation.validate_spec_content(
            "describe('x', () => { it('x', () => cy.get('.secret').click()) })", self.case_ids
        )
        self.assertTrue(any("cy.get" in error for error in errors))
        self.assertTrue(any("traceability IDs" in error for error in errors))

    def test_automation_context_lists_cases_when_user_has_not_selected(self):
        result = automation.build_automation_context(
            "STUD-1", {"story": {"feature_key": "notes"}}, []
        )
        self.assertTrue(result["case_selection_required"])
        self.assertEqual(result["available_test_cases"][0]["tc_id"], "TC-NOTES-001")

    def test_repository_context_uses_feature_paths_and_sanitizes_credentials(self):
        notes_dir = self.root / "cypress" / "e2e" / "parallel" / "group-9" / "notes"
        other_dir = self.root / "cypress" / "e2e" / "parallel" / "group-9" / "ideas"
        page_object = self.root / "cypress" / "e2e" / "kapost" / "pageObjects" / "notesPage" / "notesPage.cy.js"
        notes_dir.mkdir(parents=True, exist_ok=True)
        other_dir.mkdir(parents=True)
        page_object.parent.mkdir(parents=True)
        (notes_dir / "notes.cy.js").write_text(
            "import notesPage from '../../../kapost/pageObjects/notesPage/notesPage.cy'\n"
            "describe('Notes', () => { it('works', () => notesPage.openNotes()) })",
            encoding="utf-8",
        )
        (other_dir / "ideas.cy.js").write_text("describe('Ideas', () => { it('works', () => {}) })", encoding="utf-8")
        page_object.write_text(
            "// Notes books editor methods\nexport const token = 'hardcoded-secret-value';",
            encoding="utf-8",
        )
        commands_path = self.root / "cypress" / "support" / "commands.js"
        commands_path.parent.mkdir(parents=True)
        commands_path.write_text(
            "Cypress.Commands.add('createNotesBookApi', () => cy.request('/notes/books'))\n"
            "Cypress.Commands.add('unrelatedCommand', () => cy.visit('/ideas'))\n",
            encoding="utf-8",
        )
        feature_doc = (
            "## Spec Map\nAll primary specs: `cypress/e2e/parallel/group-9/notes/`\n"
            "## Page Object Map\n- `cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js`\n"
            "## Custom Command Usage\n- `createNotesBookApi(...)`\n"
        )
        def indexed_chunks(repo_root, paths, query, **kwargs):
            chunks = []
            for index, path in enumerate(paths):
                if path.endswith("notes.cy.js"):
                    content, doc_type = "RAG chunk: Notes spec import notesPage", "automation_spec"
                elif path.endswith("notesPage.cy.js"):
                    content, doc_type = "RAG chunk: Notes books token = 'hardcoded-secret-value'", "automation_page_object"
                elif path.endswith("commonObjectsAndUtils.cy.js"):
                    content, doc_type = "RAG chunk: common locator utility", "cypress_page_object"
                elif path.endswith("commands.js"):
                    content, doc_type = "RAG chunk: Cypress.Commands.add createNotesBookApi", "cypress_command"
                else:
                    content, doc_type = "RAG chunk: helper", "automation_data_helper"
                chunks.append({
                    "id": f"doc-{index}", "path": path, "type": doc_type,
                    "snippet": content, "relevance_score": 4,
                })
            return {"chunks": chunks, "missing_paths": []}

        with mock.patch.object(retrieval, "get_indexed_cypress_chunks", side_effect=indexed_chunks):
            context = automation.get_cypress_repository_context(
                "notes", "Notes books", feature_doc=feature_doc
            )
        self.assertEqual([p["path"] for p in context["specs"]], ["cypress/e2e/parallel/group-9/notes/notes.cy.js"])
        self.assertTrue(any("notesPage.cy.js" in p["path"] for p in context["page_objects"]))
        self.assertTrue(any("<REDACTED>" in p["content"] for p in context["page_objects"]))
        self.assertTrue(any("createNotesBookApi" in p["content"] for p in context["custom_commands"]))
        self.assertFalse(any("ideas.cy.js" in p["path"] for p in context["specs"]))
        self.assertTrue(all("RAG chunk:" in p["content"] for group in ("specs", "page_objects", "custom_commands") for p in context[group]))
        scope = context["scope"][0]
        self.assertEqual(scope["page_objects_imported_by_selected_specs"], [
            "cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js"
        ])
        self.assertIn("commands.js", scope["shared_context"][-1])

    def test_repository_context_fails_when_required_file_has_no_rag_chunks(self):
        feature_doc = "## Spec Map\n`cypress/e2e/parallel/group-9/notes/`\n"
        spec_path = "cypress/e2e/parallel/group-9/notes/notes.cy.js"
        page_path = "cypress/e2e/kapost/pageObjects/notesPage/notesPage.cy.js"
        with (
            mock.patch.object(automation, "_feature_page_object_paths", return_value=[page_path]),
            mock.patch.object(automation, "_specs_importing_page_objects", return_value=(
                [{"path": spec_path, "resolved_import_paths": []}], [page_path]
            )),
            mock.patch.object(retrieval, "get_indexed_cypress_chunks", return_value={
                "chunks": [], "missing_paths": ["cypress/support/commands.js"]
            }),
        ):
            with self.assertRaisesRegex(automation.AutomationError, "missing required Cypress chunks"):
                automation.get_cypress_repository_context(
                    "notes", "notes page", feature_doc=feature_doc
                )

    def test_page_object_selection_keeps_all_matching_objects_and_excludes_unrelated(self):
        settings_path = "cypress/e2e/kapost/pageObjects/settingsPages/contentTypePage.cy.js"
        catalogue_path = "cypress/e2e/kapost/pageObjects/contentPages/contentCatalogue.cy.js"
        ideas_path = "cypress/e2e/kapost/pageObjects/ideasPages/ideaDetailsPage.cy.js"
        for relative, source in (
            (settings_path, "// Archive and unarchive content type settings actions"),
            (catalogue_path, "// Hide archived content types from content catalogue creation dropdown"),
            (ideas_path, "// Idea approval and submit methods"),
        ):
            target = self.root / Path(relative.replace("/", "\\"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        feature_doc = (
            "## Page Object Map\n"
            f"- `{settings_path}`\n  - Archive/unarchive content type settings actions.\n"
            f"- `{catalogue_path}`\n  - Hide archived content type in content catalogue dropdown.\n"
            f"- `{ideas_path}`\n  - Idea approval and submit workflows.\n"
        )
        selected = automation._feature_page_object_paths(
            feature_doc,
            "Archived content type hidden from creation dropdown",
            self.root,
        )
        self.assertEqual(set(selected), {settings_path, catalogue_path})

        other_page_object = self.root / "cypress/e2e/kapost/pageObjects/settingsPages/contentTypeActions.cy.js"
        other_page_object.parent.mkdir(parents=True, exist_ok=True)
        other_page_object.write_text("// Content type archive actions", encoding="utf-8")
        multi_spec = self.root / "cypress/e2e/parallel/group-1/archive/multiPageObject.cy.js"
        multi_spec.parent.mkdir(parents=True, exist_ok=True)
        multi_spec.write_text(
            "import settings from '../../../kapost/pageObjects/settingsPages/contentTypePage.cy'\n"
            "import actions from '../../../kapost/pageObjects/settingsPages/contentTypeActions.cy'\n"
            "describe('archive',()=>{it('archives content type',()=>{})})",
            encoding="utf-8",
        )
        multi_matches, imported = automation._specs_importing_page_objects(
            self.root, [settings_path, "cypress/e2e/kapost/pageObjects/settingsPages/contentTypeActions.cy.js"],
            "archive content type",
        )
        self.assertEqual([item["path"] for item in multi_matches], [
            "cypress/e2e/parallel/group-1/archive/multiPageObject.cy.js"
        ])
        self.assertEqual(set(imported), {
            settings_path,
            "cypress/e2e/kapost/pageObjects/settingsPages/contentTypeActions.cy.js",
        })

    def test_import_parser_ignores_commented_examples(self):
        source = (
            "import notesPage from '../pageObjects/notesPage/notesPage.cy'\n"
            "const shared = require('../pageObjects/commonObjectsAndUtils.cy.js')\n"
            "// import ideasPage from '../pageObjects/ideasPage.cy'\n"
            "/* const stale = require('../pageObjects/archivePage.cy') */\n"
        )
        self.assertEqual(automation._module_imports(source), [
            "../pageObjects/notesPage/notesPage.cy",
            "../pageObjects/commonObjectsAndUtils.cy.js",
        ])

    def test_writer_requires_approval_and_never_overwrites(self):
        not_approved = automation.create_spec_file(
            "STUD-1", "notes", "notesGenerated.cy.js", self.content, self.case_ids, False
        )
        self.assertFalse(not_approved["ok"])
        target = self.target_dir / "notesGenerated.cy.js"
        self.assertFalse(target.exists())

        created = automation.create_spec_file(
            "STUD-1", "notes", "notesGenerated.cy.js", self.content, self.case_ids, True
        )
        self.assertTrue(created["ok"], created)
        self.assertEqual(created["relative_path"], "cypress/e2e/parallel/group-9/notes/notesGenerated.cy.js")
        self.assertEqual(target.read_text(encoding="utf-8"), self.content)

        collision = automation.create_spec_file(
            "STUD-1", "notes", "notesGenerated.cy.js", self.content, self.case_ids, True
        )
        self.assertFalse(collision["ok"])
        self.assertIn("Refusing to overwrite", collision["error"])
        self.assertEqual(target.read_text(encoding="utf-8"), self.content)

    def test_writer_rejects_unsafe_filename_unknown_case_and_credentials(self):
        bad_name = automation.create_spec_file(
            "STUD-1", "notes", "..\\escape.cy.js", self.content, self.case_ids, True
        )
        self.assertFalse(bad_name["ok"])
        unknown_case = automation.create_spec_file(
            "STUD-1", "notes", "new.cy.js", self.content, ["TC-NOTES-999"], True
        )
        self.assertFalse(unknown_case["ok"])
        self.assertIn("not in the saved artifact", unknown_case["error"])
        secret_content = self.content.replace("notesPage.addBook()", "const password = 'hardcoded-secret-value'")
        secret = automation.create_spec_file(
            "STUD-1", "notes", "secret.cy.js", secret_content, self.case_ids, True
        )
        self.assertFalse(secret["ok"])
        self.assertTrue(any("hard-coded credential" in error for error in secret["errors"]))

    def test_jira_preview_saves_only_to_local_output_after_approval(self):
        content = self.content.replace("TC-NOTES-001", "TC-FEATURE-001")
        artifact = {
            "story": {"feature_key": "notes"},
            "test_cases": [{"tc_id": "TC-FEATURE-001"}],
        }
        self.artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        refused = automation.save_cypress_preview(
            "jira", "STUD-1", "notes.cy.js", content, ["TC-FEATURE-001"], False
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(list((self.out / "automation").glob("**/*")) if (self.out / "automation").exists() else [], [])

        saved = automation.save_cypress_preview(
            "jira", "STUD-1", "notes.cy.js", content, ["TC-FEATURE-001"], True
        )
        self.assertTrue(saved["ok"], saved)
        self.assertFalse(saved["repo_modified"])
        self.assertTrue(Path(saved["saved_path"]).is_relative_to(self.out))
        self.assertTrue(Path(saved["saved_path"]).exists())

    def test_testrail_preview_requires_source_id_and_refuses_overwrite(self):
        case = {
            "case_id": "C12345", "title": "Notes editor creates a page", "section_name": "Notes",
            "preconditions": "", "legacy_expected_result": "", "steps": [], "references": [],
        }
        content = "describe('Notes',()=>{it('C12345 creates a page',()=>{notesPage.addPage()})})"
        with mock.patch.object(automation, "fetch_case", return_value=case):
            omitted_id = automation.save_cypress_preview(
                "testrail", "C12345", "case.cy.js", "describe('x',()=>{it('TC-OTHER-001 x',()=>{})})",
                ["TC-OTHER-001"], True,
            )
            self.assertFalse(omitted_id["ok"])
            self.assertIn("must include", omitted_id["error"])

            saved = automation.save_cypress_preview(
                "testrail", "C12345", "case.cy.js", content, ["C12345"], True
            )
            self.assertTrue(saved["ok"], saved)
            self.assertFalse(saved["repo_modified"])
            collision = automation.save_cypress_preview(
                "testrail", "C12345", "case.cy.js", content, ["C12345"], True
            )
        self.assertFalse(collision["ok"])
        self.assertIn("Refusing to overwrite", collision["error"])

    def test_testrail_feature_resolution_uses_case_evidence_and_rejects_conflicts(self):
        case = {
            "case_id": "C12345", "title": "Notes editor creates a page", "section_name": "Notes",
            "preconditions": "", "legacy_expected_result": "", "steps": [], "references": [],
        }
        feature, warnings = automation._resolve_testrail_case_feature(case)
        self.assertEqual(feature, "notes")
        self.assertEqual(warnings, [])
        with self.assertRaises(automation.AutomationError):
            automation._resolve_testrail_case_feature(case, "archive-content-type")

    def test_testrail_feature_resolution_uses_linked_jira_and_requires_disambiguation(self):
        case = {
            "case_id": "C12345", "title": "Editor saves a page", "section_name": "",
            "preconditions": "", "legacy_expected_result": "", "steps": [],
            "references": ["STUD-1"],
        }
        with mock.patch.object(automation, "fetch_issue", return_value={
            "summary": "Notes: page autosave", "description": ""
        }):
            feature, warnings = automation._resolve_testrail_case_feature(case)
        self.assertEqual(feature, "notes")
        self.assertEqual(warnings, [])

        ambiguous = {**case, "references": ["STUD-1", "STUD-2"]}
        with mock.patch.object(automation, "fetch_issue", side_effect=[
            {"summary": "Notes: page autosave", "description": ""},
            {"summary": "Archive content type", "description": ""},
        ]):
            with self.assertRaises(automation.AutomationError):
                automation._resolve_testrail_case_feature(ambiguous)

    def test_build_testrail_context_preserves_structured_steps_and_target(self):
        case = {
            "case_id": "C12345", "title": "Notes editor creates a page", "section_name": "Notes",
            "preconditions": "User has opened Notes", "legacy_expected_result": "",
            "steps": [{"action": "Select Add Page", "expected": "A new page is shown"}],
            "references": [],
        }
        with (
            mock.patch.object(automation, "fetch_case", return_value=case),
            mock.patch.object(automation, "_feature_doc", return_value=("Feature notes", "notes-feature.md")),
            mock.patch.object(automation, "feature_target_directory", return_value="cypress/e2e/parallel/group-9/notes"),
            mock.patch.object(automation, "get_cypress_repository_context", return_value={
                "specs": [], "page_objects": [], "custom_commands": [], "data_helpers": [], "scope": []
            }),
            mock.patch.object(automation, "_GUIDELINES_PATH") as guidelines_path,
        ):
            guidelines_path.exists.return_value = True
            guidelines_path.read_text.return_value = "General Cypress rules"
            context = automation.build_testrail_automation_context("C12345")
        self.assertEqual(context["source_id"], "C12345")
        self.assertEqual(context["story"]["feature_key"], "notes")
        self.assertEqual(context["target_spec_directory"], "cypress/e2e/parallel/group-9/notes")
        self.assertIn("A new page is shown", context["selected_test_cases"][0]["steps"])

    def test_testrail_case_id_and_step_normalization(self):
        self.assertEqual(normalize_case_id("c12345"), ("12345", "C12345"))
        with self.assertRaises(TestRailError):
            normalize_case_id("../../123")
        with mock.patch("core.testrail_client._get", side_effect=[
            {
                "id": 12345, "title": "<b>Notes</b>", "section_id": 7, "suite_id": 2,
                "refs": "STUD-123, STUD-124", "custom_preconds": "<p>Logged in</p>",
                "custom_steps_separated": [
                    {"content": "<b>Click</b> Add Page", "expected": "Page opens<br>"},
                    {"content": "Enter text", "expected": "Text is saved"},
                ],
            },
            {"name": "Notes"},
        ]):
            result = fetch_case("C12345")
        self.assertEqual(result["case_id"], "C12345")
        self.assertEqual(result["title"], "Notes")
        self.assertEqual(result["section_name"], "Notes")
        self.assertEqual(result["references"], ["STUD-123", "STUD-124"])
        self.assertEqual(result["steps"][0], {"action": "Click Add Page", "expected": "Page opens"})

    def test_testrail_http_uses_basic_auth_and_requires_https(self):
        class Response:
            status_code = 200
            ok = True

            @staticmethod
            def json():
                return {"id": 12345, "title": "Notes"}

        with (
            mock.patch.object(config, "TESTRAIL_URL", "https://testrail.example.com"),
            mock.patch.object(config, "TESTRAIL_USER", "qa@example.com"),
            mock.patch.object(config, "TESTRAIL_TOKEN", "hidden-test-token"),
            mock.patch("core.testrail_client.requests.get", return_value=Response()) as request,
        ):
            from core.testrail_client import _get
            result = _get("get_case/12345")
        self.assertEqual(result["id"], 12345)
        self.assertEqual(request.call_args.kwargs["auth"], ("qa@example.com", "hidden-test-token"))
        self.assertTrue(request.call_args.args[0].startswith("https://"))

        with (
            mock.patch.object(config, "TESTRAIL_URL", "http://testrail.example.com"),
            mock.patch.object(config, "TESTRAIL_USER", "qa@example.com"),
            mock.patch.object(config, "TESTRAIL_TOKEN", "hidden-test-token"),
            mock.patch("core.testrail_client.requests.get") as request,
        ):
            with self.assertRaises(TestRailError):
                _get("get_case/12345")
        request.assert_not_called()

    def test_testrail_spec_writer_requires_approval_and_refuses_overwrite(self):
        case = {
            "case_id": "C12345", "title": "Notes editor creates a page", "section_name": "Notes",
            "preconditions": "", "legacy_expected_result": "", "steps": [], "references": [],
        }
        spec = "describe('Notes',()=>{it('C12345 creates a page',()=>{notesPage.addPage()})})"
        with mock.patch.object(automation, "fetch_case", return_value=case):
            refused = automation.create_testrail_spec_file("C12345", "case.cy.js", spec, False)
            self.assertFalse(refused["ok"])
            with mock.patch.object(
                automation, "feature_target_directory", return_value="cypress/e2e/parallel/group-9/notes"
            ):
                created = automation.create_testrail_spec_file("C12345", "case.cy.js", spec, True)
                self.assertTrue(created["ok"], created)
                collision = automation.create_testrail_spec_file("C12345", "case.cy.js", spec, True)
        self.assertFalse(collision["ok"])
        self.assertIn("Refusing to overwrite", collision["error"])


class ServerSaveTests(unittest.TestCase):
    """Exercises the save tools with a mocked story context (no Jira/FAISS)."""

    context = {
        "story": {
            "key": "STUD-1", "summary": "Notes books", "feature_key": "notes",
            "feature_prefix": "TC-FEATURE", "primary_source": "ac",
        },
        "requirements": ["Users can create a book"],
        "steps_to_reproduce": [], "background_dev_notes": "", "comments": "",
        "source_text": {"acceptance_criteria": "Requirement: Users can create a book"},
        "existing_testrail_cases": [],
        "product_knowledge": [], "warnings": [],
    }

    def setUp(self):
        import mcp_server
        self.server = mcp_server
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(config, "OUTPUT_DIR", Path(self.tmp.name)),
            mock.patch.object(mcp_server, "_context", return_value=self.context),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_save_writes_json_and_markdown_and_flags_ungrounded(self):
        suite = _suite([
            _case(),
            _case("TC-FEATURE-002", title="[FR-01] Book creation during network error shows retry"),
        ])
        result = self.server.save_test_cases("stud-1", suite)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["test_case_count"], 2)
        self.assertEqual(result["grounding_review_flags"][0]["tc_id"], "TC-FEATURE-002")
        payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["story"]["key"], "STUD-1")
        self.assertEqual(len(payload["test_cases"]), 2)
        self.assertTrue(Path(result["markdown_path"]).name == "STUD-1-test-cases.md")

    def test_save_returns_errors_instead_of_writing(self):
        result = self.server.save_test_cases("STUD-1", _suite([_case(refs=("FR-09",))]))
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_save_rejects_fabricated_source_citation(self):
        suite = _suite([_case()])
        suite.requirements_brief.source_evidence["FR-01"][0].quote = "Users can delete every book"
        result = self.server.save_test_cases("STUD-1", suite)
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not exactly match" in e for e in result["errors"]))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_invalid_key_rejected(self):
        self.assertFalse(self.server.save_test_cases("../x", _suite([_case()]))["ok"])

    def test_save_gap_analysis(self):
        gap = GapAnalysis(
            requirement_summary=["Books can be created"],
            non_functional_gaps=["Performance under high load is undefined"],
        )
        result = self.server.save_gap_analysis("STUD-1", gap)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["grounding_review_flags"]), 1)
        md = Path(result["markdown_path"]).read_text(encoding="utf-8")
        self.assertIn("Grounding Review Flags", md)
        self.assertIn("Performance under high load", md)


class AutomationContextPagingTests(unittest.TestCase):
    def setUp(self):
        import mcp_server
        self.server = mcp_server
        self.previous_cache = mcp_server._automation_context_cache.copy()
        mcp_server._automation_context_cache.clear()

    def tearDown(self):
        self.server._automation_context_cache.clear()
        self.server._automation_context_cache.update(self.previous_cache)

    def test_testrail_context_returns_compact_manifest_not_all_content(self):
        context = {
            "source_case": {"case_id": "C12345", "title": "Notes", "step_count": 60},
            "story": {"key": "C12345", "feature_key": "notes"},
            "target_spec_directory": "cypress/e2e/parallel/group-9/notes",
            "warnings": [],
            "selected_test_cases": [{"steps": "step text" * 1000}],
            "general_guidelines": "guideline" * 1000,
            "feature_context": "feature" * 1000,
            "product_knowledge": [{"snippet": "product" * 100}],
            "role_permissions": "role" * 100,
            "existing_specs": [{"content": "spec" * 1000} for _ in range(6)],
            "page_objects": [{"content": "page object" * 1000} for _ in range(4)],
            "custom_commands": [{"content": "commands" * 1000} for _ in range(2)],
            "data_helpers": [],
            "automation_scope": [{"selected_spec_count": 6}],
        }
        with mock.patch.object(self.server, "build_testrail_automation_context", return_value=context):
            result = self.server.get_testrail_automation_context("C12345")
        self.assertTrue(result["ok"])
        self.assertLess(len(json.dumps(result)), 3000)
        self.assertNotIn("existing_specs", result)
        self.assertIn("context_id", result)
        self.assertIn("existing_specs", result["sections"])

    def test_context_page_caps_text_and_paginates_lists(self):
        context_id = "test-context"
        self.server._automation_context_cache[context_id] = {
            "selected_test_cases": [{"steps": "x"}],
            "general_guidelines": "A" * 4200,
            "feature_context": "",
            "product_knowledge": [],
            "role_permissions": "",
            "existing_specs": [{"path": f"spec-{i}", "content": "x" * 900} for i in range(5)],
            "page_objects": [], "custom_commands": [], "data_helpers": [], "automation_scope": [],
        }
        text_page = self.server.get_testrail_automation_context_page(
            context_id, "general_guidelines", max_chars=10000
        )
        self.assertEqual(len(text_page["content"]), 1800)
        self.assertEqual(text_page["next_offset"], 1800)

        first = self.server.get_testrail_automation_context_page(
            context_id, "existing_specs", offset=0, limit=10
        )
        second = self.server.get_testrail_automation_context_page(
            context_id, "existing_specs", offset=first["next_offset"], limit=10
        )
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(len(second["items"]), 2)
        self.assertEqual(first["next_offset"], 2)

    def test_context_page_reports_expired_context(self):
        result = self.server.get_testrail_automation_context_page("missing", "existing_specs")
        self.assertFalse(result["ok"])
        self.assertIn("expired", result["error"])

    def test_jira_automation_context_gets_context_id_for_file_followups(self):
        context = {
            "story": {"key": "STUD-1", "summary": "Notes", "feature_key": "notes"},
            "target_spec_directory": "cypress/e2e/parallel/group-9/notes",
            "existing_specs": [], "page_objects": [], "custom_commands": [],
            "data_helpers": [], "automation_scope": [],
        }
        with (
            mock.patch.object(self.server, "_context", return_value={"story": {}}),
            mock.patch.object(self.server, "build_automation_context", return_value=context),
        ):
            result = self.server.get_automation_context("STUD-1", ["TC-NOTES-001"])
        self.assertTrue(result["ok"])
        self.assertIn(result["context_id"], self.server._automation_context_cache)

    def test_jira_automation_context_returns_compact_manifest_and_pages_sections(self):
        context = {
            "story": {"key": "STUD-1", "summary": "Notes", "feature_key": "notes"},
            "target_spec_directory": "cypress/e2e/parallel/group-9/notes",
            "selected_test_cases": [{"tc_id": f"TC-NOTES-{index:03d}", "steps": "step " * 100} for index in range(1, 4)],
            "general_guidelines": "guideline " * 1500,
            "feature_context": "feature context " * 700,
            "product_knowledge": [{"snippet": "product " * 200}],
            "role_permissions": "role guidance",
            "existing_specs": [],
            "page_objects": [{"path": f"notesPage{index}.cy.js", "content": "chunk " * 250} for index in range(5)],
            "custom_commands": [], "data_helpers": [], "automation_scope": [{"scope": "notes"}],
        }
        with (
            mock.patch.object(self.server, "_context", return_value={"story": context["story"]}),
            mock.patch.object(self.server, "build_automation_context", return_value=context),
        ):
            result = self.server.get_automation_context("STUD-1", ["TC-NOTES-001"])

        self.assertTrue(result["ok"])
        self.assertLess(len(json.dumps(result)), 3000)
        self.assertEqual(result["page_tool"], "get_automation_context_page")
        self.assertNotIn("page_objects", result)
        self.assertEqual(result["sections"]["page_objects"]["count"], 5)

        page = self.server.get_automation_context_page(
            result["context_id"], "page_objects", limit=20
        )
        cases = self.server.get_automation_context_page(
            result["context_id"], "test_case", limit=20
        )
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["next_offset"], 2)
        self.assertEqual(len(cases["items"]), 2)
        self.assertEqual(cases["next_offset"], 2)

    def test_file_followups_are_exact_path_bounded_and_reject_unscoped_paths(self):
        context_id = "file-followup-context"
        file_path = "cypress/e2e/kapost/pageObjects/crowdsourcingPage.cy.js"
        self.server._automation_context_cache[context_id] = {
            "existing_specs": [],
            "page_objects": [
                {"path": file_path, "chunk_id": "crowdsourcing_chunk0", "content": "initial one"},
                {"path": file_path, "chunk_id": "crowdsourcing_chunk1", "content": "initial two"},
            ],
            "custom_commands": [], "data_helpers": [],
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch.object(config, "AUTOMATION_REPO_ROOT", Path(temp)),
            mock.patch.object(retrieval, "get_indexed_cypress_file_chunks", side_effect=[
                {"chunks": [{
                    "id": "crowdsourcing_chunk2", "path": file_path, "type": "page_object",
                    "snippet": "password = 'sensitive-test-value'", "relevance_score": 0,
                }], "total_chunks": 4, "remaining_chunks": 2},
                {"chunks": [{
                    "id": "crowdsourcing_chunk3", "path": file_path, "type": "page_object",
                    "snippet": "final method", "relevance_score": 0,
                }], "total_chunks": 4, "remaining_chunks": 1},
            ]) as get_chunks,
        ):
            denied = self.server.get_automation_file_chunks(context_id, "cypress/other/file.cy.js")
            first = self.server.get_automation_file_chunks(context_id, file_path)
            second = self.server.get_automation_file_chunks(context_id, file_path)
            limited = self.server.get_automation_file_chunks(context_id, file_path)

        self.assertFalse(denied["ok"])
        self.assertEqual([chunk["chunk_id"] for chunk in first["chunks"]], ["crowdsourcing_chunk2"])
        self.assertIn("<REDACTED>", first["chunks"][0]["content"])
        self.assertNotIn("sensitive-test-value", first["chunks"][0]["content"])
        self.assertEqual([chunk["chunk_id"] for chunk in second["chunks"]], ["crowdsourcing_chunk3"])
        self.assertFalse(second["has_more"])
        self.assertFalse(limited["ok"])
        self.assertIn("limit reached", limited["error"])
        self.assertEqual(get_chunks.call_count, 2)
        first_excluded = get_chunks.call_args_list[0].kwargs["exclude_chunk_ids"]
        second_excluded = get_chunks.call_args_list[1].kwargs["exclude_chunk_ids"]
        self.assertEqual(first_excluded, ["crowdsourcing_chunk0", "crowdsourcing_chunk1"])
        self.assertIn("crowdsourcing_chunk2", second_excluded)


class StoryContextPagingTests(unittest.TestCase):
    def setUp(self):
        import mcp_server
        self.server = mcp_server
        self.previous_cache = mcp_server._story_context_cache.copy()
        self.previous_followups = mcp_server._story_context_followup_calls.copy()
        mcp_server._story_context_cache.clear()
        mcp_server._story_context_followup_calls.clear()

    def tearDown(self):
        self.server._story_context_cache.clear()
        self.server._story_context_cache.update(self.previous_cache)
        self.server._story_context_followup_calls.clear()
        self.server._story_context_followup_calls.update(self.previous_followups)

    def test_story_context_returns_context_id_for_followups(self):
        context = {
            "story": {"key": "STUD-1", "summary": "Notes editor", "feature_key": "notes"},
            "product_knowledge": [], "source_text": {},
        }
        with (
            mock.patch.object(self.server, "_context", return_value=context),
            mock.patch.object(retrieval, "get_product_knowledge", return_value=[{"id": "p1"}]),
        ):
            result = self.server.get_story_context("STUD-1")
            self.server.get_more_story_context(result["context_id"], "product_knowledge")
        self.assertTrue(result["ok"])
        self.assertIn(result["context_id"], self.server._story_context_cache)
        self.assertEqual(context["product_knowledge"], [])

    def test_story_context_followups_are_source_scoped_and_bounded(self):
        context_id = "story-context-test"
        self.server._story_context_cache[context_id] = {
            "story": {"key": "STUD-1", "summary": "Notes editor", "feature_key": "notes"},
            "source_text": {"acceptance_criteria": "Users can edit notes"},
            "product_knowledge": [{"id": "product_0", "snippet": "Initial context"}],
            "existing_testrail_cases": [],
        }
        with mock.patch.object(retrieval, "get_product_knowledge", side_effect=[
            [{"id": "product_1", "snippet": "More context 1"}],
            [{"id": "product_2", "snippet": "More context 2"}],
        ]) as get_product:
            first = self.server.get_more_story_context(context_id, "product_knowledge")
            second = self.server.get_more_story_context(context_id, "product_knowledge")
            limited = self.server.get_more_story_context(context_id, "product_knowledge")

        self.assertTrue(first["ok"])
        self.assertEqual(first["offset"], 1)
        self.assertEqual(first["followup_pages_remaining"], 1)
        self.assertEqual(second["offset"], 2)
        self.assertEqual(second["followup_pages_remaining"], 0)
        self.assertFalse(limited["ok"])
        self.assertIn("limit reached", limited["error"])
        self.assertEqual(get_product.call_count, 2)
        self.assertEqual(get_product.call_args_list[0].kwargs["offset"], 1)
        self.assertEqual(get_product.call_args_list[1].kwargs["offset"], 2)

    def test_story_context_followups_reject_unsupported_sources(self):
        self.server._story_context_cache["story-context-test"] = {"story": {}}
        result = self.server.get_more_story_context("story-context-test", "comments")
        self.assertFalse(result["ok"])
        self.assertIn("Unsupported source", result["error"])


if __name__ == "__main__":
    unittest.main()
