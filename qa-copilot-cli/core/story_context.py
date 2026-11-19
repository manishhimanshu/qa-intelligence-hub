from . import jira_client, retrieval
from .feature_resolver import resolve_feature_key
from .parsing import (
    detect_feature_prefix,
    detect_ticket_type,
    extract_acceptance_criteria,
    extract_steps_to_reproduce,
    normalize_ticket,
    strip_base64,
)


def build_story_context(key: str, include_comments: bool = False) -> dict:
    """Gather the minimum context needed for a story analysis without exceeding output limits.

    Jira comments are excluded by default because they are not required for story analysis and
    frequently bloat the payload without adding authoritative requirements.
    """
    issue = jira_client.fetch_issue(key)
    warnings: list[str] = []

    ac_list = extract_acceptance_criteria(
        f"## Acceptance Criteria\n{issue['acceptance_criteria_raw']}"
    ) if issue["acceptance_criteria_raw"].strip() else []
    str_list = extract_steps_to_reproduce(
        f"## Steps to Reproduce\n{issue['steps_to_reproduce_raw']}"
    ) if issue["steps_to_reproduce_raw"].strip() else []

    comments = ""
    if include_comments:
        try:
            comments = jira_client.fetch_comments(key)
        except jira_client.JiraError as e:
            warnings.append(f"Comments unavailable: {e}")

    description = strip_base64(issue["description"])
    feature_prefix = detect_feature_prefix(issue["summary"])
    feature_key = resolve_feature_key(
        issue["summary"],
        feature_prefix,
        f"{description} {' '.join(ac_list)} {' '.join(str_list)} {comments}",
    )
    ticket = normalize_ticket(
        key, issue["summary"], description, ac_list, str_list, comments,
        detect_ticket_type(issue["issuetype"], issue["summary"]), feature_key,
    )

    product_knowledge, automation_context, qa_guidance = [], [], []
    role_context, existing = "", []
    evidence_text = f"{description} {' '.join(ac_list)} {' '.join(str_list)}".strip()
    try:
        product_knowledge = retrieval.get_product_knowledge(
            feature_key, issue["summary"], evidence_text, top_k=2
        )
        if not product_knowledge:
            product_knowledge = retrieval.get_product_knowledge(
                feature_key, issue["summary"], evidence_text, top_k=6
            )[:2]

        automation_context = retrieval.get_automation_feature_context(
            feature_key, issue["summary"], evidence_text, top_k=2
        )
        if not automation_context:
            automation_context = retrieval.get_automation_feature_context(
                feature_key, issue["summary"], evidence_text, top_k=6
            )[:2]

        qa_guidance = retrieval.get_qa_guidance(
            issue["summary"], evidence_text, top_k=3
        )
        if not qa_guidance:
            qa_guidance = retrieval.get_qa_guidance(
                issue["summary"], evidence_text, top_k=6
            )[:3]
    except retrieval.RetrievalError as e:
        warnings.append(f"Feature/repository documentation unavailable: {e}")
    try:
        role_context = retrieval.get_role_context(issue["summary"], feature_prefix)
    except retrieval.RetrievalError as e:
        warnings.append(f"Role-permission guidance unavailable: {e}")
    try:
        existing = retrieval.get_existing_testrail_cases(key, issue["summary"], feature_key, top_k=6)
    except retrieval.RetrievalError as e:
        warnings.append(f"Existing TestRail cases unavailable: {e}")

    if not feature_key:
        warnings.append(
            "No canonical feature key resolved; product knowledge is omitted. "
            "Add an alias to rag/config/feature-aliases.json if needed."
        )
    elif not product_knowledge:
        warnings.append(f"No product knowledge indexed for feature '{feature_key}'.")
    if feature_key and not automation_context:
        warnings.append(f"No feature-specific automation/repository context indexed for '{feature_key}'.")
    if ticket["primary_source"] in ("description", "none"):
        warnings.append(
            "No Acceptance Criteria or Steps to Reproduce; requirements are inferred from the description."
        )

    return {
        "story": {
            "key": key,
            "summary": issue["summary"],
            "issuetype": issue["issuetype"],
            "status": issue["status"],
            "priority": issue["priority"],
            "labels": issue["labels"],
            "components": issue["components"],
            "ticket_type": ticket["ticket_type"],
            "feature_key": feature_key,
            "feature_prefix": feature_prefix,
            "primary_source": ticket["primary_source"],
        },
        "requirements": ticket["requirements"],
        "steps_to_reproduce": ticket["steps_to_reproduce"],
        "background_dev_notes": ticket["description_notes"],
        "comments": ticket["comments"],
        "product_knowledge": product_knowledge,
        "automation_context": automation_context,
        "qa_guidance": qa_guidance,
        "role_permissions": role_context,
        "existing_testrail_cases": [
            {
                "id": c["id"],
                "title": c["title"],
                "content": c["content"][:1200],
                "jira_linked": c["jira_linked"],
            }
            for c in existing[:12]
        ],
        "source_text": {
            "acceptance_criteria": issue["acceptance_criteria_raw"],
            "steps_to_reproduce": issue["steps_to_reproduce_raw"],
            "description": description,
            "comments": comments,
            "summary": issue["summary"],
        },
        "warnings": warnings,
    }


def evidence_text(context: dict) -> str:
    """Authoritative Jira evidence for scenario flags, respecting AC/STR over background notes."""
    source = context.get("source_text", {})
    primary = context.get("story", {}).get("primary_source", "none")
    fields = {
        "ac": ("acceptance_criteria", "comments"),
        "str": ("steps_to_reproduce", "comments"),
        "description": ("description", "comments"),
        "none": ("summary", "comments"),
    }.get(primary, ("comments",))
    return "\n".join(source.get(field, "") for field in fields)
