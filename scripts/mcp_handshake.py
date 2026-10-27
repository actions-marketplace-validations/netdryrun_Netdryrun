"""MCP stdio handshake against an installed Netdryrun, the way an MCP client starts it.

Usage: python scripts/mcp_handshake.py uvx netdryrun mcp

Speaks raw JSON-RPC (no mcp package needed on the client side): initialize, initialized,
tools/list. Exits 1 unless the server answers as netdryrun with all documented tools.
"""
import json
import subprocess
import sys
import threading

TOOLS = {"dry_run", "run_checks", "record_baseline", "validate", "check_types"}
TIMEOUT = 180  # the first uvx run downloads and installs the package


def main() -> int:
    cmd = sys.argv[1:]
    if not cmd:
        print(__doc__)
        return 2
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
    timer = threading.Timer(TIMEOUT, proc.kill)
    timer.start()

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def reply(want_id: int) -> dict:
        for line in proc.stdout:  # skip notifications and anything that is not our reply
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == want_id:
                return msg
        raise SystemExit(f"server closed stdout before replying to request {want_id} (exit {proc.poll()})")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "netdryrun-handshake", "version": "1"}}})
        init = reply(1)
        info = init.get("result", {}).get("serverInfo", {})
        print(f"initialize: protocol {init.get('result', {}).get('protocolVersion')}, server {info}")
        if "error" in init or info.get("name") != "netdryrun":
            print(f"unexpected initialize reply: {init}")
            return 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in reply(2).get("result", {}).get("tools", [])}
        print(f"tools/list: {sorted(tools)}")
        if not TOOLS <= tools:
            print(f"missing tools: {sorted(TOOLS - tools)}")
            return 1
        print("MCP handshake OK")
        return 0
    finally:
        timer.cancel()
        proc.stdin.close()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
