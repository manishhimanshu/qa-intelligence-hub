"""Read-only TestRail API access for direct case-driven workflows."""
import html
import re
from html.parser import HTMLParser

import requests

from . import config

_CASE_ID_RE = re.compile(r"^(?:C)?(\d+)$", re.IGNORECASE)
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b", re.IGNORECASE)


class TestRailError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(str(value))
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]*>", " ", str(value))
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _configured_auth() -> tuple[str, str]:
    if not (config.TESTRAIL_URL and config.TESTRAIL_USER and config.TESTRAIL_TOKEN):
        raise TestRailError("TESTRAIL_URL, TESTRAIL_USER and TESTRAIL_TOKEN must be configured in rag/.env.")
    if not config.TESTRAIL_URL.lower().startswith("https://"):
        raise TestRailError("TestRail URL must use HTTPS; refusing to send credentials over an insecure connection.")
    return config.TESTRAIL_USER, config.TESTRAIL_TOKEN


def _get(endpoint: str) -> dict:
    auth = _configured_auth()
    url = f"{config.TESTRAIL_URL}/index.php?/api/v2/{endpoint}"
    try:
        response = requests.get(
            url,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except requests.RequestException as e:
        raise TestRailError(f"TestRail request failed: {type(e).__name__}.") from e
    if response.status_code in (401, 403):
        raise TestRailError(f"TestRail authentication or permission failure (HTTP {response.status_code}).")
    if response.status_code == 404:
        raise TestRailError("TestRail case or section was not found (HTTP 404).")
    if not response.ok:
        raise TestRailError(f"TestRail returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as e:
        raise TestRailError("TestRail returned invalid JSON.") from e


def normalize_case_id(case_id: str) -> tuple[str, str]:
    match = _CASE_ID_RE.fullmatch((case_id or "").strip())
    if not match:
        raise TestRailError(f"Invalid TestRail case ID {case_id!r}; expected a numeric ID such as C12345.")
    digits = match.group(1)
    return digits, f"C{digits}"


def fetch_case(case_id: str) -> dict:
    """Fetch and normalize one TestRail case live; no writes are exposed here."""
    numeric_id, canonical_id = normalize_case_id(case_id)
    raw = _get(f"get_case/{numeric_id}")

    steps = []
    separated = raw.get("custom_steps_separated") or []
    if isinstance(separated, list):
        for item in separated:
            if not isinstance(item, dict):
                continue
            action = _plain_text(item.get("content", ""))
            expected = _plain_text(item.get("expected", ""))
            if action or expected:
                steps.append({"action": action, "expected": expected})

    legacy_steps = _plain_text(raw.get("custom_steps", ""))
    expected_result = _plain_text(raw.get("custom_expected", ""))
    if not steps and legacy_steps:
        step_lines = [line.strip() for line in legacy_steps.splitlines() if line.strip()]
        steps = [{"action": line, "expected": ""} for line in step_lines]

    preconditions = _plain_text(raw.get("custom_preconds", ""))
    if preconditions.lower() == "none":
        preconditions = ""
    if expected_result.lower() == "none":
        expected_result = ""

    section_id = raw.get("section_id")
    section_name = ""
    if section_id is not None:
        try:
            section_name = _plain_text(_get(f"get_section/{section_id}").get("name", ""))
        except TestRailError as e:
            if "not found" not in str(e).lower():
                raise

    refs = sorted({match.upper() for match in _JIRA_KEY_RE.findall(str(raw.get("refs") or ""))})
    return {
        "case_id": canonical_id,
        "title": _plain_text(raw.get("title", "")),
        "section_id": section_id,
        "section_name": section_name,
        "suite_id": raw.get("suite_id"),
        "priority_id": raw.get("priority_id"),
        "preconditions": preconditions,
        "steps": steps,
        "legacy_expected_result": expected_result,
        "references": refs,
        "source": "testrail-live",
    }
