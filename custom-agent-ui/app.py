"""
QA Intelligence Hub — Home Dashboard
Multi-page Streamlit app for QA teams:
  1. Generate structured manual test cases from Jira stories (→ Test Case Generator)
  2. View all-stories Jira ↔ TestRail coverage matrix (→ Coverage Dashboard)
  3. Run structured requirement gap analysis (→ Gap Analysis)
"""

import os
import sys
import streamlit as st
from dotenv import load_dotenv

# ── Path / env setup ────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, "../rag"))
load_dotenv(os.path.join(_DIR, "../rag/.env"))

# ── Streamlit Cloud: bridge st.secrets → os.environ ─────────────────────────
# On Streamlit Community Cloud os.getenv() only sees env vars if we map them
# here. Has no effect when running locally (st.secrets will be empty).
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

st.set_page_config(
    page_title="QA Intelligence Hub",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Header ───────────────────────────────────────────────────────────────────
st.title("🧪 QA Intelligence Hub")
st.caption("Powered by RAG · GPT-4o · Jira · TestRail  |  Kapost / Pilyr QA Suite")
st.divider()

# ── Feature navigation cards ─────────────────────────────────────────────────
st.subheader("Select a tool to get started:")

c1, c2, c3 = st.columns(3)

with c1:
    st.info(
        "### 📝 Test Case Generator\n"
        "Generate structured manual test cases from any Jira story.\n\n"
        "- Extracts Acceptance Criteria from Jira/RAG\n"
        "- Shows existing TestRail test cases\n"
        "- Generates missing cases: happy path, negative, role-based, edge cases\n"
        "- Format: **TC-FEATURE-NNN** with Priority, Type, Steps, Expected Result\n"
        "- Covers all 4 roles: admin / editor / contributor / consumer\n"
        "- **Exports directly to TestRail**"
    )
    st.page_link("pages/1_Test_Case_Generator.py", label="📝 Open Test Case Generator")

with c2:
    st.warning(
        "### 📊 Coverage Dashboard\n"
        "See test coverage across **ALL** Jira stories in one view.\n\n"
        "- Loads all stories from the project\n"
        "- Checks TestRail coverage per story\n"
        "- Color-coded: ✅ Covered / ⚠️ Partial / ❌ No Coverage\n"
        "- Filter by status, issue type, coverage level\n"
        "- **Export traceability matrix to Excel**\n"
        "- Download filtered view as CSV"
    )
    st.page_link("pages/2_Coverage_Dashboard.py", label="📊 Open Coverage Dashboard")

with c3:
    st.error(
        "### 🔍 Gap Analysis\n"
        "Structured requirement gap analysis for any Jira story.\n\n"
        "- Requirement Summary (what is explicitly defined)\n"
        "- Functional, Role, Data Validation, State & Edge Case gaps\n"
        "- Integration and Non-Functional gaps\n"
        "- Numbered **Questions for Product Owner**\n"
        "- Test scope estimate (flags stories > 20 TCs)\n"
        "- Automation recommendation\n"
        "- **Download as Markdown**"
    )
    st.page_link("pages/3_Gap_Analysis.py", label="🔍 Open Gap Analysis")

st.divider()

# ── System status ─────────────────────────────────────────────────────────────
st.subheader("🔌 System Status")

col1, col2, col3, col4 = st.columns(4)

faiss_path = os.path.join(_DIR, "../rag/faiss_index")
col1.metric("RAG (FAISS Index)", "✅ Ready" if os.path.exists(faiss_path) else "❌ Not built")
try:
    import requests as _r
    _ollama_ok = _r.get("http://localhost:11434", timeout=1).ok
except Exception:
    _ollama_ok = False
col2.metric("OpenAI API Key",   "✅ Set" if os.getenv("OPENAI_API_KEY") else "❌ Missing")
col3.metric("TestRail",          "✅ Set"   if os.getenv("TESTRAIL_URL")    else "⚠️ Not configured")
col4.metric("Jira",              "✅ Set"   if os.getenv("JIRA_URL")        else "⚠️ Not configured")

if not os.path.exists(faiss_path):
    st.warning(
        "⚠️ RAG index not found. Run `python rag/ingest_all.py` to build the FAISS index "
        "from Jira and TestRail. The app will not load stories until this is done."
    )

st.divider()

# ── Architecture reference ─────────────────────────────────────────────────────
with st.expander("ℹ️ Architecture & Data Flow"):
    st.markdown("""
    **Data ingestion pipeline (run once, then refresh as needed):**
    ```
    Jira API    ──→  rag/ingest/jira_ingest.py    ──→ FAISS vectorstore
    TestRail    ──→  rag/ingest/testrail_ingest.py ──┘
    Cypress specs → rag/ingest/cypress_ingest.py   ──┘
    PDFs        ──→  rag/ingest/pdf_ingest.py       ──┘
    ```
    Refresh:  `python rag/ingest_all.py`

    **Page responsibilities:**

    | Page | What it does |
    |------|-------------|
    | **Test Case Generator** | Per-story TC generation → TestRail export |
    | **Coverage Dashboard** | All-stories coverage matrix → Excel / CSV export |
    | **Gap Analysis** | Structured AC gap analysis per story → Markdown download |

    **Coverage thresholds:**  ≥ 2 TestRail TCs = Covered · 1 TC = Partial · 0 = No Coverage

    **Credentials:** All read from `rag/.env`  (never hardcoded)
    """)

# ── Workflow guide ────────────────────────────────────────────────────────────
with st.expander("📖 Recommended QA Workflow"):
    st.markdown("""
    1. **Ingest data** — run `python rag/ingest_all.py` to index Jira + TestRail
    2. **Coverage Dashboard** — identify which stories have no test coverage (red rows)
    3. **Gap Analysis** — for each uncovered story, run gap analysis; share PO questions
    4. **Test Case Generator** — generate structured test cases, review, then push to TestRail
    5. **Re-run ingest** when new stories or test cases are added to keep the index fresh
    """)



