"""Build a concise introduction/demo deck for the QA Copilot CLI.

Run from the repository root with:
    .venv\\Scripts\\python.exe qa-copilot-cli\\build_demo_ppt.py
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


OUTPUT = Path(__file__).resolve().parents[1] / "QA_Copilot_CLI_Demo.pptx"
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

INK = RGBColor(0x17, 0x2D, 0x34)
TEAL = RGBColor(0x0B, 0x7A, 0x72)
CORAL = RGBColor(0xD9, 0x69, 0x4E)
GOLD = RGBColor(0xC4, 0x92, 0x35)
PAPER = RGBColor(0xF5, 0xF4, 0xEE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MINT = RGBColor(0xE3, 0xEF, 0xEA)
PALE_CORAL = RGBColor(0xF7, 0xE9, 0xE3)
PALE_GOLD = RGBColor(0xF4, 0xEE, 0xDB)
PALE_BLUE = RGBColor(0xE7, 0xEF, 0xF1)
MUTED = RGBColor(0x5D, 0x70, 0x75)
LINE = RGBColor(0xD6, 0xDF, 0xDB)
FONT = "Aptos"
DISPLAY_FONT = "Aptos Display"

presentation = Presentation()
presentation.slide_width = SLIDE_WIDTH
presentation.slide_height = SLIDE_HEIGHT
BLANK = presentation.slide_layouts[6]


def add_box(slide, x, y, width, height, fill=WHITE, stroke=LINE, stroke_width=1):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = stroke
    shape.line.width = Pt(stroke_width)
    return shape


def add_text(
    slide,
    value,
    x,
    y,
    width,
    height,
    size=16,
    color=INK,
    bold=False,
    font=FONT,
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.02)
    frame.margin_right = Inches(0.02)
    frame.margin_top = Inches(0.01)
    frame.margin_bottom = Inches(0.01)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.space_after = Pt(0)
    run = paragraph.add_run()
    run.text = value
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return shape


def add_dot(slide, x, y, color=TEAL, diameter=0.10):
    dot = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(diameter), Inches(diameter)
    )
    dot.fill.solid()
    dot.fill.fore_color.rgb = color
    dot.line.fill.background()


def add_rule(slide, x, y, width, color=LINE, height=0.015):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def add_connector(slide, x1, y1, x2, y2, color=TEAL, width=1.5):
    connector = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1),
        Inches(y1),
        Inches(x2),
        Inches(y2),
    )
    connector.line.color.rgb = color
    connector.line.width = Pt(width)
    return connector


def add_footer(slide, number, dark=False):
    color = RGBColor(0xA9, 0xBC, 0xBA) if dark else MUTED
    add_text(
        slide,
        f"QA INTELLIGENCE HUB  /  COPILOT CLI                                      {number:02d}  /  10",
        0.62,
        7.12,
        12.1,
        0.18,
        size=8,
        color=color,
        bold=True,
    )


def add_content_slide(title, eyebrow, number):
    slide = presentation.slides.add_slide(BLANK)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = PAPER
    add_text(slide, eyebrow.upper(), 0.68, 0.34, 8.8, 0.24, size=9, color=TEAL, bold=True)
    add_text(slide, title, 0.68, 0.70, 12.0, 0.58, size=27, color=INK, bold=True, font=DISPLAY_FONT)
    add_rule(slide, 0.68, 1.39, 11.96, LINE, 0.012)
    add_footer(slide, number)
    return slide


def add_card(slide, x, y, width, height, title, body, accent=TEAL, fill=WHITE, title_size=16, body_size=12):
    add_box(slide, x, y, width, height, fill=fill)
    add_box(slide, x, y, 0.07, height, fill=accent, stroke=accent, stroke_width=0)
    add_text(slide, title, x + 0.22, y + 0.18, width - 0.42, 0.38, size=title_size, color=INK, bold=True)
    add_text(slide, body, x + 0.22, y + 0.66, width - 0.42, height - 0.78, size=body_size, color=MUTED)


def add_bullet(slide, x, y, width, value, color=TEAL, size=13):
    add_dot(slide, x, y + 0.10, color, 0.09)
    add_text(slide, value, x + 0.20, y, width - 0.20, 0.42, size=size, color=INK)


# 1. Cover
slide = presentation.slides.add_slide(BLANK)
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = INK
add_box(slide, 0, 0, 0.13, 7.5, fill=TEAL, stroke=TEAL, stroke_width=0)
add_text(slide, "QA INTELLIGENCE HUB", 0.92, 0.82, 5.7, 0.3, size=11, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Copilot CLI\ndemo", 0.92, 1.55, 6.8, 1.8, size=43, color=WHITE, bold=True, font=DISPLAY_FONT)
add_text(
    slide,
    "From Jira story to grounded QA plan\nand reviewable Cypress draft",
    0.96,
    3.68,
    6.1,
    0.95,
    size=20,
    color=RGBColor(0xD5, 0xE0, 0xDC),
)
add_rule(slide, 0.96, 5.10, 5.8, RGBColor(0x3B, 0x5C, 0x60), 0.018)
add_text(slide, "NEW TOOL WALKTHROUGH  |  SEPTEMBER 29, 2026", 0.96, 5.36, 6.0, 0.30, size=10, color=RGBColor(0xA9, 0xBC, 0xBA), bold=True)

# A restrained architecture motif on the right.
add_text(slide, "ASK", 8.72, 1.24, 1.2, 0.22, size=9, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "GROUND", 10.37, 2.68, 1.55, 0.22, size=9, color=RGBColor(0xEF, 0xB1, 0x94), bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "REVIEW", 8.82, 4.68, 1.3, 0.22, size=9, color=RGBColor(0xE3, 0xC5, 0x7B), bold=True, align=PP_ALIGN.CENTER)
add_connector(slide, 9.45, 1.72, 10.55, 2.55, RGBColor(0x5D, 0x9D, 0x94), 2)
add_connector(slide, 10.65, 3.15, 9.88, 4.57, RGBColor(0xC5, 0x78, 0x60), 2)
add_connector(slide, 9.28, 4.43, 9.18, 1.85, RGBColor(0xB6, 0x9A, 0x55), 2)
for px, py, shade in [(9.1, 1.55, TEAL), (10.35, 2.8, CORAL), (9.0, 4.05, GOLD)]:
    node = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(px), Inches(py), Inches(0.46), Inches(0.46))
    node.fill.solid()
    node.fill.fore_color.rgb = shade
    node.line.color.rgb = INK
    node.line.width = Pt(2)
add_text(slide, "A human-directed workflow,\nnot an autonomous test runner", 8.0, 5.55, 4.0, 0.75, size=14, color=RGBColor(0xD5, 0xE0, 0xDC), align=PP_ALIGN.CENTER)
add_footer(slide, 1, dark=True)

# 2. The problem
slide = add_content_slide("QA context is spread across the workflow", "Why this CLI exists", 2)
add_text(slide, "One story. Several places to look.", 0.72, 1.67, 11.4, 0.42, size=21, color=INK, bold=True)
source_items = [
    ("JIRA", "Story, acceptance criteria,\nsteps to reproduce", TEAL, MINT),
    ("TESTRAIL", "Existing cases, steps,\nexpected results", CORAL, PALE_CORAL),
    ("PRODUCT DOCS", "Feature rules, roles,\nknown constraints", GOLD, PALE_GOLD),
    ("CYPRESS", "Page Objects, commands,\nneighboring test patterns", INK, PALE_BLUE),
]
for index, (name, body, accent, fill) in enumerate(source_items):
    x = 0.72 + index * 3.04
    add_box(slide, x, 2.42, 2.72, 1.52, fill=fill, stroke=accent, stroke_width=1.25)
    add_text(slide, name, x + 0.18, 2.63, 2.34, 0.24, size=10, color=accent, bold=True)
    add_text(slide, body, x + 0.18, 3.04, 2.38, 0.70, size=13, color=INK, bold=True)
    if index < 3:
        add_text(slide, "+", x + 2.78, 2.91, 0.22, 0.30, size=20, color=MUTED, bold=True, align=PP_ALIGN.CENTER)
add_box(slide, 0.72, 4.46, 11.84, 1.42, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "The opportunity", 1.00, 4.71, 2.1, 0.3, size=10, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Bring the right context into one reviewable QA workflow.", 1.00, 5.10, 10.9, 0.52, size=22, color=WHITE, bold=True, font=DISPLAY_FONT)
add_text(slide, "No time-savings baseline is assumed; the pilot will measure it.", 0.76, 6.20, 11.7, 0.32, size=11, color=MUTED)

# 3. Why the tool was created
slide = add_content_slide("From a recurring QA challenge to a grounded workflow", "Why this tool was created", 3)
add_text(slide, "The goal", 0.76, 1.68, 5.55, 0.26, size=10, color=TEAL, bold=True)
add_text(slide, "Turn Jira stories into high-quality test assets faster, with the right project context already in the workflow.", 0.76, 2.02, 5.45, 0.82, size=18, color=INK, bold=True, font=DISPLAY_FONT)
goal_items = [
    "Reduce manual effort and inconsistency in test authoring",
    "Avoid prompt-only outputs that are not grounded in project context",
    "Unify test cases, coverage insight, and requirement gap analysis",
]
for index, item in enumerate(goal_items):
    add_bullet(slide, 0.80, 3.15 + index * 0.48, 5.35, item, TEAL, 11)

add_text(slide, "Before the tool", 6.72, 1.68, 5.55, 0.26, size=10, color=CORAL, bold=True)
challenge_items = [
    "Story-to-test conversion was manual and time-consuming",
    "Quality varied by individual interpretation",
    "Cross-checking existing coverage took extra effort",
    "AI could introduce unsupported or made-up scenarios",
]
for index, item in enumerate(challenge_items):
    add_bullet(slide, 6.76, 2.08 + index * 0.55, 5.30, item, CORAL, 11)

add_box(slide, 0.76, 5.08, 11.80, 1.10, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "HOW IT HELPS", 1.00, 5.31, 1.50, 0.20, size=9, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Jira + TestRail + product docs  →  FAISS / RAG context  →  Copilot reasoning  →  reviewable QA assets", 2.68, 5.27, 9.35, 0.34, size=15, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "The model generates from retrieved evidence, while QA remains in control of the final result.", 0.82, 6.43, 11.70, 0.28, size=11, color=MUTED, align=PP_ALIGN.CENTER)

# 4. Product overview
slide = add_content_slide("Three workflows, one conversational entry point", "What the CLI does", 4)
workflow_cards = [
    ("01", "Analyze", "Grounded requirement gaps and product-owner questions.\n\nOutput: reviewable Markdown analysis.", TEAL, MINT),
    ("02", "Generate", "Scenario-level manual cases with source evidence, coverage references, and duplicate warnings.\n\nOutput: Markdown + JSON.", CORAL, PALE_CORAL),
    ("03", "Automate", "Build a case-scoped Cypress draft from existing feature patterns.\n\nOutput: preview, then save only with approval.", GOLD, PALE_GOLD),
]
for index, (number, title, body, accent, fill) in enumerate(workflow_cards):
    x = 0.72 + index * 4.04
    add_box(slide, x, 1.83, 3.72, 3.52, fill=WHITE, stroke=LINE, stroke_width=1)
    add_box(slide, x, 1.83, 3.72, 0.13, fill=accent, stroke=accent, stroke_width=0)
    add_text(slide, number, x + 0.22, 2.15, 0.54, 0.34, size=15, color=accent, bold=True)
    add_text(slide, title, x + 0.22, 2.66, 3.16, 0.43, size=22, color=INK, bold=True, font=DISPLAY_FONT)
    add_text(slide, body, x + 0.22, 3.28, 3.22, 1.62, size=13, color=MUTED)
    add_box(slide, x + 0.22, 4.87, 1.25, 0.28, fill=fill, stroke=fill, stroke_width=0)
    add_text(slide, "HUMAN REVIEW", x + 0.28, 4.93, 1.12, 0.12, size=7, color=accent, bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "Start from the repository root:", 0.76, 5.87, 3.0, 0.28, size=11, color=MUTED, bold=True)
add_box(slide, 0.72, 6.20, 5.12, 0.48, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "copilot --agent=qa-analyst", 0.94, 6.30, 4.72, 0.24, size=13, color=WHITE, font="Consolas")
add_text(slide, "CLI path uses the Copilot model; no OpenAI API key is required.", 6.15, 6.27, 6.2, 0.30, size=12, color=TEAL, bold=True)

# 5. Architecture
slide = add_content_slide("Architecture: model reasoning, local context tools", "How it fits together", 5)
# Top interaction row
add_box(slide, 0.72, 1.70, 2.20, 0.78, fill=WHITE, stroke=TEAL, stroke_width=1.3)
add_text(slide, "QA ENGINEER", 0.90, 1.86, 1.84, 0.18, size=9, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "Story key + intent", 0.90, 2.12, 1.84, 0.20, size=11, color=INK, align=PP_ALIGN.CENTER)
add_text(slide, ">", 3.02, 1.91, 0.38, 0.30, size=20, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
add_box(slide, 3.48, 1.70, 4.42, 0.78, fill=MINT, stroke=TEAL, stroke_width=1.3)
add_text(slide, "GITHUB COPILOT CLI  /  qa-analyst", 3.70, 1.86, 4.00, 0.20, size=11, color=INK, bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "Coordinator + Jira, test design, review, Cypress skills", 3.70, 2.13, 4.00, 0.20, size=10, color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, ">", 8.00, 1.91, 0.38, 0.30, size=20, color=CORAL, bold=True, align=PP_ALIGN.CENTER)
add_box(slide, 8.46, 1.70, 4.10, 0.78, fill=PALE_CORAL, stroke=CORAL, stroke_width=1.3)
add_text(slide, "COPILOT MODEL", 8.70, 1.86, 3.62, 0.20, size=11, color=CORAL, bold=True, align=PP_ALIGN.CENTER)
add_text(slide, "Reasoning and language generation", 8.70, 2.13, 3.62, 0.20, size=10, color=MUTED, align=PP_ALIGN.CENTER)

# MCP tool boundary
add_connector(slide, 5.70, 2.50, 5.70, 2.80, TEAL, 1.4)
add_box(slide, 0.72, 2.84, 11.84, 0.70, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "LOCAL MCP BOUNDARY  /  qa-hub", 0.94, 3.02, 3.18, 0.18, size=10, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Fetch context  |  page large results  |  validate schemas and citations  |  save approved artifacts", 4.00, 3.02, 8.28, 0.22, size=11, color=WHITE)

# Sources and index row
source_cards = [
    (0.72, "LIVE SYSTEMS", "Jira story details\nTestRail case details", TEAL, MINT),
    (4.74, "LOCAL KNOWLEDGE", "FAISS retrieval\nMiniLM embeddings run locally", GOLD, PALE_GOLD),
    (8.76, "SCOPED CYPRESS CONTEXT", "Exact-path code chunks\nFeature Page Objects + commands", CORAL, PALE_CORAL),
]
for x, heading, body, accent, fill in source_cards:
    add_connector(slide, x + 1.85, 3.56, x + 1.85, 3.78, accent, 1.2)
    add_box(slide, x, 3.82, 3.80, 0.98, fill=fill, stroke=accent, stroke_width=1)
    add_text(slide, heading, x + 0.16, 3.98, 3.48, 0.18, size=9, color=accent, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, body, x + 0.16, 4.22, 3.48, 0.44, size=11, color=INK, align=PP_ALIGN.CENTER)

# Outputs row
add_text(slide, "REVIEWABLE OUTPUTS", 0.76, 5.15, 2.20, 0.20, size=9, color=TEAL, bold=True)
output_cards = [
    (0.72, "Gap analysis", "Markdown + grounded questions"),
    (4.74, "Test cases", "Cited Markdown + validated JSON"),
    (8.76, "Cypress draft", "Preview; approved new spec only"),
]
for x, heading, body in output_cards:
    add_box(slide, x, 5.47, 3.80, 0.75, fill=WHITE, stroke=LINE, stroke_width=1)
    add_text(slide, heading, x + 0.17, 5.61, 3.46, 0.23, size=13, color=INK, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, body, x + 0.17, 5.94, 3.46, 0.18, size=9, color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, "No direct Jira/TestRail writes. Cypress is not executed by the CLI.", 0.76, 6.47, 11.7, 0.28, size=11, color=CORAL, bold=True, align=PP_ALIGN.CENTER)

# 6. Guardrails
slide = add_content_slide("Built for review, not blind automation", "Trust and boundaries", 6)
add_text(slide, "What is controlled", 0.76, 1.72, 5.3, 0.32, size=16, color=TEAL, bold=True)
controls = [
    "Jira source precedence and exact quotations for evidence",
    "Feature-scoped retrieval instead of broad code dumping",
    "Schema, citation, and traceability validation before saving",
    "Duplicate and unsupported-scenario warnings stay visible",
    "Preview and approval before creating a Cypress spec",
    "Manual sign-in in the headed browser; never read secrets from config",
]
for index, item in enumerate(controls):
    add_bullet(slide, 0.80, 2.20 + index * 0.58, 5.45, item, TEAL, 12)

add_box(slide, 6.85, 1.72, 5.55, 4.16, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "What it does not claim", 7.15, 2.00, 4.90, 0.38, size=17, color=WHITE, bold=True)
limits = [
    "Not a replacement for QA judgment",
    "Does not write to Jira or TestRail",
    "Does not run generated Cypress tests",
    "Knowledge can be stale until the index is refreshed",
]
for index, item in enumerate(limits):
    add_bullet(slide, 7.20, 2.72 + index * 0.63, 4.75, item, CORAL, 12)
add_text(slide, "Quality remains a human decision; the tool makes the evidence and draft faster to inspect.", 0.80, 6.27, 11.8, 0.42, size=14, color=INK, bold=True, align=PP_ALIGN.CENTER)

# 7. Demo storyboard
slide = add_content_slide("A live story-to-automation walkthrough", "Suggested 8-10 minute demo", 7)
steps = [
    ("01", "Orient", "Start the agent from repo root. Show the workflow options.", "copilot --agent=qa-analyst", TEAL),
    ("02", "Analyze", "Use a known Jira story; inspect requirement sources and PO questions.", "Analyze STUD-12345 for requirement gaps and PO questions.", CORAL),
    ("03", "Generate", "Generate cases; highlight citations, coverage refs, and review warnings.", "Generate test cases for STUD-12345.", GOLD),
    ("04", "Automate", "Choose one saved case; inspect the preview and approval gate.", "Generate Cypress automation for STUD-12345; list saved cases first.", TEAL),
]
for index, (number, heading, detail, prompt, accent) in enumerate(steps):
    y = 1.76 + index * 1.14
    add_text(slide, number, 0.82, y + 0.12, 0.48, 0.25, size=14, color=accent, bold=True)
    add_text(slide, heading, 1.45, y + 0.06, 1.22, 0.30, size=15, color=INK, bold=True)
    add_text(slide, detail, 2.75, y + 0.04, 4.15, 0.56, size=11, color=MUTED)
    add_box(slide, 7.16, y, 5.28, 0.72, fill=WHITE, stroke=LINE, stroke_width=1)
    add_text(slide, prompt, 7.36, y + 0.15, 4.88, 0.43, size=10, color=INK, font="Consolas")
add_text(slide, "Replace STUD-12345 with a demo story that has current AC, known product context, and a saved case.", 0.82, 6.42, 11.6, 0.36, size=11, color=CORAL, bold=True)

# 8. Benefits and evidence
slide = add_content_slide("Benefits to test for in a pilot", "Value hypothesis", 8)
add_text(slide, "Potential benefit", 0.82, 1.72, 4.55, 0.26, size=10, color=TEAL, bold=True)
add_text(slide, "How we would measure it", 6.10, 1.72, 5.70, 0.26, size=10, color=TEAL, bold=True)
benefits = [
    ("Less time to first draft", "Median minutes from story selection to reviewable cases"),
    ("More traceable outputs", "Share of cases with valid source citations and coverage refs"),
    ("Less context hunting", "QA reviewer rating and number of manual context switches"),
    ("Better reuse of automation patterns", "Share of drafts reusing the right feature Page Objects"),
    ("Earlier requirement clarification", "Useful PO questions raised before implementation starts"),
]
for index, (benefit, metric) in enumerate(benefits):
    y = 2.12 + index * 0.79
    fill = WHITE if index % 2 == 0 else RGBColor(0xEF, 0xF0, 0xEA)
    add_box(slide, 0.76, y, 11.82, 0.62, fill=fill, stroke=fill, stroke_width=0)
    add_text(slide, benefit, 0.96, y + 0.17, 4.70, 0.25, size=13, color=INK, bold=True)
    add_text(slide, metric, 6.10, y + 0.17, 6.15, 0.25, size=11, color=MUTED)
add_text(slide, "These are pilot hypotheses, not measured outcomes.", 0.82, 6.40, 11.6, 0.32, size=12, color=CORAL, bold=True, align=PP_ALIGN.CENTER)

# 9. ROI model
slide = add_content_slide("ROI: make the assumptions visible", "Illustrative capacity model", 9)
add_box(slide, 0.76, 1.76, 5.05, 3.98, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "NET HOURS RECLAIMED / WEEK", 1.04, 2.04, 4.48, 0.28, size=10, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Stories per week x\n(minutes saved per story / 60)\n- weekly review and upkeep", 1.04, 2.55, 4.44, 1.25, size=18, color=WHITE, bold=True, font=DISPLAY_FONT)
add_rule(slide, 1.04, 4.10, 4.42, RGBColor(0x3B, 0x5C, 0x60), 0.02)
add_text(slide, "Annual capacity value = net weekly hours x active weeks x loaded hourly rate", 1.04, 4.40, 4.42, 0.76, size=12, color=RGBColor(0xD5, 0xE0, 0xDC))

add_text(slide, "Example only - replace with pilot data", 6.28, 1.90, 5.75, 0.32, size=16, color=INK, bold=True)
example_rows = [
    ("Stories / week", "8"),
    ("Assumed minutes saved / story", "40"),
    ("Review + upkeep / week", "2 hours"),
    ("Net capacity reclaimed", "3.3 hours / week"),
    ("At 46 active weeks", "about 153 hours / year"),
]
for index, (label, value) in enumerate(example_rows):
    y = 2.48 + index * 0.58
    add_rule(slide, 6.28, y + 0.44, 5.65, LINE, 0.012)
    add_text(slide, label, 6.34, y, 3.30, 0.30, size=11, color=MUTED)
    add_text(slide, value, 9.68, y, 2.20, 0.30, size=12, color=TEAL if index > 2 else INK, bold=True, align=PP_ALIGN.RIGHT)
add_text(slide, "Convert hours to value using your approved loaded rate; subtract setup, support, and licensing costs. This is capacity, not guaranteed cash savings.", 0.82, 6.12, 11.70, 0.60, size=11, color=CORAL, bold=True)

# 10. Pilot and close
slide = add_content_slide("Prove value with a small, measurable pilot", "Decision and next steps", 10)
pilot = [
    ("SCOPE", "10-15 representative Jira stories across 2 weeks"),
    ("BASELINE", "Record today's authoring and review time before using the CLI"),
    ("MEASURE", "Time-to-first-draft, citation validity, review edits, reuse, reviewer confidence"),
    ("DECIDE", "Expand, refine prompts/context, or stop based on evidence"),
]
for index, (label, detail) in enumerate(pilot):
    y = 1.82 + index * 0.92
    add_box(slide, 0.82, y, 1.56, 0.57, fill=[MINT, PALE_CORAL, PALE_GOLD, PALE_BLUE][index], stroke=LINE, stroke_width=0.8)
    add_text(slide, label, 0.96, y + 0.17, 1.28, 0.20, size=10, color=[TEAL, CORAL, GOLD, INK][index], bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, detail, 2.70, y + 0.13, 8.95, 0.32, size=14, color=INK, bold=index == 3)

add_box(slide, 0.82, 5.80, 11.70, 0.88, fill=INK, stroke=INK, stroke_width=0)
add_text(slide, "ASK", 1.06, 6.07, 0.65, 0.20, size=10, color=RGBColor(0x9C, 0xC9, 0xC1), bold=True)
add_text(slide, "Sponsor  |  2 QA reviewers  |  approved story sample  |  baseline time", 1.90, 6.03, 10.20, 0.30, size=15, color=WHITE, bold=True)

presentation.save(OUTPUT)
print(f"Created {OUTPUT}")
print(f"Slides: {len(presentation.slides)}")
