# QA Copilot CLI

This directory contains the QA Copilot MCP server and its tests. It is one of the two tools in the QA Intelligence Hub repository; it shares `rag/.env`, the FAISS index, and documentation with the Streamlit app.

Use the [root README](../README.md) for the complete first-time setup. From the repository root, the Copilot-specific steps are:

```powershell
.\qa-copilot-cli\setup.ps1
copilot --agent=qa-analyst
```

The Copilot registration step requires GitHub Copilot CLI and Node.js 22+. Once in the agent, run `Check setup` first.

Run the CLI regression tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qa-copilot-cli/tests -p test_core.py
```