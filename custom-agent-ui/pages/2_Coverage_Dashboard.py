"""
Coverage Dashboard
All-stories Jira ↔ TestRail traceability matrix.
Shows coverage status across every story in the project,
allows filtering, and exports to styled Excel or CSV.
"""

import os
import sys
import re
import io
import requests
from datetime import datetime
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Path / env setup ─────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, "../../rag"))
load_dotenv(os.path.join(_DIR, "../../rag/.env"))

st.set_page_config(page_title="Coverage Dashboard", page_icon="📊", layout="wide")

JIRA_URL   = os.getenv("JIRA_URL",   "").rstrip("/")
JIRA_USER  = os.getenv("JIRA_USER",  "")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")


# ── RAG helper ────────────────────────────────────────────────────────────────
def rag_query(query: str, top_k: int = 20) -> list:
    from get_relevant_docs import get_relevant_docs
    return get_relevant_docs(query, top_k=top_k)


# Shared singleton loader — ONE @st.cache_resource across all pages prevents triple FAISS load
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_UI_DIR, ".."))
from shared_vectorstore import load_vectorstore as _load_vectorstore


@st.cache_data(show_spinner="Loading Jira stories from RAG…")
def load_all_stories() -> list:
    """
    Iterate ALL documents in the FAISS docstore and return every unique
    Jira issue key. Using docstore iteration (not similarity search) means
    the full 16 000+ story index is available, not just top-k neighbours.
    """
    import re

    vs = _load_vectorstore()
    if vs is None:
        st.error("RAG index not found. Run `python ingest_all.py` first.")
        return []

    stories, seen = [], set()
    for langchain_doc in vs.docstore._dict.values():
        if not hasattr(langchain_doc, "metadata"):
            continue
        meta = langchain_doc.metadata
        if meta.get("source") != "jira":
            continue

        # Strip _chunkN suffix to get the canonical Jira key
        doc_id = meta.get("id", "")
        key    = doc_id.split("_chunk")[0] if "_chunk" in doc_id else doc_id
        if not key or key in seen:
            continue
        seen.add(key)

        content    = langchain_doc.page_content
        lines      = [l.strip() for l in content.splitlines() if l.strip()]
        # Content format: "Jira Issue: KEY\nType: … | … | Status: …\n…\nSummary: <text>"
        summary    = key
        issuetype  = meta.get("type", "Story")
        status     = meta.get("status", "Unknown")
        for line in lines:
            if re.match(r'summary:', line, re.IGNORECASE):
                summary = line.split(":", 1)[-1].strip()
                break

        stories.append({"key": key, "summary": summary,
                         "issuetype": issuetype, "status": status})

    return sorted(stories, key=lambda x: (
        x["key"].split("-")[0],
        int(re.search(r'\d+$', x["key"]).group(0)) if re.search(r'\d+$', x["key"]) else 0
    ))


@st.cache_data(show_spinner="Building TestRail keyword index…")
def build_testrail_index() -> list:
    """
    Load ALL TestRail cases from the FAISS docstore into a flat list of
    {id, title_lower, content_lower} dicts for fast keyword matching.
    This avoids the top_k cap that causes FAISS similarity search to miss cases.
    """
    vs = _load_vectorstore()
    if vs is None:
        return []
    cases = []
    for doc in vs.docstore._dict.values():
        if not hasattr(doc, "metadata"):
            continue
        if doc.metadata.get("source") != "testrail":
            continue
        doc_id  = doc.metadata.get("id", "")
        content = doc.page_content.lower()
        # Extract title line for fast matching
        title = ""
        for line in doc.page_content.splitlines():
            if line.lower().startswith("title:"):
                title = line.split(":", 1)[-1].strip().lower()
                break
        cases.append({"id": doc_id, "title": title, "content": content})
    return cases


