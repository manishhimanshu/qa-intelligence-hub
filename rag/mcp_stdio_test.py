"""
Quick smoke test: send real MCP JSON-RPC messages to the retriever server
over stdio and measure response time.
Run: python mcp_stdio_test.py
Tests the pure-stdlib retriever_mcp_server.py (no fastmcp/anyio dependency).
"""
import subprocess, json, time, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

proc = subprocess.Popen(
    [sys.executable, "retriever_mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=open("mcp_server_child.err", "w"),
    text=True,
    bufsize=1,
)

def send(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()

def read_line(timeout=10):
    import select, platform
    deadline = time.time() + timeout
    if platform.system() == "Windows":
        # Windows: just use readline with process poll
        import threading
        result = []
        def _read():
            result.append(proc.stdout.readline())
        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        return result[0] if result else ""
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            return line
    return ""

print("=== MCP stdio smoke test ===")

# 1. Initialize
print("1. Sending initialize...")
send({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "clientInfo": {"name": "smoke-test", "version": "1.0"},
    },
})
resp = read_line(timeout=15)
if resp.strip():
    data = json.loads(resp)
    print(f"   OK — server name: {data.get('result', {}).get('serverInfo', {}).get('name', '?')}")
else:
    print("   TIMEOUT — no initialize response after 15s")
    proc.terminate()
    sys.exit(1)

# 2. Initialized notification
send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

# 3. Call retrieve tool
print("2. Calling retrieve tool...")
send({
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "retrieve", "arguments": {"prompt": "content export CSV", "top_k": 2}},
})

start = time.time()
resp = read_line(timeout=30)
elapsed = time.time() - start

if resp.strip():
    data = json.loads(resp)
    content = data.get("result", {}).get("content", [])
    print(f"   OK — responded in {elapsed:.2f}s, content items: {len(content)}")
    if content:
        text = content[0].get("text", "")
        print(f"   Preview: {text[:120]}")
else:
    print(f"   TIMEOUT — no tool response after 30s ({elapsed:.1f}s elapsed)")

proc.terminate()
print("\nServer child stderr log written to mcp_server_child.err")
