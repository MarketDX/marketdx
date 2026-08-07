#!/usr/bin/env python3
"""Minimal MCP streamable-HTTP client for testing the deployed marketdx-mcp.
Usage:
  python3 mcpcli.py list
  python3 mcpcli.py call <tool_name> '<json-args>'
Each run does a fresh initialize → (op). The DECISION of which tool + args is the CALLER's job.
"""
import sys, json, os, urllib.request, uuid

# The deployed MCP endpoint + a test Bearer. Set MDX_TEST_BEARER in your env (a test-account key, e.g. the
# fin-mcp-test account) — DO NOT hardcode a live key here.
ENDPOINT = os.environ.get("MDX_MCP_ENDPOINT", "https://marketdx-mcp-485191690396.us-east1.run.app/mcp")
BEARER = os.environ.get("MDX_TEST_BEARER", "")
if not BEARER:
    sys.exit("set MDX_TEST_BEARER (a test-account API key) in your environment first")

def _post(body, session=None):
    headers = {
        "Authorization": f"Bearer {BEARER}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=90)
    sid = resp.headers.get("Mcp-Session-Id")
    raw = resp.read().decode()
    # streamable-http may return SSE ("data: {...}") or plain JSON
    out = None
    if "data:" in raw:
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    out = json.loads(line[5:].strip())
                except Exception:
                    pass
    else:
        try:
            out = json.loads(raw)
        except Exception:
            out = {"_raw": raw[:500]}
    return out, sid

def _rpc(method, params, id_=1, session=None):
    return _post({"jsonrpc": "2.0", "id": id_, "method": method, "params": params}, session)

def init():
    out, sid = _rpc("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "mcp-financials-test", "version": "1.0"},
    })
    # notifications/initialized (best-effort)
    try:
        _post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session=sid)
    except Exception:
        pass
    return out, sid

def main():
    if len(sys.argv) < 2:
        print("usage: mcpcli.py list | call <tool> '<json-args>'"); return
    initres, sid = init()
    if sys.argv[1] == "list":
        out, _ = _rpc("tools/list", {}, id_=2, session=sid)
        tools = (out or {}).get("result", {}).get("tools", [])
        print(f"# server instructions:\n{(initres or {}).get('result', {}).get('instructions', '')[:4000]}\n")
        print(f"# {len(tools)} tools:")
        for t in tools:
            print(f"- {t['name']}: {t.get('description','')[:180]}")
    elif sys.argv[1] == "call":
        tool = sys.argv[2]
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        out, _ = _rpc("tools/call", {"name": tool, "arguments": args}, id_=3, session=sid)
        print(json.dumps(out, indent=2)[:20000])

if __name__ == "__main__":
    main()
