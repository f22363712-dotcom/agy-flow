"""Doctor and Status modules — health checks and task summaries."""

import datetime
import json
import os
import sys
from pathlib import Path

# Import the module so we can reference its live attributes
import agent_relay.config
from agent_relay.config import (
    get_config,
    get_agent_registry,
)
from agent_relay.connectors import agents_report, probe_all
from agent_relay.state_machine import get_task_state
from agent_relay.adapter import list_runs
from agent_relay.quality_gate import evaluate_task_quality
from agent_relay.policy import get_policy_info
from agent_relay.errors import AgentRelayError
from agent_relay.git_ops import run_cmd


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def doctor():
    """Run a full system health check.

    Returns a dict with checks, warnings, and a healthy flag.
    """
    # Use live module attributes (not stale import bindings)
    cfg_file = agent_relay.config.CONFIG_FILE
    board_file = agent_relay.config.BOARD_FILE
    project_root = agent_relay.config.PROJECT_ROOT
    agents_dir = agent_relay.config.AGENTS_DIR
    runs_dir = agent_relay.config.RUNS_DIR
    tasks_dir = agent_relay.config.TASKS_DIR

    checks = []
    warnings = []
    errors = []

    # 1. Config file
    cfg = None
    if cfg_file and cfg_file.exists():
        try:
            cfg = get_config()
            checks.append({"check": "config", "status": "ok", "detail": str(cfg_file)})
        except Exception as e:
            errors.append({"check": "config", "status": "error", "detail": str(e)})
    else:
        errors.append(
            {
                "check": "config",
                "status": "error",
                "detail": "Config file not found. Run 'agent-relay init'.",
            }
        )

    # 2. Agent registry
    try:
        registry = get_agent_registry(cfg)
        agent_count = len(registry)
        checks.append(
            {
                "check": "agent_registry",
                "status": "ok",
                "detail": f"{agent_count} agents registered",
            }
        )
    except Exception as e:
        warnings.append(
            {"check": "agent_registry", "status": "warning", "detail": str(e)}
        )

    # 3. Connector probe
    try:
        probes = probe_all()
        available = sum(1 for p in probes if p.get("available"))
        total = len(probes)
        checks.append(
            {
                "check": "connectors",
                "status": "ok",
                "detail": f"{available}/{total} agents available",
            }
        )
        for p in probes:
            if not p.get("available"):
                warnings.append(
                    {
                        "check": f"connector:{p['name']}",
                        "status": "warning",
                        "detail": p.get("reason", "unavailable"),
                    }
                )
    except Exception as e:
        warnings.append({"check": "connectors", "status": "warning", "detail": str(e)})

    # 4. Board file
    if board_file and board_file.exists():
        checks.append({"check": "board", "status": "ok", "detail": str(board_file)})
    else:
        warnings.append(
            {
                "check": "board",
                "status": "warning",
                "detail": "Board file not found. Run 'agent-relay init'.",
            }
        )

    # 5. Runs dir
    if runs_dir:
        runs_dir.mkdir(parents=True, exist_ok=True)
        checks.append({"check": "runs_dir", "status": "ok", "detail": str(runs_dir)})

    # 6. Tasks dir
    if tasks_dir and tasks_dir.exists():
        task_files = list(tasks_dir.glob("*.md"))
        checks.append(
            {
                "check": "tasks_dir",
                "status": "ok",
                "detail": f"{len(task_files)} task files",
            }
        )
    else:
        warnings.append(
            {
                "check": "tasks_dir",
                "status": "warning",
                "detail": "Tasks dir not found.",
            }
        )

    # 7. Git repo
    if project_root:
        git_dir = project_root / ".git"
        if git_dir.exists():
            code, stdout, stderr = run_cmd(["git", "status", "--porcelain"])
            dirty = bool(stdout.strip())
            detail = "clean" if not dirty else "uncommitted changes"
            checks.append({"check": "git", "status": "ok", "detail": detail})
            if dirty:
                warnings.append(
                    {
                        "check": "git_dirty",
                        "status": "warning",
                        "detail": "Repository has uncommitted changes.",
                    }
                )
        else:
            warnings.append(
                {"check": "git", "status": "warning", "detail": "Not a git repository."}
            )

    # 8. Current task guard
    guard_path = agents_dir / "current_task.json" if agents_dir else None
    if guard_path and guard_path.exists():
        try:
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
            checks.append(
                {
                    "check": "current_task_guard",
                    "status": "ok",
                    "detail": f"Assigned to {guard.get('agent', 'unknown')} ({
                        guard.get('role', '?')
                    })",
                }
            )
        except Exception as e:
            warnings.append(
                {"check": "current_task_guard", "status": "warning", "detail": str(e)}
            )
    else:
        checks.append(
            {
                "check": "current_task_guard",
                "status": "ok",
                "detail": "No active guard (idle).",
            }
        )

    healthy = len(errors) == 0

    return {
        "healthy": healthy,
        "timestamp": _now(),
        "project_root": str(project_root) if project_root else None,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def task_status(task_id):
    """Return a comprehensive summary for a single task.

    Combines state, route (via get_task_state + runs), quality, and policy
    into a single report.
    """
    state = get_task_state(task_id)
    runs = list_runs(task_id=task_id)[:5]  # latest 5
    quality = evaluate_task_quality(task_id)
    policy = get_policy_info(task_id)

    writer_runs = [r for r in runs if r.get("role") == "writer"]
    reviewer_runs = [r for r in runs if r.get("role") == "reviewer"]

    return {
        "task_id": task_id,
        "state": state.get("state", "unknown"),
        "state_reason": state.get("reason", ""),
        "state_updated": state.get("updated_at", ""),
        "run_count": len(list_runs(task_id=task_id)),
        "latest_writer": writer_runs[0] if writer_runs else None,
        "latest_reviewer": reviewer_runs[0] if reviewer_runs else None,
        "quality_ready": quality.get("ready", False),
        "quality_blocking_count": len(quality.get("blocking_issues", [])),
        "quality_warning_count": len(quality.get("warnings", [])),
        "quality_recommended": quality.get("recommended_next_action", "manual"),
        "policy_run_count": policy.get("run_count", 0),
        "policy_max_loop": policy.get("max_auto_loop", 3),
        "policy_can_dispatch": policy.get("can_dispatch_new", False),
        "timestamp": _now(),
    }
