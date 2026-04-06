"""
Jira ingestion for Kapost/Pilyr.
Fetches stories, bugs, epics from your Jira project and returns them
as structured dicts ready for the FAISS vectorstore.

Env vars required:
  JIRA_URL        – e.g. https://yourcompany.atlassian.net
  JIRA_USER       – your Atlassian account email
  JIRA_TOKEN      – Atlassian API token
  JIRA_PROJECT    – Jira project key (e.g. KAP)
  JIRA_JQL_FILTER – optional extra JQL clause (e.g. "sprint in openSprints()")
"""
import os
import requests
from typing import List, Dict


def _adf_to_markdown(node) -> str:
    """
    Convert Atlassian Document Format (ADF) to markdown-structured text,
    preserving headings, lists, and paragraph breaks so that downstream
    text parsers (e.g. extract_acceptance_criteria) can locate sections.
    """
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(_adf_to_markdown(n) for n in node)
    if not isinstance(node, dict):
        return str(node)
    ntype   = node.get("type", "")
    content = node.get("content") or []
    if ntype == "text":
        return node.get("text", "")
    if ntype == "doc":
        parts = [_adf_to_markdown(c) for c in content]
        return "\n".join(p for p in parts if p.strip())
    if ntype == "paragraph":
        return "".join(_adf_to_markdown(c) for c in content)
    if ntype == "heading":
        level = node.get("attrs", {}).get("level", 2)
        inner = "".join(_adf_to_markdown(c) for c in content)
        return "#" * level + " " + inner
    if ntype == "bulletList":
        return "\n".join(_adf_to_markdown(c) for c in content)
    if ntype == "orderedList":
        lines = []
        for i, c in enumerate(content, 1):
            text = _adf_to_markdown(c).lstrip("- ").strip()
            lines.append(f"{i}. {text}")
        return "\n".join(lines)
    if ntype == "listItem":
        inner = "\n".join(_adf_to_markdown(c) for c in content).strip()
        return "- " + inner
    if ntype == "hardBreak":
        return "\n"
    if ntype == "rule":
        return "---"
    if ntype == "codeBlock":
        inner = "".join(_adf_to_markdown(c) for c in content)
        return f"```\n{inner}\n```"
    if ntype == "blockquote":
        inner = "\n".join(_adf_to_markdown(c) for c in content)
        return "> " + inner
    if content:
        return "".join(_adf_to_markdown(c) for c in content)
    return node.get("text", "")


_AC_FIELD_ID: str = ""   # module-level cache
_STR_FIELD_ID: str = ""  # Steps to Reproduce custom field


