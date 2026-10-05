from pptx import Presentation
from pptx.util import Pt


def _set_notes(slide, text: str) -> None:
    notes = slide.notes_slide
    notes.notes_text_frame.text = text


def _add_title(prs: Presentation, title: str, subtitle: str, notes: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle
    _set_notes(slide, notes)


def _add_dense_slide(prs: Presentation, title: str, lines: list[str], notes: str = "") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    tf = slide.shapes.placeholders[1].text_frame
    tf.clear()
    tf.word_wrap = True

    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.level = 0
        p.font.size = Pt(16)
    _set_notes(slide, notes)


def build(out_path: str) -> None:
    prs = Presentation()

    _add_title(
        prs,
        "QA Intelligence Hub - Private Reference Deck",
        "Detailed script for presenter use only",
        "Use this deck as your speaker cheat sheet. Read verbatim where needed.",
    )

    _add_dense_slide(
        prs,
        "How To Use This Deck",
        [
            "Purpose: Keep this open privately while presenting the public walkthrough deck.",
            "Each slide contains detailed narrative you can read directly.",
            "Use the bold sequence: Problem -> Architecture -> Retrieval -> Generation -> Guardrails -> Demo -> Q&A.",
            "If interrupted, jump to Q&A slides and resume with Demo Summary slide.",
            "Time goal: 45 mins total; main demo segment should be 12-15 mins.",
        ],
    )

    _add_dense_slide(
        prs,
        "Opening Script (Read This)",
        [
            "Today I am showing a QA Intelligence tool that converts Jira stories into grounded test assets.",
            "The key idea is retrieval-first generation: the model is not asked to guess from memory.",
            "We ingest Jira, product docs, and automation assets, index them, retrieve relevant context, and then generate.",
            "We enforce strict output contracts and deterministic filters to remove unsupported invented scenarios.",
            "So the output is faster to produce, more consistent, and easier to trust and review.",
        ],
    )

    _add_dense_slide(
        prs,
        "45-Minute Session Breakdown",
        [
            "0-5 min: Context and problem statement",
            "5-12 min: Architecture explanation and data flow",
            "12-22 min: Code-level walkthrough of key modules",
            "22-35 min: Live tool demo end-to-end",
            "35-41 min: Guardrails, quality controls, and known limits",
            "41-45 min: Q&A and next steps",
        ],
    )

    _add_dense_slide(
        prs,
        "Problem Statement",
        [
            "Manual story-to-test conversion is time-intensive and varies by engineer.",
            "Prompt-only LLM generation often creates unsupported scenarios.",
            "Teams need outputs that are grounded in Jira evidence and internal standards.",
            "The objective is speed plus trust: faster authoring without losing correctness.",
        ],
    )

    _add_dense_slide(
        prs,
        "Architecture (Complete Pipeline)",
        [
            "Data sources: Jira stories, product markdown/PDF docs, automation repo artifacts.",
            "Ingestion: source-specific loaders normalize documents and metadata.",
            "Chunking + metadata: each chunk carries source/type/doc_domain/feature_key/path details.",
            "Embeddings: HuggingFace sentence-transformers generate vectors for chunks and queries.",
            "Vector index: FAISS stores embeddings for nearest-neighbor semantic retrieval.",
            "Retrieval: semantic candidate search + metadata filters for feature scoping.",
            "Generation: strict schema prompts consume only grounded context payloads.",
            "Guardrails: deterministic post-filters remove unsupported generated items.",
            "Outputs: test cases, automation artifacts, gap analysis, markdown/export payloads.",
        ],
    )

    _add_dense_slide(
        prs,
        "Concept Explainer: LangChain",
        [
            "LangChain is orchestration glue around document loading, splitting, embeddings, and vector search.",
            "It standardizes interaction with retrievers and vector stores in one workflow.",
            "In this tool, LangChain wrappers reduce custom plumbing and keep retrieval modular.",
            "Important: LangChain is not the model; it is workflow infrastructure around the model.",
        ],
    )

    _add_dense_slide(
        prs,
        "Concept Explainer: Embeddings + Semantic Search",
        [
            "Embeddings map text into vectors representing semantic meaning.",
            "Semantic search compares vector proximity rather than exact keyword overlap.",
            "This enables matching synonyms and paraphrases from Jira wording to doc wording.",
            "Semantic retrieval is necessary but not sufficient: metadata filtering is added for precision.",
        ],
    )

    _add_dense_slide(
        prs,
        "Concept Explainer: FAISS / Vector DB",
        [
            "FAISS is a high-performance nearest-neighbor index used as the vector store layer.",
            "It supports fast retrieval of top-k most similar chunks for a query embedding.",
            "In practice: query embedding -> FAISS top-k candidates -> metadata filtering -> final context.",
            "Benefit: latency and cost are lower than repeatedly sending large corpora to the LLM.",
        ],
    )

    _add_dense_slide(
        prs,
        "Concept Explainer: RAG",
        [
            "RAG means Retrieval-Augmented Generation.",
            "The model is augmented with fresh, relevant, internal context at generation time.",
            "This improves domain specificity and reduces hallucinations compared with prompt-only generation.",
            "In this tool, RAG is combined with strict schema and deterministic post-filtering.",
        ],
    )

    _add_dense_slide(
        prs,
        "Feature Scoping (Critical Trust Layer)",
        [
            "Feature aliases define canonical keys (feature-aliases.json).",
            "resolve_feature_key derives canonical feature from summary/prefix/context text.",
            "Retrieval passes feature_key_eq + doc_domain_eq + path_contains filters.",
            "If semantic misses, deterministic docstore fallback still enforces exact feature match.",
            "Result: context for Notes should not bleed into Content Type and vice versa.",
            "If no alias matches, feature context may be empty and retrieval becomes broader by type/query.",
        ],
    )

    _add_dense_slide(
        prs,
        "Strict Generation Contracts",
        [
            "Automation generation uses response_format json_object.",
            "Prompt defines exact output keys and behavior constraints.",
            "Manual test generation requires JSON array only (no prose).",
            "Gap analysis also requires strict JSON sections.",
            "Outputs are normalized before UI display/export, reducing shape drift.",
        ],
    )

    _add_dense_slide(
        prs,
        "Deterministic Post-Filtering",
        [
            "Rule-based filters run after model generation.",
            "Unsupported scenarios are removed unless evidence exists in Jira story text.",
            "Example blocked by default: network failure, timeout, offline, server-500, concurrency, performance, browser-compat.",
            "Applied in test generation and gap analysis paths.",
            "This is deterministic: same input + same evidence gives same filter decision.",
        ],
    )

    _add_dense_slide(
        prs,
        "Automation Guardrails",
        [
            "No naked cy.get selectors allowed in generated spec bodies.",
            "Locators must be routed through page object wrappers/variables.",
            "Reuse existing wrappers from common utilities and feature page objects first.",
            "Custom command suggestions are limited to API data setup/cleanup patterns.",
            "Existing page object implementation suggestions are suppressed if already present.",
        ],
    )

    _add_dense_slide(
        prs,
        "Live Demo Script (Readable)",
        [
            "Step 1: Select one Jira story and show AC/STR/description details.",
            "Step 2: Generate test cases and call out coverage refs and grounded sections.",
            "Step 3: Highlight filtered behavior if unsupported scenarios appear.",
            "Step 4: Open automation tab and generate Cypress artifacts.",
            "Step 5: Show feature-context chunks used and strict command/page-object constraints.",
            "Step 6: Run gap analysis and explain grounded PO questions.",
            "Step 7: Export markdown/spec output and close with value summary.",
        ],
    )

    _add_dense_slide(
        prs,
        "What To Say While Demo Runs",
        [
            "I am not asking the model to create tests from thin air.",
            "The story is normalized first, then context is retrieved from indexed internal artifacts.",
            "Generation must fit a strict JSON contract, then deterministic filters enforce realism.",
            "That is why output is reviewable, structured, and less prone to hallucination.",
        ],
    )

    _add_dense_slide(
        prs,
        "Code Anchors (Mention Verbally)",
        [
            "Ingestion: rag/ingest_all.py",
            "Retriever filter logic: rag/get_relevant_docs.py",
            "Vector store/embeddings setup: rag/vectorstore.py",
            "Test generation and filters: custom-agent-ui/pages/1_Test_Case_Generator.py",
            "Gap analysis and filters: custom-agent-ui/pages/3_Gap_Analysis.py",
            "Automation policy file: rag/docs/automation/automation-guidelines.md",
            "Feature aliases: rag/docs/automation/feature-context/feature-aliases.json",
        ],
    )

    _add_dense_slide(
        prs,
        "Questions You Will Likely Get (With Answers)",
        [
            "Q: Is this hallucination-proof? A: No system is absolute; retrieval + strict schema + deterministic filters materially reduce risk.",
            "Q: Why not fine-tune? A: RAG is faster to update and better for changing internal docs.",
            "Q: What if retrieval misses? A: There is deterministic fallback plus transparent context display.",
            "Q: How do you ensure domain fit? A: Feature scoping and repo-specific guidelines control outputs.",
            "Q: What is still manual? A: Final QA review and acceptance remain human-owned.",
        ],
    )

    _add_dense_slide(
        prs,
        "Known Limits (Be Honest)",
        [
            "Alias coverage needs expansion for more features (example: initiatives aliases).",
            "If indexed docs are sparse or stale, retrieval quality degrades.",
            "LLM may still over-generate before deterministic filters clean outputs.",
            "Metadata quality during ingest directly affects feature-scoped retrieval precision.",
        ],
    )

    _add_dense_slide(
        prs,
        "Mitigations and Next Steps",
        [
            "Expand feature alias map for all major modules.",
            "Automate periodic ingest and index refresh.",
            "Add evaluation set with precision/recall-style QA metrics.",
            "Log dropped items from filters to monitor generation drift.",
            "Add confidence dashboard for retrieval evidence quality.",
        ],
    )

    _add_dense_slide(
        prs,
        "Closing Script (Read This)",
        [
            "This tool combines retrieval-first architecture, strict output contracts, and deterministic validation.",
            "The result is faster QA authoring while keeping outputs grounded in Jira and internal standards.",
            "It is not a black-box chat assistant; it is a controlled QA generation workflow.",
            "Our next focus is broader feature coverage, continuous evaluation, and deeper governance telemetry.",
        ],
    )

    prs.save(out_path)


if __name__ == "__main__":
    output = r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Private_Reference.pptx"
    build(output)
    print(output)
