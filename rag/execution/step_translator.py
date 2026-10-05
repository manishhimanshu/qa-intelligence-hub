"""Translate one generated manual test case into a validated browser plan."""

from __future__ import annotations

import json
from typing import Any, Callable

from .playwright_runner import validate_execution_plan


PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["test_case_id", "title", "precondition_actions", "test_steps"],
    "properties": {
        "test_case_id": {"type": "string"},
        "title": {"type": "string"},
        "precondition_actions": {"type": "array", "items": {"type": "object"}},
        "test_steps": {"type": "array", "items": {"type": "object"}},
    },
}


def translate_steps_to_playwright_plan(
    manual_test_case: dict[str, Any],
    feature_key: str,
    *,
    client: Any,
    model: str,
    retrieve_context: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Use one focused LLM call to produce a deterministic execution plan.

    The feature key is required and is never inferred here. If execution-map
    context is unavailable, the function returns a blocked result rather than
    asking the model to invent selectors or setup data.
    """
    normalized_feature = (feature_key or "").strip().lower()
    if not normalized_feature:
        return _blocked("Cannot translate the test case without a resolved feature key.")

    context_docs = []
    if retrieve_context:
        context_docs = retrieve_context(
            _case_query(manual_test_case),
            top_k=8,
            feature_key_eq=normalized_feature,
            doc_domain_eq="ui_execution_map",
            path_contains="automation/execution-maps",
        )
    if not context_docs:
        return _blocked(
            f"No UI execution map was found for feature '{normalized_feature}'."
        )

    execution_context = "\n\n".join(
        f"[{doc.get('relative_source_path') or doc.get('source', 'execution map')}]\n"
        f"{doc.get('content', '')}"
        for doc in context_docs
    )
    prompt = _build_prompt(manual_test_case, normalized_feature, execution_context)

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {
            "name": "playwright_execution_plan",
            "strict": True,
            "schema": PLAN_SCHEMA,
        }},
        messages=[
            {
                "role": "system",
                "content": (
                    "You translate manual QA cases into deterministic Playwright plans. "
                    "Use only selectors, routes, setup operations, and assertions present "
                    "in the supplied execution map. Never invent missing values."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content or "{}"
    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        return _blocked("The execution-plan response was not valid JSON.")

    errors = validate_execution_plan(plan)
    if errors:
        return {
            "status": "blocked",
            "error": " ".join(errors),
            "plan": plan,
            "feature_key": normalized_feature,
        }

    plan["feature_key"] = normalized_feature
    plan["status"] = "ready"
    return plan


def _case_query(test_case: dict[str, Any]) -> str:
    return " ".join(
        str(test_case.get(field, ""))
        for field in ("title", "preconditions", "steps", "expected_result")
    ).strip()


def _build_prompt(
    test_case: dict[str, Any],
    feature_key: str,
    execution_context: str,
) -> str:
    return f"""Feature key: {feature_key}

Manual test case:
{json.dumps(test_case, indent=2, ensure_ascii=True)}

Feature-scoped UI execution map:
{execution_context}

Return a Playwright plan using only these actions:
- goto: requires url
- click, fill, select, hover: require a selector from the execution map
- wait: requires duration_ms
- assert_visible, assert_not_visible: require a selector
- assert_text: requires a selector and expected text

Rules:
1. Preserve the intent and order of the manual test case.
2. Use API setup only when the execution map documents the endpoint and payload.
3. Use stable selectors from the execution map; never invent CSS classes or text selectors.
4. Every test step needs a clear description.
5. If a required selector, route, setup operation, or expected value is missing, do not guess; return the plan with the missing information represented clearly so the caller can block the run.
6. Do not add generic network, browser, or unsupported scenarios not present in the manual case.
"""


def _blocked(message: str) -> dict[str, Any]:
    return {"status": "blocked", "error": message, "plan": None}
