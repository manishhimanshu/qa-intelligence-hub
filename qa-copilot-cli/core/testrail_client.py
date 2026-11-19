"""TestRail API access for read workflows and explicitly approved case creation."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

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


def _get(endpoint: str) -> dict | list:
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


def _request(method: str, url: str, **kwargs) -> dict:
    auth = _configured_auth()
    try:
        response = requests.request(
            method,
            url,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=20,
            **kwargs,
        )
    except requests.RequestException as e:
        detail = " The write outcome may be unknown; verify TestRail before retrying." if method == "POST" else ""
        raise TestRailError(f"TestRail request failed: {type(e).__name__}.{detail}") from e
    if response.status_code in (401, 403):
        raise TestRailError(f"TestRail authentication or permission failure (HTTP {response.status_code}).")
    if response.status_code == 404:
        raise TestRailError("TestRail suite, section or case was not found (HTTP 404).")
    if not response.ok:
        detail = " Verify TestRail before retrying if the case may have been created." if method == "POST" else ""
        raise TestRailError(f"TestRail returned HTTP {response.status_code}.{detail}")
    try:
        data = response.json()
    except ValueError as e:
        detail = " The write may have succeeded; verify TestRail before retrying." if method == "POST" else ""
        raise TestRailError(f"TestRail returned invalid JSON.{detail}") from e
    if not isinstance(data, dict):
        raise TestRailError("TestRail returned an unexpected response shape.")
    return data


def _get_all(endpoint: str, list_key: str) -> list[dict]:
    _configured_auth()
    url = f"{config.TESTRAIL_URL}/index.php?/api/v2/{endpoint}"
    results = []
    while url:
        data = _request("GET", url)
        items = data.get(list_key)
        if not isinstance(items, list):
            raise TestRailError(f"TestRail returned an invalid {list_key} list.")
        results.extend(item for item in items if isinstance(item, dict))
        next_link = (data.get("_links") or {}).get("next")
        if not next_link:
            url = ""
        elif str(next_link).startswith("http"):
            next_url = urlparse(str(next_link))
            if next_url.scheme != "https" or next_url.netloc.lower() != urlparse(config.TESTRAIL_URL).netloc.lower():
                raise TestRailError("TestRail returned an unsafe pagination URL.")
            url = str(next_link)
        elif str(next_link).startswith("/api/v2"):
            url = f"{config.TESTRAIL_URL}/index.php?{next_link}"
        else:
            url = f"{config.TESTRAIL_URL}{next_link}"
    return results


def _positive_id(value, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as e:
        raise TestRailError(f"Invalid TestRail {label} ID.") from e
    if result <= 0:
        raise TestRailError(f"Invalid TestRail {label} ID.")
    return result


def export_priority_mapping() -> dict[str, dict]:
    """Resolve export priorities by configured names, never by display order or assumed IDs."""
    data = _get("get_priorities")
    if not isinstance(data, list):
        raise TestRailError("TestRail returned an invalid priorities list.")
    names = {
        "Critical": "1 - Base level test",
        "High": "3 - Functional",
        "Medium": "3 - Functional",
        "Low": "4 - Edge case",
    }

    def normalized(name: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", name.casefold()))

    mapping = {}
    for priority, name in names.items():
        matches = [
            item for item in data
            if isinstance(item, dict) and normalized(str(item.get("name", ""))) == normalized(name)
        ]
        if len(matches) != 1:
            raise TestRailError(f"Expected exactly one TestRail priority named '{name}'; export blocked.")
        mapping[priority] = {
            "id": _positive_id(matches[0].get("id"), "priority"),
            "name": str(matches[0]["name"]),
        }
    return mapping


def list_suites() -> list[dict]:
    project_id = _positive_id(config.TESTRAIL_PROJECT_ID, "project")
    suites = _get_all(f"get_suites/{project_id}", "suites")
    return [{
        "id": _positive_id(item.get("id"), "suite"),
        "name": _plain_text(item.get("name", "")),
    } for item in suites]


def list_sections(suite_id: int) -> list[dict]:
    project_id = _positive_id(config.TESTRAIL_PROJECT_ID, "project")
    suite_id = _positive_id(suite_id, "suite")
    sections = _get_all(f"get_sections/{project_id}&suite_id={suite_id}", "sections")
    return [{
        "id": _positive_id(item.get("id"), "section"),
        "name": _plain_text(item.get("name", "")),
        "suite_id": item.get("suite_id"),
    } for item in sections]


def list_cases(suite_id: int) -> list[dict]:
    project_id = _positive_id(config.TESTRAIL_PROJECT_ID, "project")
    suite_id = _positive_id(suite_id, "suite")
    cases = _get_all(f"get_cases/{project_id}&suite_id={suite_id}", "cases")
    return [{
        "id": _positive_id(item.get("id"), "case"),
        "title": _plain_text(item.get("title", "")),
        "section_id": _positive_id(item.get("section_id"), "section"),
    } for item in cases]


def validate_case_target(suite_id: int, section_id: int) -> dict:
    suite_id = _positive_id(suite_id, "suite")
    section_id = _positive_id(section_id, "section")
    suite = next((item for item in list_suites() if item["id"] == suite_id), None)
    if suite is None:
        raise TestRailError(f"TestRail suite {suite_id} is not in the configured project.")
    section = next((item for item in list_sections(suite_id) if item["id"] == section_id), None)
    if section is None:
        raise TestRailError(f"TestRail section {section_id} does not belong to suite {suite_id}.")
    return {"suite": suite, "section": section}


def create_case(section_id: int, payload: dict) -> dict:
    section_id = _positive_id(section_id, "section")
    url = f"{config.TESTRAIL_URL}/index.php?/api/v2/add_case/{section_id}"
    data = _request("POST", url, json=payload)
    case_id = data.get("id")
    try:
        numeric_id = _positive_id(case_id, "case")
    except TestRailError as e:
        raise TestRailError(
            "TestRail accepted the create request but returned no valid case ID; verify TestRail before retrying."
        ) from e
    return {"id": f"C{numeric_id}", "title": _plain_text(data.get("title", payload.get("title", "")))}


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
    if not isinstance(raw, dict):
        raise TestRailError("TestRail returned an invalid case.")

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
            section = _get(f"get_section/{section_id}")
            if not isinstance(section, dict):
                raise TestRailError("TestRail returned an invalid section.")
            section_name = _plain_text(section.get("name", ""))
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
