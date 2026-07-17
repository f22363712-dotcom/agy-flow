"""Smoke test for the full agent-relay lifecycle.

Creates a temporary project, runs the complete MVP flow, and outputs a
JSON smoke report.  No real API calls or GUI launches occur.
"""

import json
import os
import sys
import tempfile
import threading
import socket
import importlib.util
from http.server import HTTPServer
from pathlib import Path

# Path setup
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

os.environ["AGY_FLOW_TESTING"] = "1"


def free_port():
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    report = {
        "smoke_test": True,
        "script": __file__,
        "steps": [],
        "passed": 0,
        "failed": 0,
        "overall": "pending",
    }

    def step(name):
        def record(status="pass", detail=None):
            entry = {"step": name, "status": status}
            if detail:
                entry["detail"] = str(detail)[:500]
            report["steps"].append(entry)
            if status == "pass":
                report["passed"] += 1
            else:
                report["failed"] += 1
            print(f"  [{status.upper()}] {name}")

        return record

    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name).resolve()
    print(f"Smoke test temp dir: {temp_path}")

    try:
        # Import the module
        spec = importlib.util.spec_from_file_location(
            "agent_relay_main", project_root / "agent-relay.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["agent_relay_main"] = mod
        spec.loader.exec_module(mod)

        # Patch paths
        mod.PROJECT_ROOT = temp_path
        mod.AGENTS_DIR = temp_path / ".agents"
        mod.TASKS_DIR = mod.AGENTS_DIR / "tasks"
        mod.BOARD_FILE = mod.TASKS_DIR / "board.md"

        import agent_relay.config

        agent_relay.config.update_paths(temp_path)

        import agent_relay.git_ops

        orig_git_root = agent_relay.git_ops.PROJECT_ROOT
        agent_relay.git_ops.PROJECT_ROOT = temp_path

        # Init
        step1 = step("1. init_project")

        class DummyArgs:
            pass

        mod.init_project(DummyArgs())
        step1("pass")

        # Fix config
        config_path = temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        # Create task
        step2 = step("2. create_task")

        class CreateArgs:
            title = "Smoke test task"
            agent = "claude"
            desc = "Auto-generated smoke test"

        mod.create_task(CreateArgs())
        step2("pass")

        # Route
        step3 = step("3. route")
        from agent_relay.router import route_task_by_id

        route = route_task_by_id("task-001")
        assert route.get("primary"), "Route missing primary"
        step3("pass")

        # Auto dispatch dry-run
        step4 = step("4. auto_dispatch_dry_run")
        from agent_relay.orchestrator import auto_dispatch_task

        dry = auto_dispatch_task("task-001", dry_run=True)
        assert dry["status"] == "dry_run", f"Expected dry_run, got {dry['status']}"
        step4("pass")

        # Start gateway
        port = free_port()
        server = HTTPServer(("127.0.0.1", port), mod.AgentRelayHTTPHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        base_url = f"http://127.0.0.1:{port}"

        # Dispatch deepseek mock via API
        step5 = step("5. dispatch_deepseek_mock")
        import urllib.request

        payload = json.dumps({"agent": "deepseek", "mock": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/tasks/task-001/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
        assert data.get("status") == "success", f"Dispatch failed: {data.get('error')}"
        step5("pass", detail=f"run_id={data.get('run_id')}")

        # Continue mock
        step6 = step("6. continue_after_run")
        run_id = data["run_id"]
        from agent_relay.review_loop import continue_after_run

        loop = continue_after_run(run_id, mock=True)
        assert loop["status"] in (
            "continued",
            "no_action",
            "failed",
        ), f"Unexpected: {loop['status']}"
        step6("pass", detail=f"status={loop['status']}")

        # Quality
        step7 = step("7. quality_gate")
        from agent_relay.quality_gate import evaluate_task_quality

        quality = evaluate_task_quality("task-001")
        assert "ready" in quality
        step7(
            "pass",
            detail=f"ready={quality['ready']} blocking={len(quality['blocking_issues'])}",
        )

        # Finalize dry-run
        step8 = step("8. finalize_dry_run")
        from agent_relay.submit_pipeline import finalize_task

        final = finalize_task("task-001", dry_run=True)
        assert final["status"] == "dry_run", f"Expected dry_run, got {final['status']}"
        step8("pass")

        # Doctor
        step9 = step("9. doctor")
        from agent_relay.doctor import doctor

        health = doctor()
        assert "healthy" in health
        step9("pass", detail=f"healthy={health['healthy']}")

        # Task status
        step10 = step("10. task_status")
        from agent_relay.doctor import task_status

        info = task_status("task-001")
        assert info["task_id"] == "task-001"
        step10("pass")

        # Gateway doctor
        step11 = step("11. gateway_doctor")
        req = urllib.request.Request(f"{base_url}/doctor")
        with urllib.request.urlopen(req) as res:
            ghealth = json.loads(res.read().decode("utf-8"))
        assert "healthy" in ghealth
        step11("pass")

        # Cleanup
        server.shutdown()
        server.server_close()
        thread.join()
        agent_relay.git_ops.PROJECT_ROOT = orig_git_root

        report["overall"] = "pass" if report["failed"] == 0 else "fail"
        print(f"\nSmoke report: {report['passed']} passed, {report['failed']} failed")

    except Exception as e:
        report["overall"] = "fail"
        report["error"] = str(e)
        print(f"\nSmoke test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        try:
            temp_dir.cleanup()
        except Exception:
            pass

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
