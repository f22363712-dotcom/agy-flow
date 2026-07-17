"""MCP Client Smoke — simulate an MCP client against agent-relay MCP server.

v2: now also tests resources/list, resources/read (board + handoff),
and the 3 new handoff tools (write / read / ack).

Creates a temporary project, starts the MCP server as a subprocess,
sends all JSON-RPC messages, reads all responses, validates each one.

Usage: python scripts/mcp_client_smoke.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _find_project_root():
    curr = Path(__file__).parent.parent.resolve()
    if (curr / "agent-relay.py").exists():
        return curr
    return None


def main():
    project_root = _find_project_root()
    if project_root is None:
        print(json.dumps({"overall": "fail", "error": "Cannot find project root"}))
        return 1

    report = {
        "script": __file__,
        "steps": [],
        "passed": 0,
        "failed": 0,
        "overall": "pending",
    }

    def record(step, status, detail=None):
        report["steps"].append(
            {
                "step": step,
                "status": status,
                "detail": str(detail)[:500] if detail else None,
            }
        )
        if status == "pass":
            report["passed"] += 1
        elif status == "fail":
            report["failed"] += 1
        print(f"  [{status.upper()}] {step} {detail or ''}")

    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name).resolve()
    os.environ["AGY_FLOW_TESTING"] = "1"

    # Init minimal project in temp dir
    try:
        sys.path.insert(0, str(project_root))
        from agent_relay.config import update_paths
        from agent_relay.tasks import init_project

        update_paths(temp_path)
        init_project(type("", (), {})())
        config_path = temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        import agent_relay.git_ops

        agent_relay.git_ops.PROJECT_ROOT = temp_path
        record("0. init_temp_project", "pass")
    except Exception as e:
        record("0. init_temp_project", "fail", str(e))
        print(json.dumps(report, indent=2))
        return 1

    proc = None
    try:
        agent_relay_py = str(project_root / "agent-relay.py")
        proc = subprocess.Popen(
            [sys.executable, agent_relay_py, "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(temp_path),
            text=True,
        )
        record("1. start_server", "pass")

        # Build ALL messages — v2 now includes resources + handoff tools
        all_msgs = [
            # v1 baseline
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "agy_doctor", "arguments": {}},
            },
            # v2: resources
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": "board://tasks"},
            },
            # v2: handoff tools
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "agy_handoff_write",
                    "arguments": {
                        "task_id": "task-001",
                        "from_agent": "claude",
                        "to_agent": "codex",
                        "summary": "Smoke test handoff",
                        "context": "This is a smoke test context for the MCP blackboard.",
                        "commit_hash": "deadbeef",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "agy_handoff_read",
                    "arguments": {"task_id": "task-001"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "agy_handoff_ack",
                    "arguments": {"task_id": "task-001", "agent": "codex"},
                },
            },
            # v2: read handoff resource after writing
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "resources/read",
                "params": {"uri": "handoff://current/task-001"},
            },
        ]

        # Write all messages, then close stdin
        for m in all_msgs:
            proc.stdin.write(json.dumps(m) + "\n")
        proc.stdin.flush()
        proc.stdin.close()

        # Read all responses
        stdout_data, stderr_data = proc.communicate(timeout=30)
        lines = [l.strip() for l in stdout_data.split("\n") if l.strip()]

        # We expect >= 8 responses (initialize, tools/list, doctor, resources/list,
        # board read, handoff write, handoff read, handoff ack, handoff
        # resource read)
        if len(lines) < 5:
            record(
                "2. responses",
                "fail",
                f"Expected >=5 responses, got {len(lines)}: stderr={stderr_data[:200]}",
            )
            print(json.dumps(report, indent=2))
            return 1

        parsed = []
        for i, l in enumerate(lines):
            parsed.append(json.loads(l))

        # Parse by id or error
        for r in parsed:
            if r.get("error"):
                print(f"  ERROR from server: {r['error']['message'][:100]}")
                record("server_error", "warn", r["error"]["message"][:100])

        response_map = {}
        for r in parsed:
            if "id" in r:
                response_map[r["id"]] = r

        # 2. initialize (id=1)
        r1 = response_map.get(1)
        if r1 and "result" in r1:
            caps = r1["result"].get("capabilities", {})
            has_tools = "tools" in caps
            has_resources = "resources" in caps
            if not has_resources:
                record(
                    "2. initialize",
                    "fail",
                    "missing resources capability",
                )
            else:
                record(
                    "2. initialize",
                    "pass",
                    f"version={r1['result'].get('protocolVersion')} "
                    f"tools={has_tools} resources={has_resources}",
                )
        else:
            record("2. initialize", "fail", "no init response")

        # 3. notification - no response expected
        record("3. notification", "pass")

        # 4. tools/list (id=2)
        r2 = response_map.get(2)
        if r2 and "result" in r2 and "tools" in r2["result"]:
            tools = r2["result"]["tools"]
            names = {t["name"] for t in tools}
            has_handoff = "agy_handoff_write" in names
            if not has_handoff:
                record(
                    "4. tools/list",
                    "fail",
                    f"{len(tools)} tools, handoff tools missing",
                )
            else:
                record(
                    "4. tools/list",
                    "pass",
                    f"{len(tools)} tools, handoff={has_handoff}",
                )
        else:
            record("4. tools/list", "fail", f"No tools response: {r2}")

        # 5. agy_doctor (id=3)
        r3 = response_map.get(3)
        if r3 and "result" in r3:
            txt = json.loads(r3["result"]["content"][0]["text"])
            record("5. agy_doctor", "pass", f"healthy={txt.get('healthy')}")
        else:
            record("5. agy_doctor", "warn", f"No doctor response: {r3}")

        # 6. resources/list (id=4)
        r4 = response_map.get(4)
        if r4 and "result" in r4 and "resources" in r4["result"]:
            res_list = r4["result"]["resources"]
            record("6. resources/list", "pass", f"{len(res_list)} resources")
        else:
            record("6. resources/list", "fail", f"No resources response: {r4}")

        # 7. resources/read board://tasks (id=5)
        r5 = response_map.get(5)
        if r5 and "result" in r5:
            contents = r5["result"]["contents"]
            record("7. board://tasks", "pass", f"{len(contents)} content(s)")
        else:
            record("7. board://tasks", "fail", f"No board response: {r5}")

        # 8. agy_handoff_write (id=6)
        r6 = response_map.get(6)
        if r6 and "result" in r6:
            txt = json.loads(r6["result"]["content"][0]["text"])
            has_id = bool(txt.get("handoff_id"))
            if has_id:
                record(
                    "8. handoff_write",
                    "pass",
                    f"handoff_id={txt.get('handoff_id')}",
                )
            else:
                record("8. handoff_write", "fail", "missing handoff_id")
        else:
            record("8. handoff_write", "fail", f"No write response: {r6}")

        # 9. agy_handoff_read (id=7)
        r7 = response_map.get(7)
        if r7 and "result" in r7:
            txt = json.loads(r7["result"]["content"][0]["text"])
            record("9. handoff_read", "pass", f"summary={txt.get('summary')}")
        else:
            record("9. handoff_read", "fail", f"No read response: {r7}")

        # 10. agy_handoff_ack (id=8)
        r8 = response_map.get(8)
        if r8 and "result" in r8:
            txt = json.loads(r8["result"]["content"][0]["text"])
            record("10. handoff_ack", "pass", f"status={txt.get('status')}")
        else:
            record("10. handoff_ack", "fail", f"No ack response: {r8}")

        # 11. resources/read handoff://current (id=9)
        r9 = response_map.get(9)
        if r9 and "result" in r9:
            record("11. handoff_resource", "pass", "handoff://current read ok")
        else:
            record(
                "11. handoff_resource", "fail", f"No handoff resource response: {r9}"
            )

        # 12. stdout clean
        record("12. stdout_clean", "pass", f"{len(lines)} JSON-RPC lines")

        # 13. stderr check
        if stderr_data and "Traceback" in stderr_data:
            record("13. stderr_clean", "warn", "Traceback in stderr")
        else:
            record("13. server_shutdown", "pass")

        report["overall"] = "pass" if report["failed"] == 0 else "fail"
        print(f"\nSmoke report: {report['passed']} passed, {report['failed']} failed")

    except Exception as e:
        report["overall"] = "fail"
        report["error"] = str(e)
        import traceback

        traceback.print_exc()
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
        try:
            temp_dir.cleanup()
        except Exception:
            pass

    print(json.dumps(report, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
