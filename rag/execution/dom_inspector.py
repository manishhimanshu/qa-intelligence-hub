"""Extract candidate locators and flag unstable selectors from a live page.

Feeds the Selector Dictionary section of execution maps under
rag/docs/automation/execution-maps/. Prefers stable attributes
(data-cy, data-testid, id) over CSS classes or generated markup.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STABLE_ATTRS = ["data-cy", "data-testid", "data-test", "id"]
INTERACTIVE_SELECTOR = (
    "button, a[href], input, select, textarea, [role=button], [role=link], "
    "[role=checkbox], [role=tab], [role=menuitem], [onclick]"
)

_EXTRACT_JS = """
({ stableAttrs, interactiveSelector }) => {
    function accessibleName(el) {
        return (
            el.getAttribute('aria-label') ||
            el.innerText ||
            el.getAttribute('placeholder') ||
            el.getAttribute('title') ||
            ''
        ).trim().slice(0, 120);
    }

    function stableSelector(el) {
        for (const attr of stableAttrs) {
            const val = el.getAttribute(attr);
            if (val) return { attr, value: val, selector: `[${attr}="${val}"]` };
        }
        return null;
    }

    const elements = Array.from(document.querySelectorAll(interactiveSelector));
    const results = [];
    for (const el of elements) {
        const rect = el.getBoundingClientRect();
        const visible = rect.width > 0 && rect.height > 0 && el.offsetParent !== null;
        const stable = stableSelector(el);
        results.push({
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || (el.tagName.toLowerCase() === 'button' ? 'button' : ''),
            accessible_name: accessibleName(el),
            visible,
            stable_selector: stable ? stable.selector : null,
            stable_attr: stable ? stable.attr : null,
        });
    }
    return results;
}
"""


def extract_locators(
    url: str,
    *,
    headless: bool = True,
    wait_until: str = "domcontentloaded",
    login_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Open a page, optionally run login steps, and list interactive elements.

    login_steps entries look like {"action": "click"|"fill", "selector": "...", "value": "..."}
    and are run before extraction so authenticated-only UI can be inspected.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=30000)
            for step in login_steps or []:
                action = step.get("action")
                selector = step.get("selector", "")
                if action == "click":
                    page.locator(selector).click(timeout=5000)
                elif action == "fill":
                    page.locator(selector).fill(str(step.get("value", "")), timeout=5000)
                elif action == "wait":
                    page.wait_for_timeout(int(step.get("duration_ms", 500)))

            elements = page.evaluate(
                _EXTRACT_JS,
                {"stableAttrs": STABLE_ATTRS, "interactiveSelector": INTERACTIVE_SELECTOR},
            )
            title = page.title()
            final_url = page.url
        finally:
            browser.close()

    stable = [e for e in elements if e["stable_selector"] and e["visible"]]
    unstable = [e for e in elements if not e["stable_selector"] and e["visible"]]

    return {
        "url": final_url,
        "title": title,
        "stable_elements": stable,
        "unstable_elements": unstable,
        "summary": {
            "total_visible_interactive": len(stable) + len(unstable),
            "with_stable_selector": len(stable),
            "missing_stable_selector": len(unstable),
        },
    }


def to_selector_table(report: dict[str, Any]) -> str:
    """Render stable elements as a Markdown table matching the execution-map template."""
    lines = ["| Logical target | Selector | Notes |", "|---|---|---|"]
    for el in report["stable_elements"]:
        label = el["accessible_name"] or f"{el['tag']} ({el['stable_attr']})"
        label = label.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {label} | `{el['stable_selector']}` | tag={el['tag']}, role={el['role'] or 'n/a'} |")
    return "\n".join(lines)


def to_missing_selectors_report(report: dict[str, Any]) -> str:
    """List interactive elements with no stable selector — needs dev instrumentation."""
    lines = [
        f"{report['summary']['missing_stable_selector']} interactive element(s) "
        f"on {report['url']} have no data-cy/data-testid/id attribute:",
        "",
    ]
    for el in report["unstable_elements"]:
        label = el["accessible_name"] or "(no accessible name)"
        lines.append(f"- <{el['tag']}> role={el['role'] or 'n/a'} — \"{label}\"")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--output", help="Write JSON report to this path")
    args = parser.parse_args()

    report = extract_locators(args.url, headless=args.headless)
    print(to_selector_table(report))
    print()
    print(to_missing_selectors_report(report))

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
