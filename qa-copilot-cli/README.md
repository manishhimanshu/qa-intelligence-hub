# QA Copilot CLI

This utility runs Jira gap analysis and manual test case generation from **GitHub Copilot CLI**, using the same Jira, product knowledge, role permissions and TestRail context as the Streamlit app.

Copilot's model does the reasoning. A local MCP server (`qa-hub`) only fetches context and validates or saves output, so this path needs **no OpenAI key**.

The repo-local coordinator is `.github/agents/qa-analyst.agent.md`. Its reusable QA workflows are skills under `.github/skills/`: Jira analysis, manual test design, test-case generation, test-case review, duplicate detection, and Cypress automation generation, with feature-specific Cypress guidance for Notes and archived content types. Run Copilot from the repository root so it can discover these skills.

## Setup

Prerequisites:

- The repository `.venv`, `rag/.env`, and built FAISS index
- GitHub Copilot CLI and Node.js 22+
- The Playwright MCP browser installed by the setup command
Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\qa-copilot-cli\setup.ps1
```

This installs the dependencies, validates the repo-local agent and skills, copies the coordinator to `~/.copilot/agents/`, and registers `qa-hub` plus the isolated Playwright MCP server for both Copilot CLI (`~/.copilot/mcp-config.json`) and VS Code Copilot Chat (`%APPDATA%/Code/User/mcp.json`). Existing servers and inputs in those files are preserved; setup backs up each config before updating it. Playwright uses the highest installed Node 22+ under nvm/current PATH. Default allowed origins are `https://e2etest.pilyr.com` and `https://arontier.pilyr.com`; set `PLAYWRIGHT_ALLOWED_ORIGINS` before setup to override them (semicolon-separated). The regular setup does not log in. It is safe to re-run.

## Usage
```powershell
copilot --agent=qa-analyst
```

Then ask:

- `Check setup`
- `Analyze STUD-17771 for requirement gaps`
- `Generate test cases for STUD-17771`
- `Analyze the stories in epic STUD-17000`

Outputs are written to `qa-copilot-cli/output/`, which is gitignored:

| File | Purpose |
|---|---|
| `<KEY>-analysis.md` | Gap analysis report |
| `<KEY>-test-cases.md` | Test cases for review |
| `<KEY>-test-cases.json` | Validated structured copy, for the future TestRail export |

## MCP tools

| Tool | Purpose |
|---|---|
| `check_setup` | Checks config, the index and Jira connectivity (no secrets returned) |
| `get_story_context` | Fetches the Jira story, source text, feature-scoped product and automation docs, shared QA guidance, role rules, and related indexed TestRail cases |
| `get_epic_children` | Lists child issues of an epic |
| `get_automation_context` | Loads selected saved cases, feature automation docs, general guidelines, and relevant existing Cypress specs/page objects/commands |
| `get_automation_context_page` | Reads bounded pages from a Jira or TestRail automation-context manifest (up to 2 items or 1,800 text characters per call) |
| `get_testrail_automation_context` | Fetches a TestRail case live by `C12345`, normalizes steps/preconditions/references, resolves the feature from case evidence and linked Jira issues, and returns grounded Cypress patterns |
| `get_testrail_automation_context_page` | Reads bounded pages from the returned context manifest (up to 2 code chunks or 1,800 text characters per call) |
| `save_cypress_preview` | Saves an approved spec under `qa-copilot-cli/output/automation/` without touching the external Cypress repository |
| `create_cypress_spec` | Creates a new `.cy.js` in the feature-mapped folder after approval; refuses to overwrite and never edits page objects/commands |
| `create_cypress_spec_from_testrail` | Creates a new spec from a live TestRail case after approval; re-fetches the case and requires its TestRail ID in the spec |
| `save_gap_analysis` | Writes Markdown and flags unsupported scenario categories for QA review without deleting them |
| `save_test_cases` | Validates schema, source citations, and traceability; flags realism and exact-title duplicate concerns; writes JSON and Markdown |

Generation citations must quote the authoritative Jira source exactly. Missing or invalid citations block saving; unsupported-scenario and duplicate checks are warnings and do not silently remove cases.

Nothing in this version writes to Jira or TestRail. Cypress generation accepts either saved Jira-generated cases or a live TestRail case ID. Feature ambiguity blocks TestRail generation rather than guessing. Cypress uses `AUTOMATION_REPO_ROOT` from `rag/.env`; only new spec files can be created, and Cypress execution is not automatic.

Example request in Copilot: `Generate Cypress automation for TestRail case C16848553`. The initial tool returns a small manifest, then the agent pages through the selected case, feature guidance and indexed code chunks. It confirms the feature against linked Jira references when present, matches case-relevant Page Objects, and retrieves Cypress code only from exact-path FAISS chunks for specs statically importing those Page Objects. Every feature also receives exact-path chunks for the common locator utility and `commands.js`. Filesystem reads are used only to resolve feature metadata/import relationships; missing required chunks stop the workflow and require index re-ingestion. It then previews the proposed spec. Choose the `output/automation/` preview destination to keep the Cypress repo unchanged, or approve creating a new spec in that repo.

If required locators are absent from the indexed Page Object chunks, the agent can use Playwright MCP to inspect only the case-relevant UI on the approved test host. It reports observed locator evidence and proposes a Cypress Page Object diff; it does not automatically edit the external repo. Authentication must use an approved UI/session flow; never put API keys or credentials in a URL or prompt. Playwright is for locator discovery only. Run the generated Cypress spec yourself from the Cypress CLI.

If sign-in is needed for locator discovery, Playwright MCP uses a headed browser by default. The agent navigates to the exact approved URL, pauses, and asks you to sign in directly in that browser. It waits for your confirmation before continuing. Never paste credentials into Copilot or have the agent read them from Cypress config. If the browser is not visible or interactive, locator discovery stops rather than using an automated credential helper.

## Tests

```powershell
cd qa-copilot-cli; ..\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Notes

- The server takes about 15 s to start because it preloads the embedding model. On Windows, loading it after the MCP stdio loop starts deadlocks, so it is loaded first.
- Product Markdown feature keys are canonicalized through `feature-aliases.json`, including aliases such as `archived-content-type` → `archive-content-type`.
- Cypress automation is grounded in the indexed automation repository and feature-context documents. It previews code first; the user must approve the target path before a new spec is written.
- Logic is copied from the Streamlit pages (Option A). A later refactor will move it into a shared module used by both.
