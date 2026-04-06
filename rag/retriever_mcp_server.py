"""
Kapost RAG Retriever — MCP stdio server (pure-stdlib, no anyio/fastmcp).

Uses a straightforward synchronous stdin/stdout loop so it works reliably on
Windows with Python 3.13+ (anyio async-pipe issues avoided entirely).
"""

import json
import sys
import os
import logging

from dotenv import load_dotenv

# Resolve .env relative to this file regardless of working directory
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from get_relevant_docs import get_relevant_docs

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
log = logging.getLogger(__name__)

_TOOL_DEF = {
    "name": "retrieve",
    "description": (
        "Retrieve relevant Kapost knowledge for a given prompt. "
        "Sources: Jira stories (STUD project), TestRail test cases (project 34), "
        "product documentation, and existing Cypress automation patterns. "
        "Returns the top_k most relevant document chunks."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Natural-language search query",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["prompt"],
    },
}


def _send(msg: dict) -> None:
    """Write a JSON-RPC message to stdout and flush immediately."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _handle(request: dict) -> None:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    # Notifications have no id and need no reply
    if method == "notifications/initialized":
        return

    if method == "initialize":
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kapost-rag", "version": "1.0.0"},
            },
        })
        return

    if method == "tools/list":
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [_TOOL_DEF]},
        })
        return

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "retrieve":
            try:
                results = get_relevant_docs(
                    args.get("prompt", ""),
                    top_k=int(args.get("top_k", 5)),
                )
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(results, indent=2)}
                        ]
                    },
                })
            except Exception as exc:
                log.exception("retrieve failed")
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(exc)},
                })
        else:
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            })
        return

    # Unknown method with an id → return error
    if req_id is not None:
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })


def main() -> None:
    """Read newline-delimited JSON-RPC messages from stdin, reply to stdout."""
    # Re-open stdin/stdout in UTF-8 text mode so Windows doesn't mangle encoding
    stdin = open(sys.stdin.fileno(), encoding="utf-8", errors="replace", closefd=False)
    # Redirect our global stdout writes through a UTF-8 wrapped stdout
    global_stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
    sys.stdout = global_stdout

    for raw_line in stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            log.warning("Bad JSON from client: %s — %s", exc, raw_line[:80])
            continue
        try:
            _handle(request)
        except Exception:
            log.exception("Unhandled error processing request")


if __name__ == "__main__":
    main()
