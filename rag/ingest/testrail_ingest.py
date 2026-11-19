"""
TestRail ingestion for Kapost.
Fetches test cases across all suites in the project, enriched with
suite name, section name, steps, and expected results.

Env vars required:
  TESTRAIL_URL        – e.g. https://yourcompany.testrail.io
  TESTRAIL_USER       – your TestRail email
  TESTRAIL_TOKEN      – TestRail API key
  TESTRAIL_PROJECT_ID – numeric project ID (visible in the URL)
"""
import os
import re
import requests
from typing import List, Dict

_JIRA_KEY_RE = re.compile(r"(?<![A-Z0-9_])[A-Z][A-Z0-9_]+-\d+(?![A-Z0-9_-])", re.IGNORECASE)


class _TestRailClient:
    def __init__(self, base_url: str, user: str, token: str):
        self.base   = base_url.rstrip("/")
        self.auth   = (user, token)
        self.headers = {"Content-Type": "application/json"}

    def get(self, endpoint: str) -> dict | list:
        url      = f"{self.base}/index.php?/api/v2/{endpoint}"
        response = requests.get(url, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_all(self, endpoint: str, list_key: str) -> list:
        """Fetch all pages of a paginated endpoint using _links.next."""
        results = []
        url = f"{self.base}/index.php?/api/v2/{endpoint}"
        while url:
            response = requests.get(url, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            results.extend(data.get(list_key, []))
            next_link = (data.get("_links") or {}).get("next")
            if not next_link:
                url = None
            elif next_link.startswith("http"):
                # Already a full URL
                url = next_link
            elif next_link.startswith("/api/v2"):
                # TestRail returns /api/v2/... but the real path is /index.php?/api/v2/...
                url = f"{self.base}/index.php?{next_link}"
            else:
                url = f"{self.base}{next_link}"
        return results


def _strip_html(text: str) -> str:
    """Remove HTML tags from TestRail rich-text fields."""
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def ingest_testrail_cases() -> List[Dict]:
    """
    Fetch all test cases from the configured TestRail project.
    Builds rich text chunks with suite, section, steps and expected results.
    """
    base_url   = os.getenv("TESTRAIL_URL")
    user       = os.getenv("TESTRAIL_USER")
    token      = os.getenv("TESTRAIL_TOKEN")
    project_id = os.getenv("TESTRAIL_PROJECT_ID")

    if not all([base_url, user, token, project_id]):
        raise ValueError("TESTRAIL_URL, TESTRAIL_USER, TESTRAIL_TOKEN, TESTRAIL_PROJECT_ID must be set in .env")

    client = _TestRailClient(base_url, user, token)
    docs: List[Dict] = []

    # Fetch all suites in the project (paginated, wrapped in {"suites": [...]})
    suites = client.get_all(f"get_suites/{project_id}", "suites")

    for suite in suites:
        suite_id   = suite.get("id")
        suite_name = suite.get("name", "")

        # Fetch sections (paginated)
        section_map: Dict[int, str] = {}
        sec_endpoint = f"get_sections/{project_id}&suite_id={suite_id}" if suite_id else f"get_sections/{project_id}"
        sections = client.get_all(sec_endpoint, "sections")
        for s in sections:
            section_map[s["id"]] = s.get("name", "")

        # Fetch test cases (paginated, wrapped in {"cases": [...]})
        cases_endpoint = f"get_cases/{project_id}&suite_id={suite_id}" if suite_id else f"get_cases/{project_id}"
        cases = client.get_all(cases_endpoint, "cases")

        for case in cases:
            case_id    = case.get("id")
            section_id = case.get("section_id")
            section    = section_map.get(section_id, "")
            priority_map = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
            priority   = priority_map.get(case.get("priority_id"), "Medium")
            jira_refs = sorted({
                match.group(0).upper()
                for match in _JIRA_KEY_RE.finditer(str(case.get("refs") or ""))
            })

            steps          = _strip_html(case.get("custom_steps", "") or "")
            expected       = _strip_html(case.get("custom_expected", "") or "")
            steps_separated = case.get("custom_steps_separated", []) or []

            # If steps are structured, build readable text
            if steps_separated:
                step_lines = []
                for i, step in enumerate(steps_separated, 1):
                    if isinstance(step, dict):
                        step_lines.append(
                            f"  Step {i}: {_strip_html(step.get('content', ''))}\n"
                            f"  Expected: {_strip_html(step.get('expected', ''))}"
                        )
                steps = "\n".join(step_lines)

            preconds = _strip_html(case.get("custom_preconds", "") or "")
            # TestRail stores the string "None" for empty fields — treat as empty
            if preconds.strip().lower() == "none":
                preconds = ""
            if expected.strip().lower() == "none":
                expected = ""

            content = (
                f"TestRail Case: {case_id}\n"
                f"Suite: {suite_name} | Section: {section}\n"
                f"Priority: {priority}\n"
                f"Title: {case.get('title', '')}\n"
                + (f"Jira References: {', '.join(jira_refs)}\n" if jira_refs else "")
                + f"Preconditions: {preconds}\n"
                + f"Steps:\n{steps}\n"
                + f"Expected Result:\n{expected}"
            ).strip()

            docs.append({
                "id":      f"testrail_{case_id}",
                "content": content,
                "source":  "testrail",
                "suite":   suite_name,
                "section": section,
                "priority": priority,
                "jira_refs": jira_refs,
            })

    return docs