def check_story_coverage(story_key: str, summary: str) -> dict:
    """
    Check TestRail coverage by keyword matching across ALL indexed cases.

    Strategy (in priority order):
    1. Jira story key appears literally in the TestRail case content (most reliable)
    2. Significant words from the story summary appear in the case title/content
       (handles cases where the Jira key isn't referenced but the feature is)

    This replaces the old FAISS top_k=12 similarity search which missed >80% of
    valid matches due to the hard cap and semantic vocabulary mismatches.
    """
    tr_cases = build_testrail_index()
    if not tr_cases:
        # Fallback to old similarity method if index empty
        docs = rag_query(f"{story_key} {summary}", top_k=30)
        tcs  = []
        for doc in docs:
            doc_id = doc.get("id", "")
            if doc_id.startswith("testrail_"):
                m = re.search(r'testrail_(\d+)', doc_id)
                tcs.append(f"C{m.group(1)}" if m else doc_id)
        tc_count = len(tcs)
        coverage = "Covered" if tc_count >= 2 else "Partial" if tc_count == 1 else "No Coverage"
        return {"test_cases": tcs, "tc_count": tc_count, "coverage": coverage}

    story_key_lower = story_key.lower()

    # Build keyword set from summary — strip short/common words
    stop = {"a","an","the","and","or","of","to","in","is","it","for","with",
            "as","at","by","on","be","that","this","can","are","was","has","have",
            "not","but","when","from","they","its","all","been","will","would",
            "should","could","there","their","which","than","into","more","also"}
    summary_words = [
        w.lower().strip(".,;:!?()[]'\"")
        for w in summary.split()
        if len(w) > 3 and w.lower().strip(".,;:!?()[]'\"") not in stop
    ]
    # Keep up to 8 most distinctive (longest) words
    keyword_set = sorted(set(summary_words), key=len, reverse=True)[:8]

    matched_ids = []
    for case in tr_cases:
        content = case["content"]
        title   = case["title"]

        # Priority 1: story key mentioned directly (e.g. "STUD-17260")
        if story_key_lower in content:
            matched_ids.append(case["id"])
            continue

        # Priority 2: keyword match
        # Check title separately (higher weight — title is more precise)
        if keyword_set:
            title_hits   = sum(1 for kw in keyword_set if kw in title)
            content_hits = sum(1 for kw in keyword_set if kw in content)

            # Strong title match: ≥40% of keywords in the title alone
            title_threshold = max(1, round(len(keyword_set) * 0.4))
            if title_hits >= title_threshold:
                matched_ids.append(case["id"])
                continue

            # Content match: ≥50% of keywords appear anywhere in the content
            content_threshold = max(2, round(len(keyword_set) * 0.5))
            if content_hits >= content_threshold:
                matched_ids.append(case["id"])

    tcs = []
    for doc_id in matched_ids:
        m = re.search(r'testrail_(\d+)', doc_id)
        tcs.append(f"C{m.group(1)}" if m else doc_id)

    tc_count = len(tcs)
    coverage = "Covered" if tc_count >= 2 else "Partial" if tc_count == 1 else "No Coverage"
    return {"test_cases": tcs, "tc_count": tc_count, "coverage": coverage}


def build_coverage_matrix(stories: list, progress_bar) -> list:
    matrix = []
    for i, story in enumerate(stories):
        progress_bar.progress((i + 1) / len(stories), text=f"Checking {story['key']}…")
        cov = check_story_coverage(story["key"], story["summary"])
        matrix.append({
            "jira_key":   story["key"],
            "summary":    story["summary"],
            "issuetype":  story["issuetype"],
            "status":     story["status"],
            "test_cases": cov["test_cases"],
            "tc_count":   cov["tc_count"],
            "coverage":   cov["coverage"],
        })
    return matrix


