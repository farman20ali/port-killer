"""
Manual MCP test script for kport.
Simulates a real AI client talking to the kport MCP server over stdio.
"""

import subprocess
import json
import sys
import time

# Path to your kport entry point
KPORT_CMD = [sys.executable, "kport.py", "mcp"]


def send_and_receive(proc, message: dict) -> dict:
    """Send one JSON-RPC message and read one response."""
    line = json.dumps(message) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    response_line = proc.stdout.readline()
    return json.loads(response_line)


def pretty(obj: dict):
    print(json.dumps(obj, indent=2))
    print()


def run_tests():
    print("=" * 60)
    print("  kport MCP Server - Manual Test Session")
    print("=" * 60)
    print()

    proc = subprocess.Popen(
        KPORT_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        # ── 1. Initialize ──────────────────────────────────────────
        print("[Step 1] initialize")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"}
            }
        })
        pretty(resp)

        # ── 2. Notify initialized ──────────────────────────────────
        # (notification — no response expected)
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }) + "\n")
        proc.stdin.flush()

        # ── 3. List tools ──────────────────────────────────────────
        print("[Step 2] tools/list")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })
        pretty(resp)

        # ── 4. Call list_ports ─────────────────────────────────────
        print("[Step 3] call list_ports")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "list_ports",
                "arguments": {}
            }
        })
        pretty(resp)

        # ── 5. Call inspect_port on port 80 ────────────────────────
        print("[Step 4] call inspect_port (port=80)")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "inspect_port",
                "arguments": {"port": 80}
            }
        })
        pretty(resp)

        # ── 6. Try to kill a protected port — safety test ──────────
        print("[Step 5] kill_port protected port (port=443) - should be BLOCKED")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "kill_port",
                "arguments": {"port": 443}
            }
        })
        # Parse inner content
        content_text = resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
        result = json.loads(content_text)
        if not result.get("success", True):
            print(f"  [PASS] Safety Shield correctly blocked port 443: {result['message']}")
        else:
            print(f"  [WARN] Unexpected: kill succeeded on protected port 443")
        print()

        # ── 7. Try to kill a free/safe port ────────────────────────
        print("[Step 6] kill_port safe port (port=19999) - probably free")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "kill_port",
                "arguments": {"port": 19999, "force": True}
            }
        })
        pretty(resp)

        # ── 8. Unknown method — error handling test ────────────────
        print("[Step 7] unknown method - should return method-not-found error")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "does/not/exist",
            "params": {}
        })
        pretty(resp)

        print("=" * 60)
        print("  [DONE] All tests complete!")
        print("=" * 60)

    finally:
        proc.stdin.close()
        proc.terminate()
        stderr_output = proc.stderr.read()
        if stderr_output:
            print("\n-- Server stderr (debug logs) --")
            print(stderr_output)


if __name__ == "__main__":
    run_tests()
