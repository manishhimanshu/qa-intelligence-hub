from functools import lru_cache

import requests

from . import config
from .parsing import adf_to_markdown

_TIMEOUT = 20
_HEADERS = {"Accept": "application/json"}


class JiraError(RuntimeError):
    pass


def _require_config() -> None:
    if not (config.JIRA_URL and config.JIRA_USER and config.JIRA_TOKEN):
        raise JiraError("JIRA_URL, JIRA_USER and JIRA_TOKEN must be set in rag/.env.")


def _request(method: str, path: str, **kwargs) -> dict | list:
    _require_config()
    try:
        r = requests.request(
            method,
            f"{config.JIRA_URL}{path}",
            auth=(config.JIRA_USER, config.JIRA_TOKEN),
            headers=_HEADERS,
            timeout=_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as e:
        raise JiraError(f"Jira request failed: {type(e).__name__}") from e
    if r.status_code in (401, 403):
        raise JiraError(f"Jira authentication/permission error (HTTP {r.status_code}).")
    if r.status_code == 404:
        raise JiraError("Jira issue or resource not found (HTTP 404).")
    if not r.ok:
        raise JiraError(f"Jira returned HTTP {r.status_code}.")
    return r.json()


@lru_cache(maxsize=1)
def get_field_ids() -> tuple[str, str]:
    """Return (acceptance_criteria_id, steps_to_reproduce_id); exact name wins over partial match."""
    ac_exact = ac_partial = str_exact = str_partial = ""
    for field in _request("GET", "/rest/api/3/field"):
        name = field.get("name", "").lower().strip()
        fid = field.get("id", "")
        if name == "acceptance criteria" and not ac_exact:
            ac_exact = fid
        elif "acceptance criteria" in name and not ac_partial:
            ac_partial = fid
        if name == "steps to reproduce" and not str_exact:
            str_exact = fid
        elif ("steps to reproduce" in name or "steps_to_reproduce" in name) and not str_partial:
            str_partial = fid
    return ac_exact or ac_partial, str_exact or str_partial


def _custom_field_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        return adf_to_markdown(value)
    if isinstance(value, str):
        return value
    return ""


def fetch_issue(key: str) -> dict:
    ac_id, str_id = get_field_ids()
    fields = _request(
        "GET", f"/rest/api/3/issue/{key}", params={"fields": "*navigable"}
    ).get("fields", {})
    return {
        "key": key,
        "summary": fields.get("summary", ""),
        "issuetype": (fields.get("issuetype") or {}).get("name", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "labels": fields.get("labels") or [],
        "components": [c.get("name", "") for c in (fields.get("components") or [])],
        "description": adf_to_markdown(fields.get("description") or {}),
        "acceptance_criteria_raw": _custom_field_text(fields.get(ac_id)) if ac_id else "",
        "steps_to_reproduce_raw": _custom_field_text(fields.get(str_id)) if str_id else "",
    }


def fetch_comments(key: str, max_chars: int = 1500) -> str:
    """Newest-first comments, skipping trivial ones, capped to control prompt size."""
    data = _request(
        "GET",
        f"/rest/api/3/issue/{key}/comment",
        params={"maxResults": 50, "orderBy": "-created"},
    )
    parts: list[str] = []
    total = 0
    for c in data.get("comments", []):
        author = (c.get("author") or {}).get("displayName", "Unknown")
        body = adf_to_markdown(c.get("body") or {}).strip()
        if len(body) < 30:
            continue
        chunk = f"[{author}]: {body}"
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > 60:
                parts.append(chunk[:remaining] + "…")
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts)


def fetch_epic_children(epic_key: str, max_issues: int = 200) -> list[dict]:
    jql = f'(parent = "{epic_key}") OR ("Epic Link" = "{epic_key}") ORDER BY key ASC'
    children: list[dict] = []
    next_token = None
    while len(children) < max_issues:
        body = {
            "jql": jql,
            "fields": ["summary", "status", "issuetype"],
            "maxResults": min(100, max_issues - len(children)),
        }
        if next_token:
            body["nextPageToken"] = next_token
        data = _request("POST", "/rest/api/3/search/jql", json=body)
        for issue in data.get("issues", []):
            f = issue.get("fields", {})
            children.append({
                "key": issue.get("key", ""),
                "summary": f.get("summary", ""),
                "status": (f.get("status") or {}).get("name", ""),
                "issuetype": (f.get("issuetype") or {}).get("name", ""),
            })
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    return children
