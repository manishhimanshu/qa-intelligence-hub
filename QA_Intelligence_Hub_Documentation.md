# QA Intelligence Hub

**By Manish Himanshu**

---

## Overview

QA Intelligence Hub is an internal AI-powered tool that helps QA engineers work faster and more consistently. It connects directly to Jira and TestRail, uses a local knowledge base (RAG index) built from all historical test cases and stories, and uses GPT-4o to generate structured test cases and requirement gap analyses.

### Three tools in one app:

| Tool | What it does |
|------|--------------|
| 📝 Test Case Generator | Pick any Jira story → view AC and existing TestRail cases → generate structured test cases → export to TestRail in one click |
| 📊 Coverage Dashboard | Full Jira ↔ TestRail traceability matrix across all stories — filterable, exportable to Excel |
| 🔍 Gap Analysis | AI-driven 5-section requirement gap analysis for any story or full epic — identifies missing roles, edge cases, integration gaps, and generates PO questions |

---

## Architecture

**Stack:** Python 3.12 · Streamlit · OpenAI GPT-4o · LangChain · FAISS · HuggingFace sentence-transformers · Jira REST API v3 · TestRail REST API

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Cloud                          │
│                                                             │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  Test Case  │  │    Coverage      │  │  Gap Analysis │  │
│  │  Generator  │  │   Dashboard      │  │               │  │
│  └──────┬──────┘  └────────┬─────────┘  └───────┬───────┘  │
│         └──────────────────┼─────────────────────┘          │
│                            │                                │
│              ┌─────────────▼──────────────┐                 │
│              │   shared_vectorstore.py    │                 │
│              │  (single FAISS load per    │                 │
│              │   process — cached)        │                 │
│              └─────────────┬──────────────┘                 │
│                            │                                │
│              ┌─────────────▼──────────────┐                 │
│              │     FAISS Index            │                 │
│              │  HuggingFace MiniLM-L6     │                 │
│              │  384-dim embeddings        │                 │
│              │  Sources: Jira + TestRail  │                 │
│              │  + PDFs + Markdown docs    │                 │
│              └────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐           ┌──────────────────┐
│   Jira REST     │           │  TestRail REST    │
│   API v3        │           │  API v2           │
│ (Atlassian)     │           │ (live case fetch  │
│ - Story content │           │  + export)        │
│ - AC + STR      │           └──────────────────┘
│ - Comments      │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  OpenAI API     │
│  GPT-4o         │
│ - Test case gen │
│ - Gap analysis  │
└─────────────────┘
```

---

## Component Breakdown

### Frontend — Streamlit

- Multi-page app (`custom-agent-ui/app.py` + `pages/`)
- `app.py` bridges Streamlit Cloud secrets → `os.environ` so all pages pick up credentials
- All three pages share one FAISS load via `shared_vectorstore.py` to stay within Streamlit Cloud's 1 GB memory limit

### Knowledge Base — FAISS + RAG

- Vector store built from embeddings of all Jira stories, TestRail cases, PDFs, and Markdown docs
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (local, free, 384-dim)
- Stored at `rag/faiss_index/` — committed to the repo, loaded at startup
- Rebuilt by running `python rag/ingest_all.py` locally (requires VPN for Jira + TestRail access)

### Ingestion Pipeline — `rag/ingest_all.py`

| Stage | Source | What it indexes |
|-------|--------|-----------------|
| 1 | Jira (`POST /rest/api/3/search/jql`) | All STUD project stories — Summary, Description, Acceptance Criteria, Steps to Reproduce, Comments |
| 2 | TestRail (`GET /api/v2/get_cases`) | All test cases across 39 suites — title, steps, expected results, section hierarchy |
| 3 | PDFs | Product documentation PDFs from `rag/pdfs/` |
| 4 | Markdown | Docs and instruction files from `rag/docs/` |
| 5 | Cypress | Automation spec patterns from the Cypress project root |

### LLM — OpenAI GPT-4o

- Used only for generation (test cases, gap analysis) — not for embeddings
- Embeddings are fully local (HuggingFace) — no OpenAI quota consumed for RAG
- Model configured via `OPENAI_MODEL` env var (defaults to `gpt-4o-mini` locally, `gpt-4o` on cloud)

---

## Data Flow Per Page

### 📝 Test Case Generator

1. FAISS docstore → full story list (all stories, no `top_k` cap)
2. Jira REST API → live story content (Description + AC + Steps to Reproduce) — falls back to FAISS if unavailable
3. FAISS similarity search → existing TestRail cases (`top_k=40`, by story key + summary)
4. TestRail REST API → live steps/expected results per matched case
5. FAISS similarity search → Cypress automation patterns (if available)
6. OpenAI GPT-4o → generates structured test cases (JSON array)
7. User reviews/edits → TestRail REST API → exports cases to chosen suite/section

### 📊 Coverage Dashboard

1. FAISS docstore → all Jira stories (full iteration, no similarity search)
2. FAISS keyword index → TestRail cases matched per story
3. Coverage status: ✅ Covered / ⚠️ Partial / ❌ No Coverage
4. Export to styled Excel / CSV download

### 🔍 Gap Analysis

1. FAISS docstore → story list
2. Jira REST API → live story content (Description + AC + Steps to Reproduce)
3. OpenAI GPT-4o → 5-section gap analysis (JSON)
4. Rendered in app + downloadable as Markdown report

**Gap analysis sections:**
- Requirement Summary
- Identified Gaps (Functional / Role & Permission / Data Validation / State & Edge Case / Integration / Non-Functional)
- Questions for the Product Owner
- Test Scope Estimate (with split recommendation if > 20 TCs)
- Automation Recommendation (Automate Now / Later / Manual Only)

---

## Infrastructure & Credentials

### Environment Variables

| Environment | File | Used by |
|-------------|------|---------|
| Local development | `rag/.env` (gitignored) | All pages via `load_dotenv()` |
| Streamlit Cloud | Settings → Secrets (UI) | Mapped to `os.environ` by `app.py` bridge |

### Required Secrets

| Key | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | GPT-4o generation |
| `OPENAI_MODEL` | Model name (e.g. `gpt-4o`) |
| `JIRA_URL` | Atlassian instance URL |
| `JIRA_USER` | Atlassian account email |
| `JIRA_TOKEN` | Atlassian API token |
| `JIRA_PROJECT` | Project key (e.g. `STUD`) |
| `TESTRAIL_URL` | TestRail instance URL |
| `TESTRAIL_USER` | TestRail account email |
| `TESTRAIL_TOKEN` | TestRail API key |
| `TESTRAIL_PROJECT_ID` | Numeric TestRail project ID |

---

## Deployment

- Hosted on Streamlit Community Cloud (free tier, 1 GB RAM)
- Auto-deploys on every push to `main` branch
- FAISS index is committed to the repo — app loads it at startup without re-ingesting

---

## How to Refresh the Knowledge Base

Run locally (requires network access to Jira and TestRail):

```bash
cd rag
python ingest_all.py
```

Then commit and push the updated index:

```bash
git add rag/faiss_index/index.faiss rag/faiss_index/index.pkl
git commit -m "Refresh RAG index - YYYY-MM-DD"
git push
```

The deployed app picks up the new index on next restart.

> **Recommended cadence:** After each sprint (to pick up new stories and test cases).

---

## Known Limitations

| Area | Limitation | Workaround |
|------|-----------|------------|
| Existing test case lookup | Uses FAISS similarity — may miss cases if title doesn't mention the story key | Step details fetched live from TestRail API |
| Coverage Dashboard | Matches by keyword/semantic similarity, not by TestRail refs field | Acceptable for now; direct API match is a future improvement |
| RAG freshness | Index reflects Jira/TestRail state at last ingest time | Re-ingest after each sprint |
| Memory | FAISS + MiniLM model ~250 MB — close to Streamlit Cloud 1 GB free limit | Single shared load via `shared_vectorstore.py` |
| Streamlit Cloud | Free tier goes to sleep after inactivity | First load after sleep takes ~30 seconds |

---

## Repo Structure

```
qa-intelligence-hub/
├── custom-agent-ui/
│   ├── app.py                        # Home page + secrets bridge
│   ├── shared_vectorstore.py         # Singleton FAISS loader (shared by all pages)
│   └── pages/
│       ├── 1_Test_Case_Generator.py
│       ├── 2_Coverage_Dashboard.py
│       └── 3_Gap_Analysis.py
├── rag/
│   ├── ingest_all.py                 # Run this to rebuild the knowledge base
│   ├── vectorstore.py                # FAISS build + save
│   ├── get_relevant_docs.py          # Similarity search helper
│   ├── faiss_index/                  # Committed index (do not delete)
│   ├── ingest/
│   │   ├── jira_ingest.py
│   │   ├── testrail_ingest.py
│   │   ├── pdf_ingest.py
│   │   ├── md_ingest.py
│   │   └── cypress_ingest.py
│   ├── docs/                         # Add Markdown product docs here
│   └── pdfs/                         # Add PDF product docs here
├── requirements.txt
└── runtime.txt                       # python-3.12
```
