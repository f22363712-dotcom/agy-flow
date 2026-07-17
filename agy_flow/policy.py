"""Policy Guard v1 — business rules that constrain dispatch and review.

Provides ``can_dispatch`` and ``can_continue`` helpers that check state
machine state, agent identity, and loop counters before allowing an
operation to proceed.
"""

from agy_flow.state_machine import get_task_state, VALID_STATES
from agy_flow.adapter import get_run, list_runs
from agy_flow.errors import AgyFlowError

_MAX_AUTO_LOOP = 3


def _count_recent_runs(task_id, agent=None):
    """Count how many runs exist for *task_id*, optionally filtering by *agent*."""
    runs = list_runs(task_id=task_id)
    if agent:
        runs = [r for r in runs if r.get("agent") == agent]
    return len(runs)


def can_dispatch(task_id, agent, role="writer"):
    """Check whether dispatching *agent* as *role* on *task_id* is allowed.

    Returns
    -------
    dict with keys ``allowed`` (bool), ``reason`` (str), and
    optionally ``warnings`` (list).
    """
    warnings = []

    # 1. Check task state
    state = get_task_state(task_id)
    cur = state.get("state", "planned")

    if cur in ("blocked",):
        return {
            "allowed": False,
            "reason": f"Task '{task_id}' is '{cur}'. Clear the blocked state before dispatching.",
            "warnings": warnings,
        }

    if cur in ("done", "submitted"):
        return {
            "allowed": False,
            "reason": f"Task '{task_id}' is '{cur}'. Cannot dispatch a completed task.",
            "warnings": warnings,
        }

    if cur == "approved":
        warnings.append(
            f"Task is 'approved' — double-check that a new dispatch is intentional."
        )

    # 2. Max auto-loop guard
    if role == "reviewer":
        run_count = _count_recent_runs(task_id)
        if run_count >= _MAX_AUTO_LOOP:
            return {
                "allowed": False,
                "reason": f"Task '{task_id}' has {run_count} runs (max {_MAX_AUTO_LOOP}). "
                f"Too many automatic dispatches; manual intervention required.",
                "warnings": warnings,
            }
        if run_count >= _MAX_AUTO_LOOP - 1:
            warnings.append(
                f"Auto-loop limit approaching: {run_count}/{_MAX_AUTO_LOOP} runs."
            )

    return {
        "allowed": True,
        "reason": "Dispatch permitted by policy.",
        "warnings": warnings,
    }


def can_continue(run_id):
    """Check whether continuing after *run_id* (dispatching a reviewer) is allowed.

    Returns
    -------
    dict with keys ``allowed`` (bool), ``reason`` (str), and
    optionally ``warnings`` (list).
    """
    warnings = []

    record = get_run(run_id)
    if record is None:
        return {
            "allowed": False,
            "reason": f"Run '{run_id}' not found.",
            "warnings": warnings,
        }

    task_id = record.get("task_id", "")
    agent = record.get("agent", "")
    parsed = record.get("parsed_output", {}) or {}
    parsed_status = parsed.get("status", "unknown")
    role = record.get("role", "")

    # 1. Check task state
    state = get_task_state(task_id)
    cur = state.get("state", "planned")

    if cur in ("blocked", "done", "submitted"):
        return {
            "allowed": False,
            "reason": f"Task '{task_id}' is '{cur}'. Cannot continue.",
            "warnings": warnings,
        }

    # 2. Blocked/failed runs don't continue
    if parsed_status in ("blocked", "failed"):
        return {
            "allowed": False,
            "reason": f"Run '{run_id}' has parsed status '{parsed_status}'; cannot continue.",
            "warnings": warnings,
        }

    # 3. Only writer runs can trigger reviewer dispatch
    if role != "writer":
        return {
            "allowed": False,
            "reason": f"Run '{run_id}' has role '{role}'. Only writer runs trigger review.",
            "warnings": warnings,
        }

    # 4. Max auto-loop
    run_count = _count_recent_runs(task_id)
    if run_count >= _MAX_AUTO_LOOP:
        return {
            "allowed": False,
            "reason": f"Task '{task_id}' has {run_count} runs (max {_MAX_AUTO_LOOP}).",
            "warnings": warnings,
        }

    if run_count >= _MAX_AUTO_LOOP - 1:
        warnings.append(
            f"Auto-loop limit approaching: {run_count}/{_MAX_AUTO_LOOP} runs."
        )

    return {
        "allowed": True,
        "reason": "Continue permitted by policy.",
        "warnings": warnings,
    }


def get_policy_info(task_id):
    """Return a full policy summary for *task_id*."""
    state = get_task_state(task_id)
    runs = list_runs(task_id=task_id)
    return {
        "task_id": task_id,
        "state": state.get("state", "unknown"),
        "previous_state": state.get("previous_state"),
        "reason": state.get("reason"),
        "run_count": len(runs),
        "max_auto_loop": _MAX_AUTO_LOOP,
        "auto_loop_remaining": max(0, _MAX_AUTO_LOOP - len(runs)),
        "can_dispatch_new": can_dispatch(task_id, "__check__")["allowed"],
    }
