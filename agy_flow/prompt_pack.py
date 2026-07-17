"""Agent Handoff Prompt Pack v1 — generate task-context prompts for external agents.

The core function ``build_handoff_prompt()`` reads the current guard state,
task board, runs, route, quality, and policy, then assembles a structured
prompt that can be copied/pasted into Claude, Codex, or Antigravity.
"""

import datetime
import json

from agy_flow.config import get_config, get_agent_registry
from agy_flow.handoff import whoami
from agy_flow.state_machine import get_task_state
from agy_flow.adapter import list_runs
from agy_flow.quality_gate import evaluate_task_quality
from agy_flow.policy import get_policy_info
from agy_flow.errors import AgyFlowError
from agy_flow.workspaces import resolve_workspace

_AGENT_DISPLAY = {
    "claude": "Claude Code",
    "codex": "Codex (VS Code)",
    "antigravity": "Antigravity",
    "deepseek": "DeepSeek",
    "gemini": "Gemini CLI",
}

_SAFETY_CONSTRAINTS = [
    "Do NOT write API keys into code or config.",
    "Do NOT launch any GUI, browser, or desktop application.",
    "Do NOT call real external APIs unless explicitly instructed.",
    "Work inside the assigned worktree directory only.",
    "Do NOT commit or push to the main branch directly.",
    "When finished, run: agy-flow submit {task_id} (if writer).",
]


def build_handoff_prompt(
    target_agent, task_id=None, objective=None, include_context=True
):
    """Build a structured handoff prompt for *target_agent*.

    Parameters
    ----------
    target_agent : str
        One of claude, codex, antigravity.
    task_id : str, optional
        If omitted, uses the active task from the guard file.
    objective : str, optional
        Free-text objective for this handoff.
    include_context : bool
        If True, include full task/runs/quality/policy context.

    Returns
    -------
    dict with keys ``target_agent``, ``task_id``, ``prompt``,
    ``context_files``, ``warnings``.
    """
    target = target_agent.strip().lower()
    if target not in _AGENT_DISPLAY:
        raise AgyFlowError(
            f"Unknown agent '{target_agent}'. Known: {
                ', '.join(sorted(_AGENT_DISPLAY))
            }"
        )

    guard = whoami()
    if not task_id:
        task_id = guard.get("task_id")

    context_files = []
    warnings = []

    # 1. Guard context
    prompt_sections = []
    prompt_sections.append(
        f"You are about to hand off work to **{_AGENT_DISPLAY[target]}** "
        f"inside the agy-flow collaboration framework."
    )
    prompt_sections.append("")

    # Resolve workspace for this task
    ws_name, ws_path = resolve_workspace()
    if ws_name and ws_path:
        obj = objective or ""
        if ws_path not in obj:
            prompt_sections.append(f"## Workspace")
            prompt_sections.append(f"  Name: {ws_name}")
            prompt_sections.append(f"  Path: {ws_path}")
            prompt_sections.append("")

    # 2. Objective
    if objective:
        prompt_sections.append(f"## Objective")
        prompt_sections.append(objective)
        prompt_sections.append("")
    else:
        prompt_sections.append(f"## Objective")
        prompt_sections.append(
            "(No explicit objective provided — continue the current task.)"
        )
        prompt_sections.append("")

    # 3. Task context
    if task_id:
        prompt_sections.append(f"## Task: {task_id}")
        state = get_task_state(task_id)
        prompt_sections.append(f"  Current State: {state.get('state', 'unknown')}")
        prompt_sections.append(f"  Reason: {state.get('reason', '-')}")
        context_files.append(f".agents/tasks/{task_id}.md")

        # Runs
        runs = list_runs(task_id=task_id)
        writer_runs = [r for r in runs if r.get("role") == "writer"]
        reviewer_runs = [r for r in runs if r.get("role") == "reviewer"]
        if writer_runs:
            latest = writer_runs[0]
            parsed = latest.get("parsed_output", {}) or {}
            prompt_sections.append(
                f"  Latest Writer: {latest.get('agent')} — {parsed.get('status', '?')}"
            )
        if reviewer_runs:
            latest = reviewer_runs[0]
            parsed = latest.get("parsed_output", {}) or {}
            prompt_sections.append(
                f"  Latest Reviewer: {latest.get('agent')} — {
                    parsed.get('status', '?')
                }"
            )
        prompt_sections.append("")

    # 4. Guard info
    prompt_sections.append("## Guard: Writer / Reviewer Protocol")
    prompt_sections.append(f"  Current Writer: {guard.get('writer', 'none')}")
    prompt_sections.append(
        f"  Reviewers: {', '.join(guard.get('reviewers', [])) or 'none'}"
    )
    prompt_sections.append(f"  Current Role: {guard.get('role', 'none')}")
    prompt_sections.append(f"  Current Mode: {guard.get('mode', 'none')}")
    prompt_sections.append("")

    # 5. Quality & policy (if task_id)
    if task_id:
        try:
            quality = evaluate_task_quality(task_id)
            prompt_sections.append(f"## Quality Gate")
            prompt_sections.append(
                f"  Ready: {'Yes' if quality.get('ready') else 'No'}"
            )
            if quality.get("blocking_issues"):
                for issue in quality["blocking_issues"]:
                    prompt_sections.append(f"  Blocking: {issue}")
            if quality.get("warnings"):
                for w in quality["warnings"]:
                    prompt_sections.append(f"  Warning: {w}")
            prompt_sections.append("")
        except Exception:
            pass

    # 6. Role-specific instructions
    prompt_sections.append(f"## Instructions for {_AGENT_DISPLAY[target]}")
    if target == "claude":
        prompt_sections.append('- Run as `claude -p "..."` or paste this prompt.')
        prompt_sections.append("- Read .agents/current_task.json first.")
        prompt_sections.append("- Work inside the worktree directory if one is set.")
    elif target == "codex":
        prompt_sections.append("- Open the worktree in VS Code.")
        prompt_sections.append("- Read .agents/current_task.json first.")
        prompt_sections.append("- Use Ctrl+Shift+B to submit when done.")
    elif target == "antigravity":
        prompt_sections.append("- Open the worktree in Antigravity.")
        prompt_sections.append("- Read .agents/current_task.json first.")

    prompt_sections.append("")

    # 7. Safety constraints
    prompt_sections.append("## Safety Constraints")
    for c in _SAFETY_CONSTRAINTS:
        prompt_sections.append(f"- {c.format(task_id=task_id or 'N/A')}")

    prompt = "\n".join(prompt_sections)

    return {
        "target_agent": target,
        "task_id": task_id,
        "prompt": prompt,
        "context_files": context_files,
        "warnings": warnings,
    }
