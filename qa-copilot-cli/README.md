# QA Copilot CLI

This directory contains the QA Copilot MCP server and its tests. It is one of the two tools in the QA Intelligence Hub repository; it shares `rag/.env`, the FAISS index, and documentation with the Streamlit app.

Use the [root README](../README.md) for the complete first-time setup. From the repository root, the Copilot-specific steps are:

```powershell
.\qa-copilot-cli\setup.ps1
copilot --agent=qa-analyst
```

The Copilot registration step requires GitHub Copilot CLI and Node.js 22+. Once in the agent, run `Check setup` first.

The `qa-analyst` agent permits read/search tools for repository workflow guidance, in addition to `qa-hub` tools. Large `get_story_context` responses automatically return a compact manifest instead of overflowing the CLI output limit. Call `get_story_context_page` at offset 0 and follow `next_offset` until null; concatenate its JSON fragments to reconstruct the complete initial context before analysis or generation. Each page contains at most 3,000 characters of ASCII-serialized JSON, preserving exact source evidence without requiring temporary-file access. The initial snapshot stays stable even when supporting-source follow-ups append results. `get_more_story_context` remains the separate tool for optional additional supporting-source retrieval. Restart Copilot and its QA Hub MCP server after updating so the page tool and revised agent instructions are loaded.

Exact Jira-to-TestRail matching uses the TestRail `refs` field captured by ingestion. Rebuild the FAISS index after changing TestRail ingestion or when references need refreshing.

Feature aliases are shared configuration in `rag/config/feature-aliases.json`. Automation guidance lives under `rag/docs/automation/feature-context/<canonical-feature-key>/<canonical-feature-key>-feature-context.md`, mirroring the per-feature product-knowledge folders. For example, Notes uses `feature-context/notes/notes-feature-context.md`. The CLI discovers the document by its feature folder; Markdown ingestion assigns that folder's feature key to all documents within it. Keep filenames unique across features because ingestion document IDs use filenames. Existing alias and feature-context files are tracked; new files in ignored locations require explicit staging.

After migrating from the previous flat layout, perform a full index rebuild to replace indexed source paths, then restart QA Hub and Streamlit to clear cached configuration/index data. An incremental docs update can skip existing document IDs and is not sufficient for this migration. An alias-only edit requires restarting the running tools but not rebuilding the index.

Shared role guidance lives in `rag/docs/shared/role-permissions.md`. Markdown ingestion identifies it by filename and assigns the `role_permissions` domain; CLI and Streamlit retrieval identify indexed sources by `role-permissions`, not the previous parent folder. A full rebuild after moving the document updates indexed source paths while preserving its filename-based document IDs.

Validated generated cases can be exported individually through `qa-hub`: select a TestRail suite and section, inspect the preview and duplicate-title warnings, then explicitly approve creation and decide whether each duplicate should be created or skipped. Export uses the saved CLI JSON artifact, verifies it has not changed since preview, and never retries a create request automatically. Configure TestRail credentials and `TESTRAIL_PROJECT_ID` in `rag/.env`; never provide credentials in chat.

Destination selection happens in two steps: Copilot first calls `get_testrail_suites(issue_key=...)`, shows story/feature-name recommendations with names and IDs, and waits for your selection. Then it calls `get_testrail_sections(suite_id=..., issue_key=...)`, shows recommendations within that suite, and waits again. Reply by displayed list number, name, or explicit ID; ambiguous replies require clarification. Ask for "show all" at either step to list all existing destinations (`show_all=True`). Recommendations use whole-word overlap with the story summary and configured feature aliases, not semantic retrieval. No matches do not authorize a guessed destination: use the full list. Omitting `issue_key` retains unfiltered listing. No suites/sections are created, and destination selection does not replace the export preview and approval.

Export resolves TestRail priority IDs from their configured names: `Critical` maps to `1 - Base level test`, `High` and `Medium` to `3 - Functional`, and `Low` to `4 - Edge case`. It never selects `5 - Don't Test`. Missing/ambiguous required priorities block export, and configuration changes after preview require a fresh preview. References contain only the concerned Jira story key; generated `tc_id` values remain in the local artifact and export results, not the References field. Every exported case sends the TestRail label `AI Generated Test` using the case API's label-name support. The approval preview shows the resolved priority, story reference, and label. These rules apply to new exports; already-created TestRail cases are not modified.

Run the CLI regression tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qa-copilot-cli/tests -p test_core.py
```