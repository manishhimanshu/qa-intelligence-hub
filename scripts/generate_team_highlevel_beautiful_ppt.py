from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE


BG = RGBColor(245, 248, 252)
ACCENT = RGBColor(22, 82, 164)
ACCENT_LIGHT = RGBColor(225, 236, 250)
TEXT_DARK = RGBColor(31, 41, 55)
TEXT_MUTED = RGBColor(75, 85, 99)


def _style_slide_bg(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG


def _add_top_bar(slide, label):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.33), Inches(0.55))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()

    t = slide.shapes.add_textbox(Inches(0.45), Inches(0.08), Inches(12.0), Inches(0.35))
    tf = t.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.text = label
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = RGBColor(255, 255, 255)


def _set_title(slide, title):
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.9), Inches(11.9), Inches(0.9))
    tf = tb.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(34)
    p.font.bold = True
    p.font.color.rgb = TEXT_DARK


def add_title_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _style_slide_bg(slide)
    _add_top_bar(slide, "QA Intelligence Hub")

    _set_title(slide, "AI-Powered QA Workflow")

    sub = slide.shapes.add_textbox(Inches(0.68), Inches(1.95), Inches(11.3), Inches(0.9))
    tf = sub.text_frame
    p = tf.paragraphs[0]
    p.text = "From Jira Story to Test Cases, Coverage Insights, Gap Analysis, and Automation Drafts"
    p.font.size = Pt(19)
    p.font.color.rgb = TEXT_MUTED

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.68), Inches(3.0), Inches(12.0), Inches(2.4))
    card.fill.solid()
    card.fill.fore_color.rgb = ACCENT_LIGHT
    card.line.color.rgb = ACCENT
    tx = card.text_frame
    tx.clear()
    p = tx.paragraphs[0]
    p.text = "High-Level Walkthrough"
    p.font.bold = True
    p.font.size = Pt(22)
    p.font.color.rgb = ACCENT

    p2 = tx.add_paragraph()
    p2.text = "• Why we built this\n• How it works\n• Three bundled tools\n• Accuracy controls\n• Time saved"
    p2.font.size = Pt(18)
    p2.font.color.rgb = TEXT_DARK


def add_three_point_slide(prs, section, title, points):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _style_slide_bg(slide)
    _add_top_bar(slide, section)
    _set_title(slide, title)

    x_positions = [Inches(0.7), Inches(4.6), Inches(8.5)]
    for i, (head, body) in enumerate(points):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x_positions[i], Inches(2.15), Inches(3.9), Inches(3.1))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(255, 255, 255)
        card.line.color.rgb = RGBColor(210, 221, 235)

        tf = card.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.text = head
        p.font.size = Pt(20)
        p.font.bold = True
        p.font.color.rgb = ACCENT

        p2 = tf.add_paragraph()
        p2.text = body
        p2.font.size = Pt(15)
        p2.font.color.rgb = TEXT_DARK


def add_architecture_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _style_slide_bg(slide)
    _add_top_bar(slide, "Architecture")
    _set_title(slide, "How The Platform Works")

    steps = [
        "1. Ingest\nJira + Docs +\nAutomation Repo",
        "2. Index\nEmbeddings +\nFAISS",
        "3. Retrieve\nFeature-scoped\nContext",
        "4. Generate\nStrict Schema\nOutputs",
        "5. Validate\nDeterministic\nPost-Filter",
    ]

    x = Inches(0.65)
    for i, s in enumerate(steps):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.4), Inches(2.35), Inches(2.2))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(255, 255, 255)
        box.line.color.rgb = ACCENT
        tf = box.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.text = s
        p.font.size = Pt(14)
        p.font.bold = True
        p.alignment = PP_ALIGN.CENTER

        if i < len(steps) - 1:
            arr = slide.shapes.add_shape(MSO_SHAPE.CHEVRON, x + Inches(2.45), Inches(3.05), Inches(0.55), Inches(0.8))
            arr.fill.solid()
            arr.fill.fore_color.rgb = ACCENT_LIGHT
            arr.line.color.rgb = ACCENT
        x += Inches(2.55)

    note = slide.shapes.add_textbox(Inches(0.7), Inches(5.05), Inches(12.0), Inches(0.9))
    n = note.text_frame.paragraphs[0]
    n.text = "Accurate results = Grounded retrieval + strict schema + deterministic filtering"
    n.font.size = Pt(19)
    n.font.bold = True
    n.font.color.rgb = TEXT_DARK


