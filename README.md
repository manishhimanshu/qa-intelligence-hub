# QA Intelligence Hub

An internal AI-powered tool that automates test case generation, coverage analysis, and requirement gap analysis for the Kapost platform.

> **Full documentation:** [QA_Intelligence_Hub_Documentation.md](QA_Intelligence_Hub_Documentation.md)

---

## What It Does

| Page | Purpose |
|---|---|
| 📝 **Test Case Generator** | Select any Jira story → AI generates structured test cases from AC → export to TestRail in one click |
| 📊 **Coverage Dashboard** | Full Jira ↔ TestRail traceability matrix across all stories — filterable, exportable to Excel |
| 🔍 **Gap Analysis** | AI-driven requirement gap analysis for any story or epic — identifies missing scenarios, generates PO questions |

---

## Tech Stack

- **Frontend:** Streamlit (Python)
- **LLM:** OpenAI GPT-4o (test case generation + gap analysis)
- **Vector Search:** FAISS + HuggingFace `all-MiniLM-L6-v2` (local embeddings)
- **Integrations:** Jira REST API v3, TestRail REST API v2

---

## Local Setup

**Prerequisites:** Python 3.12, Git LFS installed

```bash
# Clone
git clone https://github.com/manishhimanshu/qa-intelligence-hub.git
cd qa-intelligence-hub

# Install dependencies
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install -r custom-agent-ui/requirements.txt

# Configure credentials
cp rag/.env.example rag/.env    # then fill in your keys

# Run
.venv\Scripts\streamlit.exe run custom-agent-ui/app.py
```

Open `http://localhost:8501` in your browser.

---

## Environment Variables

Create `rag/.env` with the following:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
JIRA_URL=https://your-instance.atlassian.net
JIRA_USER=your@email.com
JIRA_TOKEN=...
JIRA_PROJECT=STUD
TESTRAIL_URL=https://your-instance.testrail.com
TESTRAIL_USER=your@email.com
TESTRAIL_TOKEN=...
TESTRAIL_PROJECT_ID=34
```

---

## Refreshing the Knowledge Base (RAG Index)

Run locally when you want to pick up new Jira stories or TestRail cases:

```bash
$env:PYTHONIOENCODING="utf-8"
cd rag
..\.venv\Scripts\python.exe ingest_all.py
```

Then commit and push the updated index:

```bash
git add rag/faiss_index/
git commit -m "Refresh RAG index - YYYY-MM-DD"
git push
```

> Recommended cadence: after each sprint.

---

## Project Structure

```
custom-agent-ui/
  app.py                      ← Streamlit app entry point
  shared_vectorstore.py       ← Shared FAISS loader (singleton)
  pages/
    1_Test_Case_Generator.py
    2_Coverage_Dashboard.py
    3_Gap_Analysis.py
rag/
  ingest_all.py               ← Rebuild the RAG index
  vectorstore.py              ← FAISS build/load
  get_relevant_docs.py        ← Similarity search
  faiss_index/                ← Binary index (Git LFS)
  ingest/                     ← Per-source ingest modules
requirements.txt
```
