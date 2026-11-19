---
name: test-case-generation
description: Generate structured, manual test cases from Jira acceptance criteria or steps to reproduce, with evidence citations, coverage references, realistic scenarios, role scoping, and review-ready output.
---

# Manual Test Case Generation

## Required context and evidence

1. Call `qa-hub/get_story_context` first and surface its warnings. If it returns `paged: true`, call `qa-hub/get_story_context_page(context_id, offset=0)` and follow `next_offset` until null. Concatenate all `content` fragments in order to reconstruct the complete JSON context, including exact `source_text`; read every page before generating. This is initial-context transport, not optional supporting-source retrieval.
2. Follow the source precedence: Acceptance Criteria; else Steps to Reproduce; else description; else summary only. When AC/STR exist, description/dev notes are background context, not requirements. Existing TestRail cases are for duplicate detection only.
3. Use `product_knowledge`, `automation_context`, `qa_guidance`, and `role_permissions` to interpret the feature and testing conventions. Product/repository context does not expand the Jira story's scope.
4. If a specific supporting source is insufficient, call `qa-hub/get_more_story_context(context_id, source)` for that source only. Request more only when it could materially improve interpretation, test design, or duplicate review; do not fetch all sources by default. TestRail follow-ups are for duplicate detection or examples of coverage for Jira-supported behavior, never for adding requirements. The tool allows at most two follow-up pages per source.
5. Do not invent behaviors or scenarios. If an outcome is unspecified, put it in `qa_gaps` or a PO question rather than writing an assumed test.

## Requirements brief

Create one clear statement per functional requirement, with lists for directly relevant edge cases, negative scenarios, validation rules, API interactions, design techniques, and QA gaps. Use IDs by list position: FR-01… (AC/description/summary source), SC-01… (STR source), EC-01…, NS-01…, VR-01… . Keep unrelated lists empty.

For every FR/SC, EC, NS, and VR item, add `source_evidence` containing one or more citations:

```json
{"source":"acceptance_criteria","quote":"an exact excerpt from the Jira source"}
```

Allowed source values: `acceptance_criteria`, `steps_to_reproduce`, `description`, `comments`, `summary`. Use the authoritative source selected above; comments may clarify it. Quotes must be copied verbatim from the returned `source_text`, not paraphrased. Every brief item must have a citation; the MCP saver verifies citations against the Jira text and blocks invalid or missing citations.

## Test cases

- Create scenario-level cases with clear preconditions, numbered user-action steps, and observable expected results.
- Apply manual design techniques only when the requirement supports them; see the `manual-test-design` skill.
- Cover each FR/SC, EC, and NS. Apply validation rules where relevant.
- Use roles only when Jira requirements mention roles, permissions affect visibility/action, or AC differ by role. Consult `role_permissions`; don't add generic role variants.
- Use `story.feature_prefix` and sequential three-digit IDs.
- Include every materially covered requirement ID in `coverage_refs`; use only IDs that exist in this brief.
- Use the supported priority/type/automation values from the output schema. Prefix concrete test data with `CY_Test |`; otherwise use `N/A`.
- Assign `Critical` only to the most critical/base-level tests, `High` or `Medium` to other functional tests, and `Low` to extreme edge cases. TestRail export maps these to `1 - Base level test`, `3 - Functional`, and `4 - Edge case` respectively; never request `5 - Don't Test`.
- Do not include unsupported network/API, timeout/offline, server-error, concurrency, performance/load/stress, or browser-compatibility scenarios.

## Save

Call `qa-hub/save_test_cases` with the requirements brief, cases, and a candid self-critique. If it returns schema, citation, or traceability errors, correct them and retry. Grounding flags and exact-title duplicate matches are review warnings: keep the cases, inspect them, and explain the disposition. Report both Markdown and JSON paths.

## Optional TestRail export

Destination selection must be interactive and sequential:
1. Call `qa-hub/get_testrail_suites(issue_key=...)`. Display recommended suites as numbered choices with exact names and IDs, offer "show all" (`show_all=True`), and wait for the user to select.
2. Accept a list number, name, or explicit ID. Resolve it to an existing project suite; clarify ambiguous numbers/names instead of guessing. If the choice is outside recommendations, use the full list to validate it. Do not automatically choose even if there is only one recommendation.
3. Only after suite selection, call `qa-hub/get_testrail_sections(suite_id=..., issue_key=...)`. Show matching sections as numbered choices with exact names and IDs, offer "show all" within that suite, and wait again. Accept the same input forms; validate the selection within that suite and clarify ambiguity.
4. If no recommendations match, offer the existing full list. Do not create suites/sections. Then proceed to the preview; selecting a destination is not write approval.

Only export when the user explicitly requests it. Let the user select individual `tc_id` values from the saved artifact and select a suite and section using `qa-hub/get_testrail_suites` and `qa-hub/get_testrail_sections`. Call `qa-hub/preview_test_cases_to_testrail` and show its full case/target preview and duplicate-title warnings. Wait for explicit approval; for every duplicate warning, ask whether that selected case should be created or skipped. Call `qa-hub/push_test_cases_to_testrail` only with that approval and each duplicate decision. If any create outcome is uncertain, check TestRail before suggesting another attempt; the server does not retry writes.

Show the preview's resolved TestRail priority, story-only reference, and `AI Generated Test` label. Generated `tc_id` values identify cases in the local artifact and export result; they are not Jira references. Every exported case must carry the label.