def add_tools_slide(prs):
    add_three_point_slide(
        prs,
        "Bundled Tools",
        "Three Core Modules",
        [
            ("Test Case Generator", "Creates structured test cases directly from Jira story evidence."),
            ("Coverage Analysis", "Shows mapped coverage and highlights missing test areas."),
            ("Gap Analysis", "Identifies requirement gaps and PO clarification questions."),
        ],
    )


def add_accuracy_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _style_slide_bg(slide)
    _add_top_bar(slide, "Reliability")
    _set_title(slide, "Why Results Are Accurate")

    bullets = [
        "Feature-scoped retrieval (not broad semantic-only search)",
        "Grounded prompts with strict JSON contracts",
        "Deterministic post-filter removes unsupported scenarios",
        "Automation guardrails enforce framework-safe patterns",
    ]

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(2.1), Inches(11.7), Inches(3.2))
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(255, 255, 255)
    card.line.color.rgb = RGBColor(210, 221, 235)
    tf = card.text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"• {b}"
        p.font.size = Pt(20)
        p.font.color.rgb = TEXT_DARK


def add_time_saved_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _style_slide_bg(slide)
    _add_top_bar(slide, "Impact")
    _set_title(slide, "Estimated Time Saved")

    before = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(2.2), Inches(5.4), Inches(2.6))
    before.fill.solid()
    before.fill.fore_color.rgb = RGBColor(255, 255, 255)
    before.line.color.rgb = RGBColor(220, 80, 80)
    tf1 = before.text_frame
    tf1.clear()
    p1 = tf1.paragraphs[0]
    p1.text = "Before"
    p1.font.size = Pt(26)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(180, 40, 40)
    p2 = tf1.add_paragraph()
    p2.text = "45-90 min per story\n(Manual authoring + cross-checking)"
    p2.font.size = Pt(18)
    p2.font.color.rgb = TEXT_DARK

    after = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.9), Inches(2.2), Inches(5.4), Inches(2.6))
    after.fill.solid()
    after.fill.fore_color.rgb = RGBColor(255, 255, 255)
    after.line.color.rgb = RGBColor(40, 140, 70)
    tf2 = after.text_frame
    tf2.clear()
    q1 = tf2.paragraphs[0]
    q1.text = "With QA Intelligence Hub"
    q1.font.size = Pt(22)
    q1.font.bold = True
    q1.font.color.rgb = RGBColor(35, 120, 65)
    q2 = tf2.add_paragraph()
    q2.text = "10-25 min per story\n(Generation + focused reviewer validation)"
    q2.font.size = Pt(18)
    q2.font.color.rgb = TEXT_DARK

    result = slide.shapes.add_textbox(Inches(0.95), Inches(5.15), Inches(12.0), Inches(0.8))
    r = result.text_frame.paragraphs[0]
    r.text = "Estimated 60-75% cycle-time reduction in test authoring"
    r.font.size = Pt(24)
    r.font.bold = True
    r.font.color.rgb = ACCENT


def add_close_slide(prs):
    add_three_point_slide(
        prs,
        "Summary",
        "What The Team Gets",
        [
            ("Speed", "Faster story-to-test and automation draft cycles."),
            ("Consistency", "Structured outputs aligned to internal QA standards."),
            ("Trust", "Grounded retrieval plus deterministic safety controls."),
        ],
    )


def build(path):
    prs = Presentation()
    add_title_slide(prs)
    add_three_point_slide(
        prs,
        "Why",
        "Why We Built This Tool",
        [
            ("Challenge", "Manual QA authoring was slow and inconsistent."),
            ("Need", "Grounded AI outputs tied to Jira and internal assets."),
            ("Goal", "Faster, safer, and more reviewable QA workflows."),
        ],
    )
    add_architecture_slide(prs)
    add_tools_slide(prs)
    add_accuracy_slide(prs)
    add_time_saved_slide(prs)
    add_close_slide(prs)
    prs.save(path)


if __name__ == "__main__":
    out = r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Team_HighLevel_Styled.pptx"
    build(out)
    print(out)
