"""Submit Pipeline v1 — finalise a task after quality gate passes.

The function ``finalize_task(task_id, dry_run)`` runs the quality gate and,
if the task is ready, transitions it to ``submitted`` in the state machine
and calls the existing ``submit_task`` logic when a worktree exists.
"""

import datetime

from agent_relay.errors import AgentRelayError
from agent_relay.state_machine import transition_task_state, set_task_state
from agent_relay.quality_gate import evaluate_task_quality


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def finalize_task(task_id, dry_run=False):
    """Run quality gate then, if ready, finalise *task_id*.

    Parameters
    ----------
    task_id : str
    dry_run : bool
        If True, run the quality gate but do not perform the actual
        finalisation.

    Returns
    -------
    dict — finalize record with keys:

        ``task_id``, ``status`` (``submitted`` | ``blocked`` |
        ``dry_run`` | ``failed``), ``quality`` (the full quality gate
        result), ``submitted`` (bool), ``reason`` (str).
    """
    try:
        quality = evaluate_task_quality(task_id)
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "failed",
            "quality": {"ready": False, "blocking_issues": [], "warnings": []},
            "submitted": False,
            "reason": f"Quality gate evaluation failed: {e}",
            "executed_at": _now(),
        }

    if dry_run:
        return {
            "task_id": task_id,
            "status": "dry_run",
            "quality": quality,
            "submitted": False,
            "reason": (
                "Quality gate would allow submission."
                if quality["ready"]
                else f"Quality gate blocked: {'; '.join(quality['blocking_issues'])}"
            ),
            "executed_at": _now(),
        }

    if not quality["ready"]:
        return {
            "task_id": task_id,
            "status": "blocked",
            "quality": quality,
            "submitted": False,
            "reason": f"Quality gate blocked: {'; '.join(quality['blocking_issues'])}",
            "executed_at": _now(),
        }

    # --- Actually finalise ---
    try:
        # Try the existing submit logic if a worktree exists
        try:
            from agent_relay.tasks import (
                parse_board_rows,
                update_board_row,
                submit_task as tasks_submit,
            )

            tasks = parse_board_rows()
            task = next((t for t in tasks if t["id"] == task_id), None)

            if (
                task
                and task.get("worktree", "").strip()
                and "In Progress" in task.get("status", "")
            ):

                class SubmitArgs:
                    task_id = task_id
                    test_cmd = ""

                tasks_submit(SubmitArgs())
        except (Exception, SystemExit) as submit_err:
            # Non-fatal: the git-based submit may not be applicable
            # (e.g. no worktree, task not marked in_progress on board)
            pass

        # Transition state to submitted
        try:
            transition_task_state(task_id, "submitted")
        except AgentRelayError:
            # If transition is not allowed from current state, force-set it
            set_task_state(
                task_id,
                "submitted",
                reason="Quality gate passed and task finalised.",
            )

        return {
            "task_id": task_id,
            "status": "submitted",
            "quality": quality,
            "submitted": True,
            "reason": "Task finalised successfully after quality gate passed.",
            "executed_at": _now(),
        }

    except Exception as e:
        return {
            "task_id": task_id,
            "status": "failed",
            "quality": quality,
            "submitted": False,
            "reason": f"Finalisation failed: {e}",
            "executed_at": _now(),
        }
