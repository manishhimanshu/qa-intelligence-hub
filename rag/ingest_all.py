"""
ingest_all.py — Kapost RAG Knowledge Base Builder

Run this script whenever you want to refresh the RAG index:
  cd C:\\Users\\mhimanshu\\Documents\\ph\\rag
  python ingest_all.py

Sources ingested:
  1. Jira stories and bugs from your Atlassian project
  2. TestRail test cases (all suites) from your TestRail project
  3. Product documentation PDFs from ./pdfs/
  4. Product documentation Markdown files from ./docs/
  5. Cypress automation patterns (specs + page objects + custom commands)

After running, the FAISS index is saved to ./faiss_index/ and will be
automatically picked up by the MCP retriever server.
"""
import os
import sys

# Load .env from this directory before anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Add ingest/ dir to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest"))

from ingest.jira_ingest      import fetch_jira_issues
from ingest.testrail_ingest  import ingest_testrail_cases
from ingest.pdf_ingest        import ingest_pdfs
from ingest.md_ingest         import ingest_markdown_dir
from ingest.cypress_ingest    import ingest_cypress_patterns
from ingest.automation_ingest import ingest_automation_repo
from vectorstore               import build_vectorstore

def run_ingestion(sources: list[str] = None) -> bool:
    """
    Run all (or selected) ingestion sources and build/update the FAISS index.
    The no-argument run rebuilds the index from scratch. Pass a subset list like
    ["jira", "testrail"] to add missing documents without replacing other sources.
    """
    # Keep legacy cypress ingestion optional; automation ingestion is the
    # default path for framework-grounded code generation.
    rebuild = not sources
    all_sources = sources or ["jira", "testrail", "pdf", "docs", "automation"]
    all_docs = []
    failed_sources = []

    # ── 1. Jira ──────────────────────────────────────────────────────────────
    if "jira" in all_sources:
        print("\n[1/5] Fetching Jira issues...")
        try:
            jira_docs = fetch_jira_issues()
            print(f"      ✓ {len(jira_docs)} Jira issues ingested.")
            all_docs.extend(jira_docs)
        except Exception as e:
            print(f"      ✗ Jira ingestion failed: {e}")
            failed_sources.append("jira")

    # ── 2. TestRail ──────────────────────────────────────────────────────────
    if "testrail" in all_sources:
        print("\n[2/5] Fetching TestRail test cases...")
        try:
            tr_docs = ingest_testrail_cases()
            print(f"      ✓ {len(tr_docs)} TestRail test cases ingested.")
            all_docs.extend(tr_docs)
        except Exception as e:
            print(f"      ✗ TestRail ingestion failed: {e}")
            failed_sources.append("testrail")

    # ── 3. PDFs ───────────────────────────────────────────────────────────────
    if "pdf" in all_sources:
        pdf_dir = os.getenv("PDF_DIR", "./docs/product_knowledge")
        print(f"\n[3/5] Ingesting PDFs from {pdf_dir}...")
        try:
            pdf_docs = ingest_pdfs(pdf_dir)
            print(f"      ✓ {len(pdf_docs)} PDF page chunks ingested.")
            all_docs.extend(pdf_docs)
        except Exception as e:
            print(f"      ✗ PDF ingestion failed: {e}")
            failed_sources.append("pdf")

    # ── 4. Markdown docs ──────────────────────────────────────────────────────
    if "docs" in all_sources:
        docs_dir = os.getenv("DOCS_DIR", "./docs")
        print(f"\n[4/5] Ingesting Markdown docs from {docs_dir}...")
        try:
            md_docs = ingest_markdown_dir(docs_dir)
            print(f"      ✓ {len(md_docs)} Markdown sections ingested.")
            all_docs.extend(md_docs)
        except Exception as e:
            print(f"      ✗ Markdown ingestion failed: {e}")
            failed_sources.append("docs")

    # ── 5. Cypress patterns ───────────────────────────────────────────────────
    if "cypress" in all_sources:
        cypress_root = (os.getenv("CYPRESS_ROOT") or "").strip()
        if not cypress_root:
            print("\n[5/6] Skipping legacy Cypress ingest: CYPRESS_ROOT is empty.")
        else:
            print(f"\n[5/6] Ingesting Cypress patterns from {cypress_root}...")
            try:
                cy_docs = ingest_cypress_patterns(cypress_root)
                print(f"      ✓ {len(cy_docs)} Cypress knowledge chunks ingested.")
                all_docs.extend(cy_docs)
            except Exception as e:
                print(f"      ✗ Cypress ingestion failed: {e}")
                failed_sources.append("cypress")

    # ── 6. Automation repository patterns ────────────────────────────────────
    if "automation" in all_sources:
        automation_root = os.getenv("AUTOMATION_REPO_ROOT", "C:/Users/mhimanshu/Documents/ph")
        print(f"\n[6/6] Ingesting automation repository from {automation_root}...")
        try:
            auto_docs = ingest_automation_repo(automation_root)
            print(f"      ✓ {len(auto_docs)} automation knowledge chunks ingested.")
            all_docs.extend(auto_docs)
        except Exception as e:
            print(f"      ✗ Automation ingestion failed: {e}")
            failed_sources.append("automation")

    # ── Build / update vectorstore ────────────────────────────────────────────
    if rebuild and failed_sources:
        print(
            "\nFresh rebuild aborted because these sources failed: "
            f"{', '.join(failed_sources)}. The existing index was left unchanged."
        )
        return False
    if not all_docs:
        print("\n⚠  No documents ingested. Check your .env credentials and source directories.")
        return False

    operation = "fresh FAISS index" if rebuild else "FAISS index update"
    print(f"\nBuilding {operation} from {len(all_docs)} total documents...")
    build_vectorstore(all_docs, persist=True, rebuild=rebuild)
    print(f"✓ FAISS index saved to: {os.path.abspath(os.getenv('FAISS_INDEX_PATH', './faiss_index'))}")
    print("\nRAG knowledge base is ready. The MCP retriever will now use this index.")
    return True


if __name__ == "__main__":
    # Allow running specific sources: python ingest_all.py jira testrail
    sources = sys.argv[1:] if len(sys.argv) > 1 else None
    if not run_ingestion(sources):
        raise SystemExit(1)
