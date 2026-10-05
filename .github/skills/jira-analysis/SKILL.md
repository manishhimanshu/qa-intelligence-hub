---
name: jira-analysis
description: Analyze Jira stories for requirement gaps, ambiguity, testability, role/access questions, data validation questions, and grounded questions for the product owner.
---

# Jira Requirement Analysis

## Procedure

1. Call `qa-hub/get_story_context` for the issue. Stop and report the error if it fails. Surface all context warnings.
2. If the tool reports an output-too-large or temp-file condition, do not attempt to read the temp file, browser-navigate to it, or use Playwright to access it. Instead, stop and ask for the full AC/STR or a narrower payload. Report the limitation explicitly, and do not claim the story was fully analyzed from partial output.
3. State the requirement source: AC, Steps to Reproduce, description (only when AC/STR are absent), or summary only.
4. Summarize only behavior explicitly stated in that source. Use comments as BA/PO clarification. Treat description/dev notes as context when AC or STR exist.
5. Use feature-scoped product documentation and role permissions to understand terms and identify relevant questions. Do not turn product behavior absent from the Jira story into a story requirement.
6. If a specific supporting source in the returned context is insufficient, call `qa-hub/get_more_story_context(context_id, source)` for that source only. Request more only when it can clarify story terminology or testing context; do not fetch every source by default. TestRail cases may inform existing-coverage review only, never requirement evidence. The tool allows at most two follow-up pages per source.
7. Identify only relevant gaps: functional behavior, roles/access, input validation, state/edge behavior, integrations, and non-functional expectations. Leave unrelated categories empty.
8. Write concrete, answerable PO questions tied to identified gaps. Mark assumptions as questions; do not present them as facts.
9. Call `qa-hub/save_gap_analysis` and report its Markdown path and any grounding review flags.

## Guardrails

- Do not use Playwright MCP during Jira story analysis. Playwright is not a requirement-reading tool and must not be triggered by a story-analysis request.
- Do not bypass output limits by trying to read the temp file that the tool saved. This is not a supported workflow and should be treated as a hard limitation, not a workaround.
- Do not invent requirements or gaps. Do not add generic network/API failure, timeout, offline, server-error, concurrency, performance, load/stress, or browser-compatibility items unless the authoritative Jira source explicitly mentions them. Preserve flagged items for review; never claim the saver silently removed them.

## Grounding

Do not invent requirements or gaps. Do not add generic network/API failure, timeout, offline, server-error, concurrency, performance, load/stress, or browser-compatibility items unless the authoritative Jira source explicitly mentions them. Preserve flagged items for review; never claim the saver silently removed them.
