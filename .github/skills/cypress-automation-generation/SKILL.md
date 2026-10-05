---
name: cypress-automation-generation
description: Generate, review, and optionally save Cypress specs from selected QA Intelligence Hub test cases using the real repository's existing specs, page objects, commands, feature guidance, and test-data helpers.
---

# Cypress Automation Generation

## Workflow

1. Accept either a Jira issue key with saved generated test cases or a TestRail case ID such as `C12345`.
2. For Jira input, call `qa-hub/get_automation_context(issue_key)` to list saved cases, ask the user to select case IDs, then call again with those IDs. The selected-case call returns a small manifest and `context_id`, not the full source payload.
3. For TestRail input, call `qa-hub/get_testrail_automation_context(case_id)`. This returns a small manifest, context ID, feature, destination, and section sizes—not the full source payload. If feature resolution is ambiguous, stop and ask for corrected case metadata or an explicit known feature key; do not guess.
4. Fetch needed sections for either source using `qa-hub/get_automation_context_page(context_id, section, offset, limit)`. Request the selected `test_case` items, `general_guidelines`, `feature_context`, and only relevant product/role sections. Fetch `existing_specs`, `page_objects`, `custom_commands`, `data_helpers`, and `automation_scope` in pages of at most two items. Continue from `next_offset` until complete for any section you need. The older `get_testrail_automation_context_page` name remains a TestRail-compatible alias. Never retry an unpaged context request or try to open a tool-output temp file.
5. If a selected exact-path file is present but its supplied chunks do not establish a needed method or usage pattern, call `qa-hub/get_automation_file_chunks(context_id, file_path)` for that file only. Use only paths already present in the automation context, request more only when needed, and stop after the tool's bounded follow-up pages. Do not fetch more chunks from every related file. If a required file has no indexed chunks, request re-ingestion instead; this tool cannot repair a missing or stale index.
6. Do not invent imports, page-object methods, custom commands, selectors, fixtures, API helpers, or routes.

## Locator discovery with Playwright MCP

- Use this only when exact-path FAISS chunks do not contain a required locator/method, or the locator is explicitly uncertain. Do not browse the app just to reconfirm known Page Object methods.
- Use the exact test URL supplied by the user; never replace it with a `contentRegistry.js` URL or infer a different host. The user-supplied host must be in Playwright MCP's allowed-origin list. If it is not, stop and explain how to add that exact host to `PLAYWRIGHT_ALLOWED_ORIGINS`; do not navigate elsewhere.
- Tell the user which exact URL and specific test-case step will be inspected. If authentication is needed, navigate to that URL in the headed Playwright MCP browser, pause, and ask the user to sign in directly in that browser. Never read credentials from Cypress config, request them in chat, or type them through Playwright. Wait for the user's confirmation before continuing; if the browser is not visible or interactive, stop and explain the limitation.
- Do not navigate to production. A user-provided URL is used verbatim; the environment label in `contentRegistry.js` must not override it.
- Use Playwright MCP to inspect the specific screen/step and verify a candidate locator against the live DOM (unique match, visible/enabled as needed). Prefer accessible role/name, label, or stable `data-*` attributes. Record the observed evidence and relevant element state; do not send a whole-page DOM dump into the generation prompt.
- Translate the verified browser observation into the repository's Cypress convention and a Page Object method. Playwright locator syntax is not Cypress syntax; never paste `getByRole()`/Playwright calls into a Cypress spec.
- Do not submit forms, archive/delete records, create persistent test data, or trigger other state-changing actions during discovery unless the user explicitly approves that action and the environment is approved for it. Prefer read-only navigation and inspection.
- Never put API keys, credentials, session tokens, or secrets in URLs, chat prompts, screenshots, locator notes, tool arguments, or generated code. Do not ask the user to reveal a secret to Copilot or extract credentials from Cypress config. Login is user-performed in the headed Playwright MCP browser only.
- Present the locator evidence and proposed Page Object diff for review. Existing Page Objects are not modified automatically.

## Repository code scope

- Use the `automation_scope` returned by the context tool. It is built from the case-focused feature Page Objects and the static import graph of specs that import those objects; it does not use unrelated feature specs as examples.
- If several feature Page Objects match the selected workflow, inspect all of them and the matching specs that import them.
- Every feature context includes the shared `commonObjectsAndUtils.cy.js` Page Object and relevant `cypress/support/commands.js` chunks. Reuse these before proposing additional abstractions.
- Cypress code excerpts supplied to Copilot must come only from FAISS chunks whose indexed repository paths exactly match the selected specs, Page Objects, shared utility, commands file, or imported helpers. The local import scanner may inspect source to build the dependency graph, but raw filesystem source is not included in the model context.
- If any required source path has no indexed chunks, stop and ask for automation-index re-ingestion. Do not fall back to reading the source file into the prompt or to unrelated semantic matches.
- If the tool cannot resolve a feature Page Object or importing spec, stop and report the gap; do not fall back to arbitrary semantically similar feature code.

## Generation and Review

1. Read the universal automation guidelines and feature-specific context. Mirror the closest existing spec style and lifecycle from retrieved repository chunks.
2. Generate one runnable `.cy.js` spec in the returned `target_spec_directory`. Include each selected manual `tc_id` or TestRail case ID in a test title or comment.
3. Reuse existing Page Object methods, locator wrappers, Cypress commands, and data helpers. Never duplicate locators/helpers or use naked `cy.get(...)` in spec bodies.
4. Use setup/cleanup helpers only when retrieved context shows they exist. Keep cleanup local and follow the feature's documented dependency order. Use `Cypress.env()` for credentials; never hard-code credentials or production URLs.
5. Use intercepts and alias waits when relevant to the scenario. Do not add irrelevant hooks, roles, waits, or assertions. Avoid arbitrary static waits.
6. Return a review bundle: generated spec content/path, source case IDs, reused indexed paths/chunks, grounding evidence, and any proposed Page Object changes as diffs. Do not apply Page Object/custom-command changes automatically.
7. Show the full target path and code preview, then ask where to save. For a local preview, call `qa-hub/save_cypress_preview` only after approval; for a repository spec, use the source-appropriate creation tool only after approval. All save tools refuse collisions and never edit existing files.
8. Report the saved path and state that the spec has not been executed. The user runs Cypress from the CLI; never execute it or imply a pass without a separate explicit request.

## Quality review

- Every selected manual case maps to at least one `it()` block or an explicitly explained grouped scenario.
- Every test asserts an observable expected result.
- Imports resolve to files shown in repository context.
- Selectors and helper APIs match retrieved repository code, not guesses.
- Test data uses the repository's naming conventions and cleanup lifecycle.
- Preserve neighboring naming, imports, singleton/class instantiation, and hook style.
- If the feature context or codebase lacks a needed method/selector/setup helper, report the gap and propose a minimal patch; do not fabricate it.