def _get_ac_field_id(jira_url: str, auth) -> str:
    """Return the custom field ID for 'Acceptance Criteria', or '' if not found."""
    global _AC_FIELD_ID, _STR_FIELD_ID
    if _AC_FIELD_ID:
        return _AC_FIELD_ID
    try:
        r = requests.get(
            f"{jira_url}/rest/api/3/field",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        for field in r.json():
            name_lower = field.get("name", "").lower().strip()
            # Use exact match first to avoid matching 'Acceptance Testing' etc.
            if name_lower == "acceptance criteria" and not _AC_FIELD_ID:
                _AC_FIELD_ID = field["id"]
            elif "acceptance criteria" in name_lower and not _AC_FIELD_ID:
                _AC_FIELD_ID = field["id"]
            if name_lower == "steps to reproduce" and not _STR_FIELD_ID:
                _STR_FIELD_ID = field["id"]
            elif ("steps to reproduce" in name_lower or "steps_to_reproduce" in name_lower) and not _STR_FIELD_ID:
                _STR_FIELD_ID = field["id"]
    except Exception:
        pass
    return _AC_FIELD_ID


def fetch_jira_issues() -> List[Dict]:
    """
    Fetch all issues from the configured Jira project and return as a list
    of dicts suitable for ingestion into the FAISS vectorstore.
    """
    jira_url   = os.getenv("JIRA_URL")
    jira_user  = os.getenv("JIRA_USER")
    jira_token = os.getenv("JIRA_TOKEN")
    project    = os.getenv("JIRA_PROJECT")
    extra_jql  = os.getenv("JIRA_JQL_FILTER", "").strip()

    if not all([jira_url, jira_user, jira_token, project]):
        raise ValueError("JIRA_URL, JIRA_USER, JIRA_TOKEN, and JIRA_PROJECT must be set in .env")

    jql = f"project={project}"
    if extra_jql:
        jql += f" AND {extra_jql}"
    jql += " ORDER BY updated DESC"

    # POST /rest/api/3/search/jql is the only non-deprecated Jira Cloud search
    # endpoint. GET /rest/api/3/search and POST /rest/api/3/search are both 410.
    api_url  = f"{jira_url}/rest/api/3/search/jql"
    auth     = (jira_user, jira_token)
    headers  = {"Accept": "application/json", "Content-Type": "application/json"}

    # Look up the AC and Steps to Reproduce custom field IDs once before paginating
    ac_field_id  = _get_ac_field_id(jira_url, auth)  # also populates _STR_FIELD_ID
    str_field_id = _STR_FIELD_ID
    base_fields  = ["summary", "description", "issuetype", "labels",
                    "components", "priority", "status", "comment"]
    if ac_field_id:
        base_fields.append(ac_field_id)
    if str_field_id and str_field_id not in base_fields:
        base_fields.append(str_field_id)

    docs: List[Dict] = []
    next_page_token  = None
    fetched          = 0

    while True:
        body: dict = {
            "jql":        jql,
            "maxResults": 100,
            "fields":     base_fields,
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token

        response = requests.post(api_url, auth=auth, headers=headers, json=body)
        response.raise_for_status()
        result  = response.json()
        issues  = result.get("issues", [])

        for issue in issues:
            fields = issue.get("fields", {})
            key    = issue.get("key", "unknown")

            description = _adf_to_markdown(fields.get("description", "") or {})

            # Acceptance Criteria — dedicated custom field or fall back to description section
            ac_text = ""
            if ac_field_id and fields.get(ac_field_id):
                ac_raw = fields[ac_field_id]
                if isinstance(ac_raw, dict):
                    ac_text = _adf_to_markdown(ac_raw)
                elif isinstance(ac_raw, str):
                    ac_text = ac_raw

            # Steps to Reproduce — dedicated custom field
            str_text = ""
            if str_field_id and fields.get(str_field_id):
                str_raw = fields[str_field_id]
                if isinstance(str_raw, dict):
                    str_text = _adf_to_markdown(str_raw)
                elif isinstance(str_raw, str):
                    str_text = str_raw

            comments_text = " ".join(
                _adf_to_markdown(c.get("body", "") or {})
                for c in (fields.get("comment", {}) or {}).get("comments", [])
            )

            labels     = ", ".join(fields.get("labels", []))
            components = ", ".join(c.get("name", "") for c in (fields.get("components") or []))
            priority   = (fields.get("priority") or {}).get("name", "")
            status     = (fields.get("status") or {}).get("name", "")
            issue_type = (fields.get("issuetype") or {}).get("name", "")

            content_parts = [
                f"Jira Issue: {key}",
                f"Type: {issue_type} | Priority: {priority} | Status: {status}",
                f"Labels: {labels} | Components: {components}",
                f"Summary: {fields.get('summary', '')}",
            ]
            if description.strip():
                content_parts.append(f"\n## Description\n{description}")
            if ac_text.strip():
                content_parts.append(f"\n## Acceptance Criteria\n{ac_text}")
            if str_text.strip():
                content_parts.append(f"\n## Steps to Reproduce\n{str_text}")
            if comments_text.strip():
                content_parts.append(f"\n## Comments\n{comments_text}")
            content = "\n".join(content_parts).strip()

            docs.append({
                "id":       key,
                "content":  content,
                "source":   "jira",
                "type":     issue_type,
                "priority": priority,
                "status":   status,
                "labels":   labels,
            })

        # Cursor-based pagination: stop when Jira stops returning nextPageToken.
        # Never stop on isLast alone — it may be absent on some tenants.
        fetched += len(issues)
        next_page_token = result.get("nextPageToken")
        print(f"      … fetched {fetched} issues so far", end="\r")
        if not issues or not next_page_token:
            break

    return docs
