# QA Intelligence Hub

One repository provides two QA tools that share configuration and a knowledge base:

| Tool | Purpose | Entry point |
|---|---|---|
| Streamlit Hub | Manual test-case generation, coverage dashboard, and Jira gap analysis | `custom-agent-ui/app.py` |
| QA Copilot | Jira/TestRail analysis and test generation, approved TestRail case export, plus grounded Cypress automation through GitHub Copilot | `.github/agents/qa-analyst.agent.md` |

## How the Tools Fit Together

```text
                         Jira and TestRail
                                |
                       rag/ingest_all.py
                                |
                  rag/faiss_index + rag/docs
                       /                \
          Streamlit Hub                QA Copilot
       OpenAI for generation     GitHub Copilot + qa-hub MCP
```

Both tools read the same `rag/.env`, `rag/faiss_index`, and `rag/docs`. The Streamlit app uses OpenAI for generation. The Copilot tool delegates reasoning and generation to your signed-in GitHub Copilot session; it does not need an OpenAI API key. The tools have separate user interfaces and entry points. Their Python retrieval code is not yet a shared library, so changes to one implementation do not automatically change the other.

## First-Time Setup on Windows

### Prerequisites

- Git and Git LFS
- Python 3.12 or later (64-bit)
- Jira and TestRail credentials for the services you plan to use
- An OpenAI API key for Streamlit test generation and gap analysis
- For QA Copilot only: GitHub Copilot CLI, signed-in Copilot access, and Node.js 22 or later

If Python is not installed and `winget` is available, install it from PowerShell with:

```powershell
winget install --id Python.Python.3.12 --exact
```

Close and reopen PowerShell after installation. If `winget` is unavailable, install Python 3.12+ from [python.org](https://www.python.org/downloads/windows/) and enable the Python launcher or add Python to `PATH`.

### 1. Clone and retrieve the knowledge index

```powershell
git clone <repository-url>
Set-Location qa-intelligence-hub
git lfs pull
```

The FAISS index is stored with Git LFS. If `git lfs pull` is skipped, the tools may start without a usable knowledge index.

### 2. Install the project dependencies

From the repository root, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\setup.ps1
```

This creates `.venv`, installs the dependencies for both tools from the single root `requirements.txt`, and creates `rag/.env` from the template if it does not already exist. It never replaces an existing `rag/.env`.

### 3. Configure credentials

Open `rag/.env` and fill in the credentials needed for your workflows. The file is local and must not be committed.

- Streamlit test generation and gap analysis need `OPENAI_API_KEY` and Jira settings.
- TestRail-backed workflows need the TestRail URL, user, token, and project ID.
- Jira ingestion needs `JIRA_PROJECT` as well as Jira credentials.
- QA Copilot does not need `OPENAI_API_KEY`.
- `AUTOMATION_REPO_ROOT` is optional for general Jira analysis. Set it to the absolute path of your Cypress repository to ingest Cypress code and enable repository-grounded automation generation.

### 4. Start the Streamlit Hub

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\custom-agent-ui\app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

### 5. Optional: enable QA Copilot

Install and sign in to [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli), and make sure Node.js 22+ is available. Then, from the repository root, register the QA agent and MCP servers:

```powershell
.\qa-copilot-cli\setup.ps1
copilot --agent=qa-analyst
```

The registration script configures `qa-hub` and the isolated Playwright MCP server for Copilot CLI and VS Code. In the agent, start with `Check setup`. Restart the Copilot session after changing MCP configuration. The default Playwright allowlist includes the QA app hosts and their required asset/CDN origins; set `PLAYWRIGHT_ALLOWED_ORIGINS` before running the registration script to override it.

## macOS and Linux

The shared Python environment can be installed manually from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp rag/.env.example rag/.env
```

Fill in `rag/.env`, then run:

```bash
python -m streamlit run custom-agent-ui/app.py
```

The Copilot MCP registration helper is currently a PowerShell script for Windows. On other platforms, configure the local MCP servers using the paths and commands described in `qa-copilot-cli/setup.ps1`.

## Refresh the Knowledge Base

Shared cross-feature role/access guidance is maintained in `rag/docs/shared/role-permissions.md`. Markdown ingestion includes this nested directory automatically. After moving the file from its former docs-root location, rebuild the index and restart QA Hub/Streamlit to refresh indexed source paths.

Shared feature aliases belong in `rag/config/feature-aliases.json`. Feature-specific automation documents belong in `rag/docs/automation/feature-context/<canonical-feature-key>/<canonical-feature-key>-feature-context.md` (for example, `notes/notes-feature-context.md`). The existing files are tracked; newly added files in these ignored locations require explicit staging. Moving documents from the old flat layout requires a full index rebuild and restarting the tools; see [CLI feature configuration](qa-copilot-cli/README.md).

The checked-in Git LFS index is sufficient for normal use. Rebuild it only when the indexed Jira, TestRail, documentation, or Cypress data needs refreshing. Configure `rag/.env` first. For Cypress chunks, set `AUTOMATION_REPO_ROOT` to a valid Cypress repository path.

Windows PowerShell:

```powershell
Push-Location .\rag
$env:PYTHONIOENCODING = "utf-8"
..\.venv\Scripts\python.exe .\ingest_all.py
Pop-Location
```

With no source arguments, ingestion rebuilds the entire index. Passing source names such as `jira`, `testrail`, `docs`, `pdf`, or `automation` performs an incremental update instead; it does not refresh existing document IDs. If `AUTOMATION_REPO_ROOT` is not set, automation ingestion is skipped with a warning; the rest of the index can still be rebuilt.

On Windows, ingestion uses the system certificate store through `truststore` while keeping HTTPS certificate verification enabled. A TestRail suite, section, or case fetch failure aborts a full rebuild before replacing the existing index. If a previous run reported TestRail errors followed by a successful build, rerun the full rebuild after resolving the error; that index may be missing TestRail cases. Restart running MCP servers after rebuilding to clear their cached index.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qa-copilot-cli/tests -p "test_*.py"
```

## Repository Layout

```text
custom-agent-ui/       Streamlit application and pages
qa-copilot-cli/        QA MCP server, Copilot integration, and tests
rag/                   Shared ingestion code, docs, config, and FAISS index
.github/agents/        QA analyst agent instructions
.github/skills/        Reusable Jira, test design, review, and Cypress workflows
requirements.txt       The only supported Python dependency manifest
setup.ps1              Windows first-time Python environment setup
```

`custom-agent/` contains an older prototype and is not one of the two supported tools. Use this README as the installation source of truth; `qa-copilot-cli/README.md` is only a short CLI reference.