"""Task State Machine v1 — track and transition task lifecycle states.

Each task has a state persisted to ``.agents/tasks/task-xxx.state.json``.
The state machine enforces legal transitions and provides a single source
of truth for what phase of the lifecycle a task is in.
"""

import datetime
import json
from pathlib import Path

import agy_flow.config
from agy_flow.errors import AgyFlowError

# ---------------------------------------------------------------------------
# Valid states
# ---------------------------------------------------------------------------

VALID_STATES = frozenset(
    {
        "planned",  # created / planned, not yet dispatched
        "dispatched",  # writer dispatched (CLI / adapter)
        "in_progress",  # human-in-loop handoff done, work expected
        "needs_review",  # writer completed, waiting for reviewer
        "reviewing",  # reviewer dispatched
        "revision_requested",  # reviewer requested changes
        "approved",  # reviewer approved
        "blocked",  # run returned blocked/failed
        "done",  # merged / completed
        "submitted",  # submitted via agy-flow submit
    }
)

# ---- Legal transitions ----

_TRANSITIONS = {
    "planned": {"dispatched", "in_progress", "blocked"},
    "dispatched": {"in_progress", "needs_review", "blocked", "dispatched"},
    "in_progress": {"needs_review", "blocked", "submitted"},
    "needs_review": {"reviewing", "blocked"},
    "reviewing": {"approved", "revision_requested", "needs_review", "blocked"},
    "revision_requested": {"dispatched", "in_progress", "blocked"},
    "approved": {"done", "submitted", "blocked"},
    "blocked": {"planned", "dispatched", "in_progress", "done", "submitted"},
    "done": set(),
    "submitted": {"done"},
}


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------


def _get_state_file(task_id):
    return agy_flow.config.TASKS_DIR / f"{task_id}.state.json"


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_DEFAULT_STATE = {
    "state": "planned",
    "previous_state": None,
    "reason": "Task created",
    "source_run_id": None,
    "updated_at": None,
    "history": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_task_state(task_id):
    """Return the current state dict for *task_id*, or the default if none."""
    state_file = _get_state_file(task_id)
    if not state_file.exists():
        state = dict(_DEFAULT_STATE)
        state["updated_at"] = _now()
        return state
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_STATE, updated_at=_now())


def set_task_state(task_id, state, reason=None, source_run_id=None):
    """Set *task_id* to *state* (no transition validation).

    Returns the updated state dict.
    """
    if state not in VALID_STATES:
        raise AgyFlowError(f"Invalid state '{state}'. Valid: {sorted(VALID_STATES)}")

    current = get_task_state(task_id)
    previous = current.get("state")

    history_entry = {
        "from": previous,
        "to": state,
        "reason": reason or f"Manual set to {state}",
        "source_run_id": source_run_id,
        "timestamp": _now(),
    }

    new_state = {
        "state": state,
        "previous_state": previous,
        "reason": reason or f"Set to {state}",
        "source_run_id": source_run_id,
        "updated_at": _now(),
        "history": current.get("history", []) + [history_entry],
    }

    state_file = _get_state_file(task_id)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(new_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return new_state


def transition_task_state(task_id, event, run_record=None):
    """Transition *task_id* state based on *event*.

    Parameters
    ----------
    task_id : str
    event : str
        One of the events described in the transition table.
    run_record : dict, optional
        The run record that triggered this transition (used to set
        ``source_run_id``).

    Returns
    -------
    dict — the new state, or the current state if no transition was needed.

    Raises
    ------
    AgyFlowError
        If the transition is not allowed.
    """
    current = get_task_state(task_id)
    cur = current["state"]

    allowed = _TRANSITIONS.get(cur, set())
    if event not in allowed:
        raise AgyFlowError(
            f"Cannot transition task '{task_id}' from '{cur}' to '{event}'. "
            f"Allowed from '{cur}': {sorted(allowed) or '(none)'}"
        )

    source_id = None
    if run_record:
        source_id = run_record.get("run_id")

    # Compute a human-readable reason
    reason_map = {
        "dispatched": "Writer dispatched",
        "in_progress": "Agent started work (handoff)",
        "needs_review": "Writer completed, review requested",
        "reviewing": "Reviewer dispatched",
        "approved": "Reviewer approved",
        "revision_requested": "Reviewer requested revision",
        "blocked": "Run blocked or failed",
        "done": "Task completed and merged",
        "submitted": "Task submitted via CLI",
    }
    reason = reason_map.get(event, f"Transition to {event}")

    return set_task_state(task_id, event, reason=reason, source_run_id=source_id)


def infer_event_from_run(run_record):
    """Given a dispatch run record, infer the state machine event.

    Returns a string event name or ``None`` if no transition is warranted.
    """
    if not run_record:
        return None

    status = run_record.get("status", "")
    role = run_record.get("role", "")
    parsed = run_record.get("parsed_output", {}) or {}
    parsed_status = parsed.get("status", "unknown")
    next_action = parsed.get("next_action", "manual")

    # Failed/unavailable → blocked
    if status in ("unavailable", "error", "timeout"):
        return "blocked"
    if parsed_status in ("blocked", "failed"):
        return "blocked"

    # Handoff → in_progress
    if status == "handoff":
        return "in_progress"

    # Writer completed with review request → needs_review
    if role == "writer" and parsed_status in ("completed", "needs_review"):
        if next_action == "submit":
            return "submitted"
        return "needs_review"

    # Reviewer approved → approved
    if role == "reviewer":
        if status == "success":
            if next_action == "revise":
                return "revision_requested"
            if next_action in ("submit", "none"):
                return "approved"
            return "approved"  # default reviewer success = approved
        if status in ("unavailable", "error"):
            return "blocked"

    # Default: dispatched
    if status == "success":
        return "dispatched"

    return None
