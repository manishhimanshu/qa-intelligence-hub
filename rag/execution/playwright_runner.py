"""Deterministic Playwright execution for validated browser action plans."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable


SUPPORTED_ACTIONS = {
    "goto",
    "click",
    "fill",
    "select",
    "hover",
    "wait",
    "assert_visible",
    "assert_not_visible",
    "assert_text",
}


def validate_execution_plan(plan: dict[str, Any]) -> list[str]:
    """Return blocking validation errors instead of guessing missing actions."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["Execution plan must be an object."]

    steps = plan.get("test_steps")
    if not isinstance(steps, list) or not steps:
        errors.append("Execution plan must contain at least one test step.")
        return errors

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"Step {index} must be an object.")
            continue
        action = str(step.get("action", "")).strip()
        if action not in SUPPORTED_ACTIONS:
            errors.append(f"Step {index} uses unsupported action: {action or '<missing>'}.")
        if not str(step.get("description", "")).strip():
            errors.append(f"Step {index} is missing a human-readable description.")
        requires_selector = action in {
            "click",
            "fill",
            "select",
            "hover",
            "assert_visible",
            "assert_not_visible",
            "assert_text",
        }
        if requires_selector and not str(step.get("selector", "")).strip():
            errors.append(f"Step {index} requires a resolved selector.")
        if action == "goto" and not str(step.get("url", "")).strip():
            errors.append(f"Step {index} requires a URL.")
        if action == "fill" and "value" not in step:
            errors.append(f"Step {index} requires a fill value.")
        if action == "select" and "value" not in step:
            errors.append(f"Step {index} requires a select value.")
        if action == "assert_text" and not str(step.get("text", "")):
            errors.append(f"Step {index} requires expected text.")

    return errors


def run_execution_plan(
    plan: dict[str, Any],
    *,
    base_url: str = "",
    headless: bool = True,
    screenshot_dir: str | Path = "execution-artifacts",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run a validated plan and return serializable step results.

    Playwright is imported lazily so the rest of the application can still be
    imported when the optional browser dependency is not installed.
    """
    errors = validate_execution_plan(plan)
    if errors:
        return {
            "status": "blocked",
            "title": plan.get("title", "") if isinstance(plan, dict) else "",
            "test_case_id": plan.get("test_case_id", "") if isinstance(plan, dict) else "",
            "steps": [],
            "error": " ".join(errors),
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {
            "status": "blocked",
            "title": plan.get("title", ""),
            "test_case_id": plan.get("test_case_id", ""),
            "steps": [],
            "error": "Playwright is not installed. Install the browser execution dependency first.",
            "exception": str(exc),
        }

    artifact_path = Path(screenshot_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    step_results: list[dict[str, Any]] = []
    status = "passed"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            for index, step in enumerate(plan["test_steps"], start=1):
                started = time.perf_counter()
                result = _run_step(page, step, base_url=base_url)
                result["step_num"] = step.get("step_num", index)
                result["description"] = step["description"]
                result["duration_ms"] = round((time.perf_counter() - started) * 1000)
                step_results.append(result)
                if progress_callback:
                    progress_callback(result)
                if result["status"] == "failed":
                    status = "failed"
                    screenshot = artifact_path / f"step-{index}-failed.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    result["screenshot_path"] = str(screenshot)
                    break
        finally:
            browser.close()

    return {
        "status": status,
        "title": plan.get("title", ""),
        "test_case_id": plan.get("test_case_id", ""),
        "steps": step_results,
    }


def _run_step(page: Any, step: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    action = step["action"]
    try:
        if action == "goto":
            url = step["url"]
            if base_url and url.startswith("/"):
                url = base_url.rstrip("/") + url
            page.goto(url, wait_until="domcontentloaded", timeout=step.get("timeout_ms", 30000))
        elif action == "click":
            page.locator(step["selector"]).click(timeout=step.get("timeout_ms", 5000))
        elif action == "fill":
            page.locator(step["selector"]).fill(str(step["value"]), timeout=step.get("timeout_ms", 5000))
        elif action == "select":
            page.locator(step["selector"]).select_option(str(step["value"]), timeout=step.get("timeout_ms", 5000))
        elif action == "hover":
            page.locator(step["selector"]).hover(timeout=step.get("timeout_ms", 5000))
        elif action == "wait":
            page.wait_for_timeout(int(step.get("duration_ms", 500)))
        elif action == "assert_visible":
            page.locator(step["selector"]).wait_for(state="visible", timeout=step.get("timeout_ms", 5000))
        elif action == "assert_not_visible":
            page.locator(step["selector"]).wait_for(state="hidden", timeout=step.get("timeout_ms", 5000))
        elif action == "assert_text":
            page.locator(step["selector"]).get_by_text(str(step["text"]), exact=step.get("exact", False)).wait_for(
                state="visible", timeout=step.get("timeout_ms", 5000)
            )
        return {"status": "passed", "action": action, "message": "Completed successfully."}
    except Exception as exc:
        return {"status": "failed", "action": action, "message": str(exc)}
