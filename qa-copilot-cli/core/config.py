import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
RAG_DIR = REPO_ROOT / "rag"

load_dotenv(RAG_DIR / ".env")

if sys.platform == "win32":
    # Corporate SSL interception requires the Windows certificate store.
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass

JIRA_URL = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_USER = os.getenv("JIRA_USER", "")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")

TESTRAIL_URL = os.getenv("TESTRAIL_URL", "").rstrip("/")
TESTRAIL_USER = os.getenv("TESTRAIL_USER", "")
TESTRAIL_TOKEN = os.getenv("TESTRAIL_TOKEN", "")
TESTRAIL_PROJECT_ID = os.getenv("TESTRAIL_PROJECT_ID", "")

FAISS_INDEX_DIR = RAG_DIR / os.getenv("FAISS_INDEX_PATH", "./faiss_index").lstrip("./")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FEATURE_ALIASES_PATH = RAG_DIR / "config" / "feature-aliases.json"

OUTPUT_DIR = Path(os.getenv("QA_CLI_OUTPUT_DIR", str(CLI_ROOT / "output"))).resolve()
_automation_repo_root = os.getenv("AUTOMATION_REPO_ROOT", "").strip()
AUTOMATION_REPO_ROOT = Path(_automation_repo_root).expanduser().resolve() if _automation_repo_root else None
_playwright_origins = os.getenv(
    "PLAYWRIGHT_ALLOWED_ORIGINS",
    "https://e2etest.pilyr.com;https://arontier.pilyr.com",
)
PLAYWRIGHT_ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/").lower()
    for origin in _playwright_origins.split(";")
    if origin.strip()
)

_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def validate_issue_key(key: str) -> str:
    """Normalise and validate a Jira key; it is used in URLs, JQL and file names."""
    normalised = (key or "").strip().upper()
    if not _ISSUE_KEY_RE.match(normalised):
        raise ValueError(f"Invalid Jira issue key: {key!r}. Expected format like STUD-123.")
    return normalised
