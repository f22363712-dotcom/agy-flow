"""CLI Agent Execution v1 — run external CLI agents via subprocess.

Provides a single function ``run_cli_agent`` that calls an external CLI
agent (claude, gemini, etc.) with a task-context prompt and captures
stdout, stderr, return code, and duration.  No GUI is launched; ``shell``
is never set to ``True``.
"""

import datetime
import os
import subprocess
import sys
import shutil
import json
from pathlib import Path


def run_cli_agent(agent, command, prompt, cwd=None, timeout=120):
    """Execute an external CLI agent with a prompt and capture output.

    Parameters
    ----------
    agent : str
        Agent name (used for error messages only).
    command : list[str]
        Executable + args, e.g. ``["claude", "-p", "..."]``.
    prompt : str
        The full task-context prompt to pass to the agent.
    cwd : str or Path, optional
        Working directory (defaults to current).
    timeout : int
        Seconds before the subprocess is killed.

    Returns
    -------
    dict with keys:
        ``status`` (``success`` | ``unavailable`` | ``error`` | ``timeout``),
        ``returncode``, ``stdout``, ``stderr``, ``duration_ms``,
        ``error`` (human-readable on failure).
    """
    # Validate the command executable exists
    exe = command[0] if command else ""
    if not exe or not shutil.which(exe):
        return {
            "status": "unavailable",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_ms": 0,
            "error": f"CLI '{exe}' not found on PATH. Install {
                agent.capitalize()
            } CLI.",
        }

    start = datetime.datetime.now()

    try:
        res = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            env=os.environ.copy(),
        )
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)

        if res.returncode == 0:
            status = "success"
            error_text = ""
        else:
            status = "error"
            error_text = res.stderr.strip() or f"Exit code {res.returncode}"

        return {
            "status": status,
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "duration_ms": duration_ms,
            "error": error_text,
        }

    except subprocess.TimeoutExpired:
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return {
            "status": "timeout",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_ms": duration_ms,
            "error": f"CLI agent '{agent}' timed out after {timeout}s.",
        }

    except FileNotFoundError:
        return {
            "status": "unavailable",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_ms": 0,
            "error": f"CLI '{exe}' not found at invocation time.",
        }

    except Exception as e:
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_ms": duration_ms,
            "error": f"Unexpected error invoking {agent}: {e}",
        }


def build_agent_prompt(
    task_id, title, task_spec="", plan_text="", route=None, role="writer"
):
    """Build a standard task-context prompt for an external CLI agent.

    The prompt follows the contract defined in docs/agent-execution-contract.md.
    """
    lines = []
    lines.append(f"You are assigned to work on task {task_id} inside agent-relay.")
    lines.append("")
    lines.append(f"## Task: {task_id} - {title}")
    lines.append("")
    lines.append(f"### Role")
    lines.append(f"You are acting as a **{role}** for this task.")
    if role == "reviewer":
        lines.append(
            "You may read code and produce reviews, but must NOT modify files."
        )
    else:
        lines.append("You have full write access to the worktree.")
    lines.append("")

    if task_spec:
        lines.append("### Task Specification")
        lines.append(task_spec)
        lines.append("")

    if plan_text:
        lines.append("### Routing Plan")
        lines.append(plan_text)
        lines.append("")

    if route:
        lines.append("### Current Route")
        lines.append(json.dumps(route, indent=2, ensure_ascii=False))
        lines.append("")

    lines.append("### Workflow Requirements")
    lines.append("1. Read .agents/current_task.json to verify your assignment.")
    lines.append("2. Work inside the worktree directory only.")
    lines.append("3. Do NOT modify files outside the worktree.")
    lines.append("4. When finished, run: agent-relay submit {0}".format(task_id))
    lines.append("5. Do NOT commit or push to the main branch directly.")
    lines.append("")

    return "\n".join(lines)


def update_module_paths():
    """No-op: kept for config.update_paths compatibility."""
    pass
