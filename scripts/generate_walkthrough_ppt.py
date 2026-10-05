from pptx import Presentation
from pptx.util import Inches, Pt


def add_title_slide(prs, title, subtitle):
	slide = prs.slides.add_slide(prs.slide_layouts[0])
	slide.shapes.title.text = title
	slide.placeholders[1].text = subtitle


def add_bullets_slide(prs, title, bullets, level2=None):
	slide = prs.slides.add_slide(prs.slide_layouts[1])
	slide.shapes.title.text = title
	tf = slide.shapes.placeholders[1].text_frame
	tf.clear()

	level2 = level2 or {}
	for idx, bullet in enumerate(bullets):
		p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
		p.text = bullet
		p.level = 0
		p.font.size = Pt(22)
		for sub in level2.get(idx, []):
			sp = tf.add_paragraph()
			sp.text = sub
			sp.level = 1
			sp.font.size = Pt(18)


def add_architecture_slide(prs):
	slide = prs.slides.add_slide(prs.slide_layouts[5])
	slide.shapes.title.text = "Architecture Overview (End-to-End)"

	left = Inches(0.6)
	top = Inches(1.4)
	width = Inches(12.0)
	height = Inches(5.0)
	box = slide.shapes.add_textbox(left, top, width, height)
	tf = box.text_frame
	tf.word_wrap = True

	lines = [
		"Data Sources -> Ingestion -> Chunking + Metadata -> Embeddings -> FAISS Index",
		"User Story Selection -> Feature Key Resolution -> Filtered Retrieval",
		"Retrieved Context + Strict Prompt Schema -> LLM Generation",
		"Deterministic Post-Filtering + Guardrails -> UI Review + Export",
		"",
		"Sources: Jira stories, product docs, automation repo (specs, page objects, commands, fixtures)",
	]
	for i, line in enumerate(lines):
		p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
		p.text = line
		p.font.size = Pt(22 if i < 4 else 18)


def add_code_refs_slide(prs):
	slide = prs.slides.add_slide(prs.slide_layouts[1])
	slide.shapes.title.text = "Key Code Paths In Demo"
	tf = slide.shapes.placeholders[1].text_frame
	tf.clear()

	refs = [
		"Ingestion orchestrator: rag/ingest_all.py",
		"Retriever + filters: rag/get_relevant_docs.py",
		"Vector store setup: rag/vectorstore.py",
		"Test generation: custom-agent-ui/pages/1_Test_Case_Generator.py",
		"Gap analysis: custom-agent-ui/pages/3_Gap_Analysis.py",
		"Automation rules: rag/docs/automation/automation-guidelines.md",
	]
	for i, ref in enumerate(refs):
		p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
		p.text = ref
		p.level = 0
		p.font.size = Pt(20)


def build_presentation(output_path):
	prs = Presentation()

	add_title_slide(
		prs,
		"QA Intelligence Hub Walkthrough",
		"Generating Grounded Test Cases from Jira using RAG\n45-minute session demo",
	)

	add_bullets_slide(
		prs,
		"Session Objectives",
		[
			"Show how Jira stories become test cases using RAG",
			"Explain architecture: embeddings, retrieval, generation, guardrails",
			"Demonstrate grounded outputs for test cases, gap analysis, and automation draft",
			"Build trust: reduce hallucinations with deterministic post-filters",
		],
	)

	add_bullets_slide(
		prs,
		"Agenda (45 Minutes)",
		[
			"0-5: Problem statement and expected outcomes",
			"5-12: Architecture and component overview",
			"12-22: Code walkthrough (key files)",
			"22-35: Live demo (single story end-to-end)",
			"35-41: Guardrails and quality controls",
			"41-45: Q&A and next steps",
		],
	)

	add_bullets_slide(
		prs,
		"Problem We Are Solving",
		[
			"Manual story-to-test conversion is slow and inconsistent",
			"Prompt-only generation can invent scenarios not in Jira",
			"Need project-specific grounded outputs, not generic QA text",
			"Need reusable path to manual + automation-ready assets",
		],
	)

	add_architecture_slide(prs)

	add_bullets_slide(
		prs,
		"Concept Brief: RAG + Embeddings + FAISS",
		[
			"Embeddings convert text chunks into semantic vectors",
			"FAISS stores vectors and returns nearest relevant chunks fast",
			"Semantic retrieval finds meaning-based matches, not only keyword matches",
			"RAG injects retrieved project context into LLM generation",
			"LangChain orchestrates retriever/vectorstore integrations",
		],
	)

	add_bullets_slide(
		prs,
		"Feature-Scoped Retrieval (Not Broad Semantic Only)",
		[
			"Feature key resolved from story context using aliases",
			"Retrieval applies metadata filters: feature_key, doc_domain, path",
			"If semantic top-k misses, deterministic docstore fallback runs",
			"Result: only same-feature chunks are used for generation",
		],
		level2={
			1: ["Example filters: feature_key_eq + doc_domain_eq + path_contains"],
			2: ["Prevents cross-feature leakage (e.g., Notes vs Content Type)"]
		},
	)

	add_bullets_slide(
		prs,
		"Grounded Generation + Strict Schema",
		[
			"Prompt receives only selected story context + retrieved chunks + repo rules",
			"Response format is enforced as strict JSON object/array",
			"Normalization validates expected keys before UI render/export",
			"No free-form narrative output in production paths",
		],
	)

	add_bullets_slide(
		prs,
		"Deterministic Post-Filtering Guardrails",
		[
			"Unsupported generated items are removed using rule-based checks",
			"Network/API failure scenarios removed unless explicitly in Jira evidence",
			"Same principle applied in gap analysis outputs",
			"Model quality + deterministic safety gives consistent reliability",
		],
	)

	add_bullets_slide(
		prs,
		"Live Demo Plan (13 Minutes)",
		[
			"Select Jira story and display AC/STR/comments",
			"Generate test cases and show traceability + coverage refs",
			"Show feature-scoped context chunks used",
			"Run automation generation tab (page objects + command constraints)",
			"Run gap analysis and show grounded gaps/questions",
			"Export markdown/spec output",
		],
	)

	add_code_refs_slide(prs)

	add_bullets_slide(
		prs,
		"Quality & Trust Talking Points",
		[
			"Not chat-only generation: retrieval-first architecture",
			"Feature-level precision via metadata filtering",
			"Strict schema output to reduce ambiguity",
			"Deterministic post-filters remove unsupported items",
			"Human-in-the-loop review remains available before export",
		],
	)

	add_bullets_slide(
		prs,
		"Expected Outcomes",
		[
			"Faster story-to-test workflow with better consistency",
			"Higher confidence from grounded and explainable outputs",
			"Reusable architecture for other QA workflows",
			"Roadmap: richer feature aliases, telemetry, and evaluation scoring",
		],
	)

	add_bullets_slide(
		prs,
		"Backup Plan (If Live API Is Slow)",
		[
			"Use already indexed FAISS content for offline-style walkthrough",
			"Demonstrate retrieval + generation from local index artifacts",
			"Show exported outputs prepared from pre-run story",
			"Continue Q&A on architecture and controls",
		],
	)

	add_bullets_slide(
		prs,
		"Q&A",
		[
			"How do we control hallucinations?",
			"How is feature scoping enforced?",
			"How is this different from prompt-only generation?",
			"What are known limitations and next improvements?",
		],
	)

	prs.save(output_path)


if __name__ == "__main__":
	out = r"c:\Users\mhimanshu\Documents\qa-intelligence-hub\QA_Intelligence_Hub_Walkthrough.pptx"
	build_presentation(out)
	print(out)