@st.cache_data(show_spinner="Fetching epic children from Jira…", ttl=600)
def fetch_epic_children(epic_key: str) -> list:
    """Fetch all child issues of an epic via POST /rest/api/3/search/jql."""
    if not (JIRA_URL and JIRA_USER and JIRA_TOKEN):
        return []
    try:
        jql  = f'(parent = "{epic_key}" OR "Epic Link" = "{epic_key}") ORDER BY created ASC'
        url  = f"{JIRA_URL}/rest/api/3/search/jql"
        all_issues: list       = []
        next_page_token: str | None = None

        while True:
            body: dict = {
                "jql": jql, "maxResults": 100,
                "fields": ["summary", "status", "issuetype"],
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            r = requests.post(
                url,
                auth=(JIRA_USER, JIRA_TOKEN),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=body, timeout=15,
            )
            if r.status_code != 200:
                st.error(f"Jira API error {r.status_code}: {r.text[:300]}")
                break

            data   = r.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            next_page_token = data.get("nextPageToken")
            if not next_page_token or not issues:
                break

        seen, unique = set(), []
        for issue in all_issues:
            if issue["key"] not in seen:
                seen.add(issue["key"])
                unique.append({
                    "key":       issue["key"],
                    "summary":   issue["fields"].get("summary", issue["key"]),
                    "issuetype": (issue["fields"].get("issuetype") or {}).get("name", "Story"),
                    "status":    (issue["fields"].get("status")    or {}).get("name", "Unknown"),
                })
        return unique
    except Exception as e:
        st.error(f"Failed to fetch epic children: {e}")
        return []


# ── Excel export ──────────────────────────────────────────────────────────────
def build_excel_report(matrix: list) -> bytes:
    wb = openpyxl.Workbook()

    # Styles
    hdr_fill  = PatternFill("solid", fgColor="1F3864")
    cov_fill  = PatternFill("solid", fgColor="C6EFCE")
    part_fill = PatternFill("solid", fgColor="FFEB9C")
    gap_fill  = PatternFill("solid", fgColor="FFC7CE")
    alt_fill  = PatternFill("solid", fgColor="F2F2F2")
    thin      = Side(style="thin", color="CCCCCC")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)
    center    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_w    = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    hdr_font  = Font(bold=True, color="FFFFFF", size=11)
    ttl_font  = Font(bold=True, size=14, color="1F3864")
    bld_font  = Font(bold=True)

    # ── Sheet 1: Detail ───────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Coverage Gap Report"

    ws.merge_cells("A1:F1")
    ws["A1"] = "Test Coverage Gap Report"
    ws["A1"].font      = ttl_font
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:F2")
    ws["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws["A2"].alignment = center
    ws.row_dimensions[2].height = 18

    headers = ["Jira Key", "Summary", "Issue Type", "Status", "Test Cases", "Coverage"]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.fill, cell.font, cell.alignment, cell.border = hdr_fill, hdr_font, center, border
    ws.row_dimensions[3].height = 22

    coverage_fills = {"Covered": cov_fill, "Partial": part_fill, "No Coverage": gap_fill}
    for row_idx, item in enumerate(matrix, start=4):
        cov  = item.get("coverage", "No Coverage")
        c_fill = coverage_fills.get(cov, gap_fill)
        use_alt = (row_idx % 2 == 0)
        values = [
            item.get("jira_key", ""),
            item.get("summary", ""),
            item.get("issuetype", ""),
            item.get("status", ""),
            ", ".join(item.get("test_cases", [])) or "—",
            cov,
        ]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border    = border
            cell.alignment = left_w if col == 2 else center
            if col == 6:
                cell.fill = c_fill
                cell.font = bld_font
            elif use_alt:
                cell.fill = alt_fill
        ws.row_dimensions[row_idx].height = 20

    for col, width in enumerate([12, 45, 14, 16, 28, 16], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"

    # ── Sheet 2: Summary ──────────────────────────────────────────────────────
    ws2   = wb.create_sheet("Summary")
    total = len(matrix)
    cov_c = sum(1 for r in matrix if r.get("coverage") == "Covered")
    par_c = sum(1 for r in matrix if r.get("coverage") == "Partial")
    gap_c = sum(1 for r in matrix if r.get("coverage") == "No Coverage")

    ws2.merge_cells("A1:C1")
    ws2["A1"] = "Coverage Summary"
    ws2["A1"].font      = ttl_font
    ws2["A1"].alignment = center
    ws2.row_dimensions[1].height = 30

    def pct(n):
        return f"{round(n / total * 100, 1) if total else 0}%"

    summary_rows = [
        ("Metric",              "Count", "Percentage"),
        ("Total Jira Stories",  total,   "100%"),
        ("Covered",             cov_c,   pct(cov_c)),
        ("Partial Coverage",    par_c,   pct(par_c)),
        ("No Coverage (Gap)",   gap_c,   pct(gap_c)),
    ]
    row_fills = [hdr_fill, None, cov_fill, part_fill, gap_fill]
    for r, (row_data, fill) in enumerate(zip(summary_rows, row_fills), start=2):
        for c, val in enumerate(row_data, start=1):
            cell = ws2.cell(row=r, column=c, value=val)
            cell.border    = border
            cell.alignment = center
            if fill:
                cell.fill = fill
            if r == 2:
                cell.font = hdr_font
            elif r == 6:
                cell.font = bld_font
        ws2.row_dimensions[r].height = 22

    ws2["A8"] = "Stories with No Test Coverage:"
    ws2["A8"].font = bld_font
    for i, s in enumerate([r for r in matrix if r.get("coverage") == "No Coverage"], start=9):
        ws2.cell(row=i, column=1, value=s.get("jira_key", "")).fill = gap_fill
        cell = ws2.cell(row=i, column=2, value=s.get("summary", ""))
        cell.alignment = left_w

    for col in range(1, 4):
        ws2.column_dimensions[get_column_letter(col)].width = 20 if col > 1 else 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("📊 Coverage Dashboard")
st.caption("Jira ↔ TestRail traceability matrix — run for all stories, specific stories, or a full epic")

all_stories = load_all_stories()
if not all_stories:
    st.error("No Jira stories found in RAG. Run `python rag/ingest_all.py`.")
    st.stop()

story_map = {s["key"]: s for s in all_stories}

# ── Mode selector ─────────────────────────────────────────────────────────────
col_mode, col_refresh = st.columns([5, 1])
with col_mode:
    mode = st.radio(
        "Coverage Scope",
        ["📋 All Stories", "🔷 Specific Stories", "🔶 By Epic"],
        horizontal=True,
        label_visibility="collapsed",
    )
with col_refresh:
    if st.button("🔄 Refresh", help="Clear cache and reload all"):
        for k in list(st.session_state.keys()):
            if k.startswith("coverage_") or k in ("epic_cov_children", "epic_cov_key"):
                del st.session_state[k]
        st.cache_data.clear()
        st.rerun()

# ── Scope: All Stories ────────────────────────────────────────────────────────
if mode == "📋 All Stories":
    state_key      = "coverage_matrix_all"
    stories_to_run = all_stories
    scope_label    = f"all **{len(all_stories)}** Jira stories"

# ── Scope: Specific Stories ───────────────────────────────────────────────────
elif mode == "🔷 Specific Stories":
    story_opts = {f"{s['key']}  —  {s['summary'][:70]}": s for s in all_stories}
    sel_labels = st.multiselect(
        "📋 Select Stories",
        list(story_opts.keys()),
        max_selections=50,
        placeholder="Type a story key or keyword…",
    )
    stories_to_run = [story_opts[l] for l in sel_labels]
    state_key      = "coverage_matrix_sel_" + "_".join(sorted(s["key"] for s in stories_to_run))
    scope_label    = f"**{len(stories_to_run)}** selected stor{'y' if len(stories_to_run)==1 else 'ies'}"
    if not stories_to_run:
        st.info("Select one or more stories above to run coverage analysis.")
        st.stop()

# ── Scope: By Epic ────────────────────────────────────────────────────────────
elif mode == "🔶 By Epic":
    col_epic, col_fetch = st.columns([3, 1])
    with col_epic:
        epic_key_input = st.text_input("🏷️ Epic Key", placeholder="e.g. STUD-17781").strip().upper()
    with col_fetch:
        st.write("")
        fetch_clicked = st.button("🔍 Fetch Stories", use_container_width=True)

    if fetch_clicked and epic_key_input:
        with st.spinner(f"Fetching stories under {epic_key_input}…"):
            children = fetch_epic_children(epic_key_input)
        if children:
            st.session_state["epic_cov_children"] = children
            st.session_state["epic_cov_key"]      = epic_key_input
            st.success(f"Found **{len(children)}** stories under **{epic_key_input}**")
        else:
            st.warning("No stories found. Check the epic key and Jira credentials.")
    elif fetch_clicked and not epic_key_input:
        st.warning("Please enter an Epic key first.")

    children      = st.session_state.get("epic_cov_children", [])
    epic_cov_key  = st.session_state.get("epic_cov_key", "")

    if not children:
        st.info("Enter an Epic key and click **Fetch Stories** to load its children.")
        st.stop()

    st.caption(f"**{len(children)}** stories found under **{epic_cov_key}** — deselect any to exclude:")
    child_opts  = {f"{c['key']}  —  {c['summary'][:70]}": c for c in children}
    sel_labels  = st.multiselect(
        "Stories to include",
        list(child_opts.keys()),
        default=list(child_opts.keys()),
        label_visibility="collapsed",
    )
    stories_to_run = []
    for lbl in sel_labels:
        child = child_opts[lbl]
        # Enrich with RAG metadata if available, otherwise use Jira basic info
        rag   = story_map.get(child["key"], child)
        stories_to_run.append({
            "key":       child["key"],
            "summary":   child["summary"],
            "issuetype": child.get("issuetype", rag.get("issuetype", "Story")),
            "status":    child.get("status",    rag.get("status",    "Unknown")),
        })
    state_key   = "coverage_matrix_epic_" + epic_cov_key
    scope_label = f"epic **{epic_cov_key}** ({len(stories_to_run)} stories)"
    if not stories_to_run:
        st.info("Select at least one story to run coverage.")
        st.stop()

# ── Run analysis button ───────────────────────────────────────────────────────
if state_key not in st.session_state:
    st.session_state[state_key] = []

if not st.session_state[state_key]:
    st.info(f"Ready to check TestRail coverage for {scope_label}. This runs entirely locally — no API cost.")
    if st.button("📊 Run Coverage Analysis", type="primary"):
        progress = st.progress(0, text="Starting coverage analysis…")
        st.session_state[state_key] = build_coverage_matrix(stories_to_run, progress)
        progress.empty()
        st.success("✅ Coverage analysis complete!")
        st.rerun()
    st.stop()

matrix = st.session_state[state_key]

# ── Summary metrics ────────────────────────────────────────────────────────────
total   = len(matrix)
covered = sum(1 for r in matrix if r["coverage"] == "Covered")
partial = sum(1 for r in matrix if r["coverage"] == "Partial")
gaps    = sum(1 for r in matrix if r["coverage"] == "No Coverage")
pct     = round(covered / total * 100, 1) if total else 0

st.divider()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Stories",   total)
m2.metric("✅ Covered",      covered, delta=f"{pct}%")
m3.metric("⚠️ Partial",      partial)
m4.metric("❌ No Coverage",  gaps)
m5.metric("Coverage %",      f"{pct}%")
st.divider()

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("🔎 Filters")
    cov_filter  = st.multiselect(
        "Coverage Status",
        ["Covered", "Partial", "No Coverage"],
        default=["Covered", "Partial", "No Coverage"],
    )
    type_filter = st.multiselect(
        "Issue Type",
        sorted(set(r["issuetype"] for r in matrix)),
        default=sorted(set(r["issuetype"] for r in matrix)),
    )
    status_filter = st.multiselect(
        "Jira Status",
        sorted(set(r["status"] for r in matrix)),
        default=sorted(set(r["status"] for r in matrix)),
    )

filtered = [
    r for r in matrix
    if r["coverage"]  in cov_filter
    and r["issuetype"] in type_filter
    and r["status"]    in status_filter
]

# ── Table ──────────────────────────────────────────────────────────────────────
COVERAGE_ICONS = {
    "Covered":     "✅ Covered",
    "Partial":     "⚠️ Partial",
    "No Coverage": "❌ No Coverage",
}

st.subheader(f"Showing {len(filtered)} / {total} stories")

df = pd.DataFrame([
    {
        "Jira Key":   r["jira_key"],
        "Summary":    r["summary"],
        "Type":       r["issuetype"],
        "Status":     r["status"],
        "TC Count":   r["tc_count"],
        "Test Cases": ", ".join(r["test_cases"]) or "—",
        "Coverage":   COVERAGE_ICONS.get(r["coverage"], r["coverage"]),
    }
    for r in filtered
])


def _colour_coverage(val: str) -> str:
    v = str(val)
    if "✅" in v:
        return "background-color: #C6EFCE; color: #276221; font-weight: bold"
    if "⚠️" in v:
        return "background-color: #FFEB9C; color: #7c5b00; font-weight: bold"
    if "❌" in v:
        return "background-color: #FFC7CE; color: #9C0006; font-weight: bold"
    return ""


st.dataframe(
    df.style.map(_colour_coverage, subset=["Coverage"]),
    height=520,
    use_container_width=True,
)

# ── Export ─────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📥 Export")

col_xl, col_csv = st.columns(2)
_fname_tag = st.session_state.get("epic_cov_key", "") if mode == "🔶 By Epic" else datetime.now().strftime('%Y%m%d_%H%M%S')
with col_xl:
    excel_bytes = build_excel_report(matrix)
    st.download_button(
        label="📥 Download Traceability Matrix (Excel)",
        data=excel_bytes,
        file_name=f"coverage_gap_report_{_fname_tag}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

with col_csv:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Filtered View (CSV)",
        data=csv_bytes,
        file_name=f"coverage_filtered_{_fname_tag}.csv",
        mime="text/csv",
    )
