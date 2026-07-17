"""Review Loop v1 — automatically dispatch a reviewer after a writer run.

The core function ``continue_after_run(run_id, mock)`` inspects a run
record's ``parsed_output`` and decides whether to dispatch a reviewer,
then does so if conditions are met.
"""

import datetime
import json

from agent_relay.adapter import dispatch as adapter_dispatch, get_run, _save_run_record
from agent_relay.errors import AgentRelayError
from agent_relay.router import route_task_by_id
from agent_relay.state_machine import (
    transition_task_state,
    infer_event_from_run,
    set_task_state,
)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pick_reviewer(route, writer_agent):
    """Pick a reviewer candidate from the route that is not the writer.

    Returns agent name or ``None``.
    """
    candidates = route.get("reviewers", [])
    # Avoid the writer themselves
    others = [a for a in candidates if a != writer_agent]
    if others:
        return others[0]
    # Fallback to codex or antigravity
    for fallback in ("codex", "antigravity"):
        if fallback != writer_agent:
            return fallback
    return None


def continue_after_run(run_id, mock=False):
    """Inspect *run_id* and, if appropriate, dispatch a reviewer.

    Parameters
    ----------
    run_id : str
        The run record to inspect.
    mock : bool
        Passed through to the reviewer dispatch.

    Returns
    -------
    dict — loop record with keys:

        ``run_id``, ``task_id``, ``previous_agent``, ``selected_reviewer``,
        ``status`` (``continued`` | ``blocked`` | ``no_action`` | ``failed``),
        ``review_run`` (the dispatch result dict, or {}).
    """
    record = get_run(run_id)
    if record is None:
        raise AgentRelayError(f"Run '{run_id}' not found.")

    task_id = record.get("task_id", "")
    writer_agent = record.get("agent", "")
    parsed = record.get("parsed_output", {})
    parsed_status = parsed.get("status", "unknown")
    next_action = parsed.get("next_action", "manual")

    # Blocked / failed — do not continue
    if parsed_status in ("blocked", "failed"):
        try:
            set_task_state(
                task_id, "blocked", reason=f"Run '{run_id}' status='{parsed_status}'"
            )
        except Exception:
            pass
        return {
            "run_id": run_id,
            "task_id": task_id,
            "previous_agent": writer_agent,
            "selected_reviewer": None,
            "status": "blocked",
            "reason": f"Run status is '{parsed_status}'; no automatic continuation.",
            "next_action": "manual",
            "executed_at": _now(),
            "review_run": {},
        }

    # Determine whether review is warranted
    # If next_action is explicitly "submit" or "none", skip review even if
    # status is completed
    if next_action in ("submit", "none"):
        should_review = False
    else:
        should_review = next_action == "review" or parsed_status in (
            "completed",
            "needs_review",
        )

    if not should_review:
        # If the writer indicated submit/none, transition to submitted
        if next_action == "submit":
            try:
                transition_task_state(task_id, "submitted", run_record=record)
            except Exception:
                pass
        return {
            "run_id": run_id,
            "task_id": task_id,
            "previous_agent": writer_agent,
            "selected_reviewer": None,
            "status": "no_action",
            "reason": f"parsed_output.status='{parsed_status}' next_action='{next_action}' — no review triggered.",
            "next_action": next_action,
            "executed_at": _now(),
            "review_run": {},
        }

    # Transition to needs_review before dispatch
    try:
        transition_task_state(task_id, "needs_review", run_record=record)
    except Exception:
        pass

    # Pick a reviewer
    route = route_task_by_id(task_id)
    reviewer = _pick_reviewer(route, writer_agent)

    if not reviewer:
        try:
            set_task_state(task_id, "blocked", reason="No reviewer candidate available")
        except Exception:
            pass
        return {
            "run_id": run_id,
            "task_id": task_id,
            "previous_agent": writer_agent,
            "selected_reviewer": None,
            "status": "failed",
            "reason": "No reviewer candidate available (all candidates equal to writer or empty).",
            "next_action": "manual",
            "executed_at": _now(),
            "review_run": {},
        }

    # Transition to reviewing
    try:
        transition_task_state(task_id, "reviewing", run_record=record)
    except Exception:
        pass

    # Dispatch the reviewer
    try:
        review_record = adapter_dispatch(
            task_id,
            agent=reviewer,
            mock=mock,
            role="reviewer",
        )
        # Update state based on review result
        event = infer_event_from_run(review_record)
        if event:
            try:
                transition_task_state(task_id, event, run_record=review_record)
            except Exception:
                pass
    except Exception as e:
        try:
            set_task_state(task_id, "blocked", reason=f"Reviewer dispatch failed: {e}")
        except Exception:
            pass
        return {
            "run_id": run_id,
            "task_id": task_id,
            "previous_agent": writer_agent,
            "selected_reviewer": reviewer,
            "status": "failed",
            "reason": f"Reviewer dispatch failed: {e}",
            "next_action": "manual",
            "executed_at": _now(),
            "review_run": {},
        }

    return {
        "run_id": run_id,
        "task_id": task_id,
        "previous_agent": writer_agent,
        "selected_reviewer": reviewer,
        "status": "continued",
        "reason": f"Dispatched reviewer {reviewer} (mock={mock}) after writer {writer_agent}.",
        "next_action": "review",
        "executed_at": _now(),
        "review_run": review_record,
    }
