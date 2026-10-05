from pptx import Presentation
from pptx.util import Pt


def _set_notes(slide, notes_text: str) -> None:
    notes = slide.notes_slide
    notes.notes_text_frame.text = notes_text


def add_title(prs: Presentation, title: str, subtitle: str, notes: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle
    _set_notes(slide, notes)


def add_bullets(prs: Presentation, title: str, bullets: list[str], notes: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    tf = slide.shapes.placeholders[1].text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b
        p.level = 0
        p.font.size = Pt(22)
    _set_notes(slide, notes)


def add_flow_slide(prs: Presentation, notes: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Tool Flow: Story to Output"

    box = slide.shapes.add_textbox(Pt(40), Pt(110), Pt(860), Pt(300))
    tf = box.text_frame
    tf.word_wrap = True
    lines = [
        "1) Select Jira story in UI",
        "2) Extract normalized requirements (AC/STR/Description)",
        "3) Resolve feature key and retrieve feature-scoped chunks",
        "4) Generate test cases with strict JSON schema",
        "5) Run deterministic post-filtering (remove unsupported scenarios)",
        "6) Generate automation code with page-object and command guardrails",
        "7) Run gap analysis with the same anti-invention filter",
        "8) Export results",
    ]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(22)

    _set_notes(slide, notes)


def build(output_path: str) -> None:
    prs = Presentation()

    add_title(
        prs,
        "QA Intelligence Hub",
        "Tool-Focused Walkthrough Deck",
        "Open with: this is a retrieval-first QA assistant, not prompt-only generation.",
    )

    add_bullets(
        prs,
        "What This Tool Does",
        [
            "Generates test cases from Jira stories",
            "Performs gap analysis grounded in story evidence",
            "Drafts Cypress automation artifacts",
            "Exports structured outputs for QA workflow",
        ],
        "Say each outcome in one sentence. Keep this slide under 60 seconds.",
    )

    add_bullets(
        prs,
        "Core Tool Modules",
        [
            "Ingestion: Jira + docs + automation assets",
            "Indexing: embeddings + FAISS vector store",
            "Retrieval: semantic + metadata filters",
            "Generation: strict schema prompts",
            "Guardrails: deterministic post-filters",
        ],
        "Frame architecture as a pipeline with quality controls at each stage.",
    )

    add_flow_slide(
        prs,
        "Walk top to bottom. Emphasize feature-key resolution and post-filtering as trust anchors.",
    )

    add_bullets(
        prs,
        "Where Feature Scoping Happens",
        [
            "Feature aliases loaded from feature-aliases.json",
            "resolve_feature_key() derives canonical feature",
            "Retrieval passes feature_key_eq + doc_domain_eq + path_contains",
            "Docstore fallback keeps same strict feature match",
        ],
        "Mention that if no alias matches, feature context can be empty and retrieval is less strict.",
    )

    add_bullets(
        prs,
        "Strict Generation Contracts",
        [
            "Automation generation uses response_format json_object",
            "Prompt defines required output keys explicitly",
            "Manual test generation returns JSON array only",
            "Outputs are normalized before rendering/export",
        ],
        "Explain this reduces formatting drift and makes downstream handling deterministic.",
    )

    add_bullets(
        prs,
        "Deterministic Post-Filtering",
        [
            "Rule-based removal of unsupported generated items",
            "Drops network failure or made-up scenarios unless story mentions them",
            "Applied in test generation and gap analysis",
            "Produces safer, evidence-aligned outputs",
        ],
        "This is your strongest trust point: model output is validated against story evidence.",
    )

    add_bullets(
        prs,
        "Automation Guardrails",
        [
            "No naked cy.get selectors in spec test bodies",
            "Prefer existing page-object wrappers first",
            "Custom commands limited to API data setup/cleanup",
            "Existing page object implementations are not re-suggested",
        ],
        "Use one quick before/after example from your recent generated output to show the improvement.",
    )

    add_bullets(
        prs,
        "Live Demo Script (10-12 mins)",
        [
            "Select one Jira story and show AC/STR",
            "Generate test cases and show filtered result",
            "Open automation tab and generate Cypress artifacts",
            "Show feature-context chunks used",
            "Run gap analysis and show grounded PO questions",
        ],
        "Keep momentum: avoid code deep-dive during live generation. Focus on evidence and outcomes.",
    )

    add_bullets(
        prs,
        "Known Limits and Mitigations",
        [
            "Feature alias coverage affects retrieval precision",
            "Missing docs reduce context quality",
            "LLM can still over-generate before filters",
            "Mitigation: alias tuning, re-ingestion, strict filters",
        ],
        "Answer confidently: this is an evolving system with clear controls and measurable improvements.",
    )

    add_bullets(
        prs,
        "Close",
        [
            "Retrieval-first + strict schema + deterministic filtering",
            "Faster QA authoring with stronger consistency",
            "Grounded outputs that teams can review and trust",
            "Next: broaden aliases and add evaluation metrics",
        ],
        "End with business value: speed, quality, and trust in generated QA assets.",
    )

    prs.save(output_path)


if __name__ == "__main__":
    build(r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Tool_Focused_Walkthrough.pptx")
    print(r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Tool_Focused_Walkthrough.pptx")
