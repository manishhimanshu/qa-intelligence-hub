"""
build_ppt.py  —  QA Intelligence Hub deck for VP presentation
Run:  .venv\Scripts\python.exe build_ppt.py
Output: QA_Intelligence_Hub_Demo.pptx
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Palette — clean, minimal ─────────────────────────────────────────────────
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
OFF_WHITE   = RGBColor(0xF4, 0xF6, 0xF8)
DARK        = RGBColor(0x1A, 0x1A, 0x2E)
MID         = RGBColor(0x44, 0x55, 0x66)
LIGHT       = RGBColor(0x88, 0x99, 0xAA)
BLUE        = RGBColor(0x00, 0x74, 0xD9)
BLUE_LIGHT  = RGBColor(0xE8, 0xF4, 0xFF)
GREEN       = RGBColor(0x27, 0xAE, 0x60)
GREEN_LIGHT = RGBColor(0xE8, 0xF8, 0xEE)
ORANGE      = RGBColor(0xE6, 0x7E, 0x22)
RED         = RGBColor(0xC0, 0x39, 0x2B)
GREY_LINE   = RGBColor(0xDD, 0xE3, 0xE8)
YELLOW_BG   = RGBColor(0xFF, 0xF9, 0xE8)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)

prs = Presentation()
prs.slide_width  = SLIDE_W
prs.slide_height = SLIDE_H
blank = prs.slide_layouts[6]

# ── Helpers ──────────────────────────────────────────────────────────────────

def add_slide():
    return prs.slides.add_slide(blank)

def fill_bg(slide, color=WHITE):
    s = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)
    s.fill.solid(); s.fill.fore_color.rgb = color; s.line.fill.background()

def rect(slide, l, t, w, h, fill=OFF_WHITE, border=GREY_LINE, border_pt=1):
    s = slide.shapes.add_shape(1, l, t, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = fill
    s.line.color.rgb = border; s.line.width = Pt(border_pt)
    return s

def top_bar(slide, color=BLUE):
    b = slide.shapes.add_shape(1, 0, 0, SLIDE_W, Inches(0.08))
    b.fill.solid(); b.fill.fore_color.rgb = color; b.line.fill.background()

def txt(slide, text, l, t, w, h, size=16, bold=False, color=DARK,
        align=PP_ALIGN.LEFT, italic=False):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    p  = tf.paragraphs[0]; p.alignment = align
    r  = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold
    r.font.color.rgb = color; r.font.italic = italic
    return tb

def hline(slide, t, l=Inches(0.5), w=None, color=GREY_LINE):
    _w = w or (SLIDE_W - Inches(1.0))
    ln = slide.shapes.add_shape(1, l, t, _w, Pt(1.2))
    ln.fill.solid(); ln.fill.fore_color.rgb = color; ln.line.fill.background()

def slide_footer(slide, n, total=7):
    txt(slide, f"QA Intelligence Hub  |  {n} / {total}",
        Inches(0.5), SLIDE_H - Inches(0.38), Inches(12.3), Inches(0.3),
        size=9, color=LIGHT, align=PP_ALIGN.RIGHT)

def chip(slide, label, l, t, w=Inches(1.8), h=Inches(0.36),
         fill=BLUE, tc=WHITE, size=11):
    b = slide.shapes.add_shape(1, l, t, w, h)
    b.fill.solid(); b.fill.fore_color.rgb = fill; b.line.fill.background()
    tf = b.text_frame; p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r  = p.add_run(); r.text = label
    r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = tc

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — Title
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl, DARK)
top_bar(sl, BLUE)

txt(sl, "QA Intelligence Hub",
    Inches(1.0), Inches(1.6), Inches(11.3), Inches(1.5),
    size=54, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

txt(sl, "AI-Powered Test Case Generation  ·  Coverage Analysis  ·  Requirement Gap Detection",
    Inches(1.0), Inches(3.2), Inches(11.3), Inches(0.6),
    size=18, color=RGBColor(0xAA,0xCC,0xEE), align=PP_ALIGN.CENTER)

hline(sl, Inches(4.05), l=Inches(3.0), w=Inches(7.3), color=BLUE)

txt(sl, "GPT-4o  ·  RAG / FAISS  ·  Jira  ·  TestRail  ·  Streamlit",
    Inches(1.0), Inches(4.2), Inches(11.3), Inches(0.5),
    size=14, color=RGBColor(0x88,0xAA,0xCC), align=PP_ALIGN.CENTER)

chip(sl, "INTERNAL TOOL PITCH", Inches(5.1), Inches(5.2), Inches(3.1), Inches(0.4),
     fill=ORANGE, tc=WHITE, size=12)

txt(sl, "April 2026  ·  Presented to VP Engineering & Product",
    Inches(1.0), Inches(6.4), Inches(11.3), Inches(0.4),
    size=12, color=RGBColor(0x66,0x88,0xAA), align=PP_ALIGN.CENTER)

slide_footer(sl, 1)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — Problem + Solution (combined)
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 2)

txt(sl, "The Problem — and How We Solve It",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

# Left — Problems
txt(sl, "Manual QA Today",
    Inches(0.5), Inches(1.05), Inches(5.9), Inches(0.42),
    size=16, bold=True, color=RED)

problems = [
    ("30–45 min", "per story for a senior QA engineer to write test cases"),
    ("Inconsistent", "coverage — edge cases and role variants often missed"),
    ("No gap signal", "until dev is done or a production incident occurs"),
    ("4 separate tools", "Jira, TestRail, Cypress, product docs — never unified"),
    ("Manual export", "copy-paste from doc to TestRail adds 10–15 min each"),
]
for i, (bold_part, rest) in enumerate(problems):
    y = Inches(1.55 + i * 0.98)
    rect(sl, Inches(0.5), y, Inches(5.8), Inches(0.82),
         fill=RGBColor(0xFD,0xF0,0xF0), border=RGBColor(0xF5,0xC6,0xC6))
    txt(sl, bold_part, Inches(0.65), y + Inches(0.08), Inches(1.5), Inches(0.36),
        size=13, bold=True, color=RED)
    txt(sl, rest, Inches(0.65), y + Inches(0.44), Inches(5.5), Inches(0.32),
        size=12, color=MID)

# Right — Solution
txt(sl, "QA Intelligence Hub",
    Inches(7.0), Inches(1.05), Inches(6.0), Inches(0.42),
    size=16, bold=True, color=BLUE)

solutions = [
    ("< 30 seconds", "AI generates structured test cases per story"),
    ("Systematic", "every FR, edge case, role variant, negative scenario"),
    ("Pre-dev gaps", "requirement gaps flagged before a line of code is written"),
    ("Unified RAG", "Jira, TestRail, Cypress, product docs in one knowledge base"),
    ("One-click export", "generated cases pushed directly to TestRail"),
]
for i, (bold_part, rest) in enumerate(solutions):
    y = Inches(1.55 + i * 0.98)
    rect(sl, Inches(7.0), y, Inches(5.8), Inches(0.82),
         fill=BLUE_LIGHT, border=RGBColor(0xBB,0xD9,0xF5))
    txt(sl, bold_part, Inches(7.15), y + Inches(0.08), Inches(1.7), Inches(0.36),
        size=13, bold=True, color=BLUE)
    txt(sl, rest, Inches(7.15), y + Inches(0.44), Inches(5.5), Inches(0.32),
        size=12, color=MID)

# VS divider
rect(sl, Inches(6.45), Inches(1.4), Inches(0.42), Inches(5.3),
     fill=OFF_WHITE, border=GREY_LINE)
txt(sl, "VS", Inches(6.45), Inches(3.75), Inches(0.42), Inches(0.5),
    size=14, bold=True, color=MID, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — Architecture & How It Works
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 3)

txt(sl, "How It Works — Architecture",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

# Row labels
rows = [
    (Inches(1.05), "DATA\nSOURCES", BLUE),
    (Inches(2.65), "RAG INDEX", GREEN),
    (Inches(4.05), "LLM PIPELINE", ORANGE),
    (Inches(5.75), "OUTPUT", MID),
]

# Data sources
sources = [
    ("Jira\nStories", BLUE),
    ("TestRail\nCases", GREEN),
    ("Product\nDocs", ORANGE),
    ("Cypress\nPatterns", MID),
    ("Role\nPermissions", BLUE),
]
for i, (label, col) in enumerate(sources):
    x = Inches(1.5 + i * 2.2)
    b = rect(sl, x, Inches(1.05), Inches(1.9), Inches(0.78),
             fill=WHITE, border=col, border_pt=2)
    txt(sl, label, x, Inches(1.1), Inches(1.9), Inches(0.7),
        size=12, bold=True, color=col, align=PP_ALIGN.CENTER)

# Down arrow label
txt(sl, "ingest_all.py  ·  HuggingFace MiniLM-L6-v2 embeddings  (FREE, runs locally)",
    Inches(1.5), Inches(1.88), Inches(10.0), Inches(0.35),
    size=11, color=MID, align=PP_ALIGN.CENTER)

# FAISS box
faiss = rect(sl, Inches(4.5), Inches(2.3), Inches(4.3), Inches(0.78),
             fill=GREEN_LIGHT, border=GREEN, border_pt=2)
txt(sl, "FAISS Vector Index  (18,000+ documents · 384-dim)",
    Inches(4.5), Inches(2.38), Inches(4.3), Inches(0.6),
    size=13, bold=True, color=GREEN, align=PP_ALIGN.CENTER)

# Arrow down
txt(sl, "↓  RAG retrieval per story  (top-k=30, <50ms)",
    Inches(3.5), Inches(3.14), Inches(6.3), Inches(0.35),
    size=11, color=MID, align=PP_ALIGN.CENTER)

# Pipeline steps
steps = [
    ("Step 1\nExtract\nRequirements", "temp 0.1\n~2,300 tokens", BLUE),
    ("Step 2\nGenerate\nTest Cases",  "temp 0.2\n~8,500 tokens", GREEN),
    ("Step 3\nSelf-\nCritique",       "temp 0.1\n~4,500 tokens", ORANGE),
]
for i, (label, tokens, color) in enumerate(steps):
    x = Inches(1.5 + i * 3.6)
    b = rect(sl, x, Inches(3.55), Inches(3.0), Inches(1.3),
             fill=WHITE, border=color, border_pt=2)
    txt(sl, label, x, Inches(3.6), Inches(3.0), Inches(0.85),
        size=13, bold=True, color=color, align=PP_ALIGN.CENTER)
    txt(sl, tokens, x, Inches(4.45), Inches(3.0), Inches(0.36),
        size=10, color=LIGHT, align=PP_ALIGN.CENTER, italic=True)
    if i < 2:
        txt(sl, "→", Inches(4.52 + i * 3.6), Inches(3.97), Inches(0.5), Inches(0.4),
            size=20, bold=True, color=LIGHT, align=PP_ALIGN.CENTER)

# Output row
outputs = [
    ("📋  Structured\nTest Cases (JSON)", BLUE),
    ("📊  Coverage\nScore (0–100)", GREEN),
    ("🔍  QA Gaps\n& Confidence", ORANGE),
    ("✅  TestRail\nExport", MID),
]
for i, (label, color) in enumerate(outputs):
    x = Inches(0.5 + i * 3.2)
    b = rect(sl, x, Inches(5.1), Inches(3.0), Inches(0.88),
             fill=OFF_WHITE, border=GREY_LINE)
    txt(sl, label, x, Inches(5.15), Inches(3.0), Inches(0.8),
        size=12, color=color, align=PP_ALIGN.CENTER, bold=True)

txt(sl, "Jira & TestRail APIs also called live for story details and case deduplication",
    Inches(0.5), Inches(6.2), Inches(12.3), Inches(0.35),
    size=10, color=LIGHT, italic=True, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 4 — Accuracy
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 4)

txt(sl, "Accuracy — How the AI Gets It Right",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

layers = [
    (BLUE,   "1  Structured Normalisation",
     "Raw Jira fields (AC, Steps to Reproduce, Description) are normalised into a canonical schema before "
     "any LLM call. Story vs Bug detection adjusts fallback order. Gherkin grouping and divider stripping prevent noise."),
    (GREEN,  "2  Requirements Brief First  (Step 1, temp = 0.1)",
     "LLM analyses the ticket in isolation before generating anything. Separating 'understand' from 'write' "
     "eliminates hallucination and ensures every functional requirement, edge case, and negatives scenario is extracted first."),
    (ORANGE, "3  Role-Permission RAG Context",
     "Each call injects 3 chunks from the role-permissions knowledge base: Universal Rules + Object-Level "
     "Access (Owner / Edit / View) + feature-specific section. LLM writes precise preconditions such as "
     "'Contributor with EDIT access (not owner)' — not just 'logged in as contributor'."),
    (MID,    "4  Hard Coverage Mandate  (Step 2 prompt)",
     "The prompt enforces a 4-step mandate: positive case per FR → edge & boundary (BVA/EP) → negative per NS → "
     "supplementary role/API cases. LLM is instructed NOT to stop until every FR, EC, and NS is addressed."),
    (BLUE,   "5  Self-Critique Pass  (Step 3, temp = 0.1)",
     "A second LLM call reviews generated cases against the Step 1 brief. Returns: Coverage Score (0–100), "
     "per-case confidence, missing coverage list, duplicate pairs, improvement suggestions — all shown in the UI."),
]

for i, (color, title, detail) in enumerate(layers):
    y = Inches(1.08 + i * 1.1)
    rect(sl, Inches(0.5), y, Inches(12.3), Inches(0.95),
         fill=WHITE, border=color, border_pt=2)
    num_b = sl.shapes.add_shape(1, Inches(0.5), y, Inches(0.06), Inches(0.95))
    num_b.fill.solid(); num_b.fill.fore_color.rgb = color; num_b.line.fill.background()
    txt(sl, title, Inches(0.72), y + Inches(0.06), Inches(3.5), Inches(0.38),
        size=13, bold=True, color=color)
    txt(sl, detail, Inches(0.72), y + Inches(0.5), Inches(12.0), Inches(0.38),
        size=11.5, color=MID)

rect(sl, Inches(0.5), Inches(6.65), Inches(12.3), Inches(0.5),
     fill=GREEN_LIGHT, border=GREEN)
txt(sl, "Result:  QA engineers review and refine — they no longer write from scratch.  "
       "Estimated first-pass coverage completeness vs manual baseline:  > 85%",
    Inches(0.65), Inches(6.72), Inches(12.0), Inches(0.38),
    size=13, bold=True, color=GREEN)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 5 — Cost & ROI
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 5)

txt(sl, "Cost & ROI",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

# LLM cost table
txt(sl, "LLM Cost per Story  (GPT-4o @ $2.50/1M input · $10.00/1M output)",
    Inches(0.5), Inches(1.08), Inches(7.5), Inches(0.38),
    size=13, bold=True, color=DARK)

headers  = ["Step", "Input", "Output", "Cost"]
col_x    = [Inches(0.5), Inches(3.4), Inches(4.8), Inches(6.1)]
col_w    = [Inches(2.8), Inches(1.3), Inches(1.2), Inches(1.1)]

for j, (h, x, w) in enumerate(zip(headers, col_x, col_w)):
    rect(sl, x, Inches(1.52), w, Inches(0.4),
         fill=DARK, border=DARK)
    txt(sl, h, x + Inches(0.07), Inches(1.56), w, Inches(0.32),
        size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

rows_d = [
    ["1 — Extract Requirements", "~1,800", "~500",   "$0.009"],
    ["2 — Generate Test Cases",  "~5,500", "~3,000", "$0.044"],
    ["3 — Self-Critique",        "~4,000", "~500",   "$0.015"],
    ["TOTAL per story",          "~11,300","~4,000", "$0.068"],
]
for r, row in enumerate(rows_d):
    is_total = r == 3
    bg_c = GREEN_LIGHT if is_total else (WHITE if r % 2 == 0 else OFF_WHITE)
    bdr  = GREEN if is_total else GREY_LINE
    for j, (cell, x, w) in enumerate(zip(row, col_x, col_w)):
        rect(sl, x, Inches(1.95 + r * 0.47), w, Inches(0.44),
             fill=bg_c, border=bdr)
        txt(sl, cell, x + Inches(0.07), Inches(2.0 + r * 0.47), w, Inches(0.34),
            size=12, bold=is_total, color=(GREEN if is_total else DARK),
            align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER)

rect(sl, Inches(0.5), Inches(4.0), Inches(7.2), Inches(0.42),
     fill=BLUE_LIGHT, border=BLUE)
txt(sl, "✅  Embeddings: HuggingFace all-MiniLM-L6-v2  →  $0.00  (runs locally, no API calls)",
    Inches(0.65), Inches(4.06), Inches(7.0), Inches(0.3),
    size=12, color=BLUE)

# ROI comparison
txt(sl, "ROI — 100 Stories / Month",
    Inches(8.0), Inches(1.08), Inches(5.0), Inches(0.38),
    size=13, bold=True, color=DARK)

without_b = rect(sl, Inches(8.0), Inches(1.52), Inches(4.9), Inches(1.3),
                  fill=RGBColor(0xFD,0xF0,0xF0), border=RED)
txt(sl, "Without AI", Inches(8.15), Inches(1.6), Inches(4.6), Inches(0.35),
    size=13, bold=True, color=RED)
txt(sl, "30–45 min / story × 100  @  $60/hr  =  $3,000 – $4,500 / month",
    Inches(8.15), Inches(1.98), Inches(4.6), Inches(0.7),
    size=12, color=MID)

with_b = rect(sl, Inches(8.0), Inches(2.95), Inches(4.9), Inches(1.3),
               fill=GREEN_LIGHT, border=GREEN)
txt(sl, "With AI", Inches(8.15), Inches(3.03), Inches(4.6), Inches(0.35),
    size=13, bold=True, color=GREEN)
txt(sl, "$6.80 LLM  +  8.3 hrs QA review  @  $60/hr  =  ~$510 / month",
    Inches(8.15), Inches(3.41), Inches(4.6), Inches(0.7),
    size=12, color=MID)

rect(sl, Inches(8.0), Inches(4.38), Inches(4.9), Inches(0.55),
     fill=GREEN_LIGHT, border=GREEN, border_pt=2)
txt(sl, "Saving:  $2,490 – $3,990 / month  (~85% cost reduction)",
    Inches(8.15), Inches(4.46), Inches(4.6), Inches(0.38),
    size=13, bold=True, color=GREEN)

# Monthly projections
txt(sl, "Monthly LLM Cost Projections",
    Inches(0.5), Inches(4.55), Inches(7.5), Inches(0.38),
    size=13, bold=True, color=DARK)

scenarios = [
    ("100 stories", "$6.80"),
    ("500 stories", "$34"),
    ("2,000 stories", "$136"),
    ("10,000 stories", "$680"),
]
for i, (label, cost) in enumerate(scenarios):
    x = Inches(0.5 + i * 1.85)
    rect(sl, x, Inches(5.0), Inches(1.7), Inches(1.25),
         fill=WHITE, border=GREY_LINE)
    txt(sl, cost, x, Inches(5.08), Inches(1.7), Inches(0.58),
        size=22, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
    txt(sl, label, x, Inches(5.66), Inches(1.7), Inches(0.42),
        size=11, color=MID, align=PP_ALIGN.CENTER)

txt(sl, "Caching (@st.cache_data, ttl=1h):  regenerating same story costs $0.00",
    Inches(0.5), Inches(6.35), Inches(12.3), Inches(0.35),
    size=11, italic=True, color=LIGHT)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 6 — Hosting & Expansion
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 6)

txt(sl, "Internal Hosting & Multi-Product Expansion",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

# Hosting options
txt(sl, "Recommended Hosting — Docker on Internal Server",
    Inches(0.5), Inches(1.08), Inches(12.3), Inches(0.38),
    size=14, bold=True, color=DARK)

hosting = [
    (BLUE,  "Infrastructure",    "2 vCPU · 4 GB RAM · 2 GB disk  ·  No GPU required  ·  docker-compose.yml (one file deploy)"),
    (GREEN, "FAISS Index",       "Persisted as a Docker volume  ·  nightly cron job re-ingests Jira + TestRail + docs"),
    (ORANGE,"Secrets",           "API keys in .env or Vault — never in source code  ·  All traffic over HTTPS (truststore)"),
    (MID,   "Access",            "Exposed via internal reverse proxy (nginx) + SSO (Azure AD / Okta)  ·  Zero public surface"),
]
for i, (color, label, detail) in enumerate(hosting):
    y = Inches(1.55 + i * 0.65)
    rect(sl, Inches(0.5), y, Inches(12.3), Inches(0.56),
         fill=WHITE, border=GREY_LINE)
    b = sl.shapes.add_shape(1, Inches(0.5), y, Inches(0.06), Inches(0.56))
    b.fill.solid(); b.fill.fore_color.rgb = color; b.line.fill.background()
    txt(sl, label, Inches(0.7), y + Inches(0.07), Inches(1.6), Inches(0.36),
        size=12, bold=True, color=color)
    txt(sl, detail, Inches(2.45), y + Inches(0.07), Inches(10.2), Inches(0.36),
        size=12, color=MID)

# Multi-product
hline(sl, Inches(4.28))
txt(sl, "Expanding to Other Products",
    Inches(0.5), Inches(4.38), Inches(12.3), Inches(0.38),
    size=14, bold=True, color=DARK)

txt(sl, "The hub is product-agnostic. Each new product team needs only 3 config values:",
    Inches(0.5), Inches(4.85), Inches(12.3), Inches(0.35),
    size=13, color=MID)

configs = [
    (BLUE,   "JIRA_PROJECT",        "e.g. STUD, BLOG, MKTG  — Jira project key to ingest"),
    (GREEN,  "TESTRAIL_PROJECT_ID", "e.g. 34  — TestRail project with the team's test suites"),
    (ORANGE, "Docs folder",         "Drop product .md / .pdf files into /docs  — auto-ingested on next run"),
]
for i, (color, key, detail) in enumerate(configs):
    x = Inches(0.5 + i * 4.3)
    rect(sl, x, Inches(5.27), Inches(4.05), Inches(0.88),
         fill=WHITE, border=color, border_pt=2)
    txt(sl, key, x + Inches(0.12), Inches(5.33), Inches(3.8), Inches(0.35),
        size=12, bold=True, color=color)
    txt(sl, detail, x + Inches(0.12), Inches(5.7), Inches(3.8), Inches(0.35),
        size=11, color=MID)

txt(sl, "Estimated onboarding time for a new product team:  1–2 days",
    Inches(0.5), Inches(6.28), Inches(8.0), Inches(0.35),
    size=12, color=MID, italic=True)

chip(sl, "Shared FAISS (multi-tenant)",
     Inches(8.6), Inches(6.2), Inches(4.0), Inches(0.42),
     fill=BLUE_LIGHT, tc=BLUE, size=12)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 7 — Roadmap + The Ask
# ═══════════════════════════════════════════════════════════════════════════
sl = add_slide()
fill_bg(sl)
top_bar(sl)
slide_footer(sl, 7)

txt(sl, "Roadmap & The Ask",
    Inches(0.5), Inches(0.22), Inches(12.3), Inches(0.65),
    size=28, bold=True, color=DARK)
hline(sl, Inches(0.92))

# Roadmap — 4 phases as horizontal timeline
phases = [
    (GREEN,  "Phase 1  ✅  DONE",      "Q1–Q2 2026",
     "3-step pipeline · Coverage dashboard · Gap analysis · Role RAG · TestRail export"),
    (BLUE,   "Phase 2  —  Pilot",      "Q2–Q3 2026",
     "Docker deploy · SSO · Feedback loop (thumbs up/down) · 2nd product team"),
    (ORANGE, "Phase 3  —  Platform",   "Q3–Q4 2026",
     "Multi-product namespace · CI auto-ingest · Coverage trend analytics · Versioning"),
    (MID,    "Phase 4  —  Enterprise", "2027+",
     "Azure OpenAI (data residency) · LLM fine-tuning · Jira webhook auto-trigger"),
]
for i, (color, phase, period, detail) in enumerate(phases):
    x = Inches(0.4 + i * 3.23)
    rect(sl, x, Inches(1.08), Inches(3.08), Inches(2.0),
         fill=WHITE, border=color, border_pt=2)
    b = sl.shapes.add_shape(1, x, Inches(1.08), Inches(3.08), Inches(0.07))
    b.fill.solid(); b.fill.fore_color.rgb = color; b.line.fill.background()
    txt(sl, phase, x + Inches(0.1), Inches(1.2), Inches(2.88), Inches(0.4),
        size=12, bold=True, color=color)
    txt(sl, period, x + Inches(0.1), Inches(1.62), Inches(2.88), Inches(0.3),
        size=10, color=LIGHT, italic=True)
    txt(sl, detail, x + Inches(0.1), Inches(1.94), Inches(2.88), Inches(1.0),
        size=11, color=MID)

# The Ask
hline(sl, Inches(3.25))
txt(sl, "The Ask — What We Need to Launch",
    Inches(0.5), Inches(3.35), Inches(12.3), Inches(0.42),
    size=16, bold=True, color=DARK)

asks = [
    (BLUE,   "Approve internal hosting",
     "Small server or container env  ·  2 vCPU · 4 GB RAM · 2 GB disk  ·  One-time setup"),
    (GREEN,  "2-week pilot sprint",
     "1 QA engineer + 1 DevOps engineer  ·  Deploy, SSO, validate on 20+ stories"),
    (ORANGE, "OpenAI API budget",
     "~$50–$100 / month for pilot (500–1,500 stories)  ·  Azure OpenAI option if needed"),
    (MID,    "TestRail service account",
     "Read + write access on target project  ·  Required for one-click export workflow"),
]
for i, (color, title, detail) in enumerate(asks):
    row = i // 2
    col = i % 2
    x = Inches(0.5 + col * 6.42)
    y = Inches(3.88 + row * 1.28)
    rect(sl, x, y, Inches(6.1), Inches(1.1),
         fill=WHITE, border=color, border_pt=2)
    b2 = sl.shapes.add_shape(1, x, y, Inches(0.06), Inches(1.1))
    b2.fill.solid(); b2.fill.fore_color.rgb = color; b2.line.fill.background()
    txt(sl, title, x + Inches(0.18), y + Inches(0.1), Inches(5.8), Inches(0.38),
        size=13, bold=True, color=DARK)
    txt(sl, detail, x + Inches(0.18), y + Inches(0.54), Inches(5.8), Inches(0.46),
        size=11.5, color=MID)

rect(sl, Inches(0.5), Inches(6.62), Inches(12.3), Inches(0.55),
     fill=GREEN_LIGHT, border=GREEN)
txt(sl, "Goal:  QA Intelligence Hub live for Kapost by end of Q2 2026  ·  "
       "Second product team onboarded by Q3 2026",
    Inches(0.65), Inches(6.7), Inches(12.0), Inches(0.38),
    size=13, bold=True, color=GREEN, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════════
output_path = r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Demo.pptx"
prs.save(output_path)
print(f"Saved: {output_path}")
print(f"Slides: {len(prs.slides)}")

