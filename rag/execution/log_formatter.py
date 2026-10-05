"""Human-readable formatting for browser execution results."""

from __future__ import annotations

from typing import Any


def format_execution_log(result: dict[str, Any]) -> str:
    """Format a runner result as a concise QA-readable execution log."""
    lines = [
        f"Status: {str(result.get('status', 'unknown')).upper()}",
        f"Test case: {result.get('test_case_id') or result.get('title') or 'Unknown'}",
    ]

    for step in result.get("steps", []):
        status = str(step.get("status", "unknown")).upper()
        prefix = "PASS" if status == "PASSED" else "FAIL" if status == "FAILED" else status
        description = step.get("description") or step.get("action") or "Unnamed step"
        detail = step.get("message") or ""
        duration = step.get("duration_ms")
        suffix = f" ({duration} ms)" if duration is not None else ""
        lines.append(f"{prefix} Step {step.get('step_num', '?')}: {description}{suffix}")
        if detail:
            lines.append(f"  {detail}")
        if step.get("screenshot_path"):
            lines.append(f"  Screenshot: {step['screenshot_path']}")

    if result.get("error"):
        lines.append(f"Error: {result['error']}")

    return "\n".join(lines)
