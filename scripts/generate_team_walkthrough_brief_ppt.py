from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor


def add_title(prs, title, subtitle):
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle


def add_bullets(prs, title, bullets, font_size=22):
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    tf = slide.shapes.placeholders[1].text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b
        p.level = 0
        p.font.size = Pt(font_size)


def add_architecture_diagram(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Architecture Overview"

    # Top row
    boxes = [
        (Inches(0.4), Inches(1.5), Inches(2.1), Inches(0.9), "Data Sources\nJira + Docs +\nAutomation Repo"),
        (Inches(2.8), Inches(1.5), Inches(2.1), Inches(0.9), "Ingestion +\nChunking +\nMetadata"),
        (Inches(5.2), Inches(1.5), Inches(2.1), Inches(0.9), "Embeddings\nHuggingFace"),
        (Inches(7.6), Inches(1.5), Inches(2.1), Inches(0.9), "Vector Index\nFAISS"),
    ]

    fill = RGBColor(233, 243, 255)
    line = RGBColor(55, 110, 180)

    for left, top, width, height, text in boxes:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        shape.line.color.rgb = line
        tf = shape.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(14)

    # Bottom row
    boxes2 = [
        (Inches(0.4), Inches(3.2), Inches(2.4), Inches(0.95), "Feature-Scoped\nRetrieval\n(semantic + filters)"),
        (Inches(3.2), Inches(3.2), Inches(2.4), Inches(0.95), "LLM Generation\n(Strict JSON schema)"),
        (Inches(6.0), Inches(3.2), Inches(2.4), Inches(0.95), "Deterministic\nPost-Filtering"),
        (Inches(8.8), Inches(3.2), Inches(1.9), Inches(0.95), "UI + Export"),
    ]

    for left, top, width, height, text in boxes2:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        shape.line.color.rgb = line
        tf = shape.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(14)

    slide.shapes.add_textbox(Inches(0.5), Inches(5.0), Inches(9.8), Inches(0.7)).text_frame.text = (
        "Accurate outputs are achieved by grounding generation in retrieved evidence + strict schema + post-filters."
    )


def build(path):
    prs = Presentation()

    add_title(
        prs,
        "QA Intelligence Hub",
        "AI-assisted QA workflow for Jira-to-Test + Automation generation (Team Walkthrough)",
    )

    add_bullets(
        prs,
        "Why This Tool Was Created",
        [
            "Convert Jira stories into high-quality test assets faster",
            "Reduce manual effort and inconsistency in test authoring",
            "Avoid prompt-only AI outputs that are not grounded in project context",
            "Provide one unified QA flow: test cases, coverage insight, and gap analysis",
        ],
    )

    add_bullets(
        prs,
        "Challenge Before This Tool",
        [
            "Story-to-test conversion was manual and time-consuming",
            "Quality varied by individual interpretation",
            "Cross-checking against existing coverage took extra effort",
            "Generated content could include unsupported or made-up scenarios",
        ],
    )

    add_bullets(
        prs,
        "How This Tool Helps",
        [
            "Retrieves relevant internal context before generation (RAG)",
            "Uses feature-scoped filtering to reduce cross-feature noise",
            "Enforces structured output contracts for consistency",
            "Applies deterministic filters to remove unsupported items",
            "Generates automation-ready Cypress artifacts with framework guardrails",
            "Keeps human review in control before export",
        ],
    )

    add_architecture_diagram(prs)

    add_bullets(
        prs,
        "Bundled Tool 1: Test Case Generator",
        [
            "Input: Jira story (summary, description, AC, STR, comments)",
            "Output: structured test cases with traceability references",
            "Quality controls: duplicate checks, critique + refinement pass",
            "Accuracy: removes unsupported scenarios not present in story evidence",
        ],
        font_size=20,
    )

    add_bullets(
        prs,
        "Bundled Tool 2: Coverage Analysis",
        [
            "Maps story requirements to available test coverage",
            "Highlights coverage gaps and duplication risk",
            "Uses indexed context for broad project-level visibility",
            "Helps prioritize where new tests are needed first",
        ],
        font_size=20,
    )

    add_bullets(
        prs,
        "Bundled Tool 3: Gap Analysis",
        [
            "Generates requirement-summary and identified requirement gaps",
            "Produces targeted questions for Product Owner clarification",
            "Supports single-story, multi-story, and epic-level analysis",
            "Accuracy: removes inferred scenarios unless explicitly present in story set",
        ],
        font_size=20,
    )

    add_bullets(
        prs,
        "Automation Generation (Built-In)",
        [
            "Input: selected generated test cases + feature-scoped automation context",
            "Output: Cypress spec file, page object updates, data-command suggestions",
            "Reads framework guidelines directly (automation-guidelines.md)",
            "Matches similar spec style while staying grounded in project patterns",
            "Designed to accelerate automation handoff from QA to SDET/dev",
        ],
        font_size=20,
    )

    add_bullets(
        prs,
        "Automation Guardrails for Reliable Output",
        [
            "No naked cy.get selectors in spec test bodies",
            "Prefer existing page object wrappers before creating new locator abstractions",
            "Custom command suggestions limited to API data setup/cleanup, not UI flow commands",
            "Avoids suggesting implementation of already-existing page objects",
            "Strict JSON output contract plus post-filtering before display/export",
        ],
        font_size=19,
    )

    add_bullets(
        prs,
        "How We Improve Accuracy",
        [
            "Feature-scoped retrieval (not broad semantic-only search)",
            "Grounded prompts with strict JSON schema",
            "Deterministic post-filtering of unsupported generated items",
            "Automation guardrails: page-object-first locator policy",
            "Transparent outputs for reviewer validation",
        ],
    )

    add_bullets(
        prs,
        "Estimated Time Saved",
        [
            "Manual story-to-test design (before): ~45-90 minutes per story",
            "With tool + reviewer validation (now): ~10-25 minutes per story",
            "Estimated reduction: ~60-75% for authoring cycle time",
            "Additional savings from reusable automation/gap outputs",
            "Note: figures are team pilot estimates and can be refined with usage metrics",
        ],
        font_size=19,
    )

    add_bullets(
        prs,
        "Conclusion",
        [
            "The tool improves speed, consistency, and confidence in QA outputs",
            "Architecture is retrieval-first, structured, and guardrail-driven",
            "It supports immediate QA productivity while keeping human review in loop",
            "Next step: expand alias coverage and measure weekly productivity gains",
        ],
    )

    prs.save(path)


if __name__ == "__main__":
    out = r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Team_Brief_Walkthrough.pptx"
    build(out)
    print(out)
