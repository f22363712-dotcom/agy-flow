"""Auto Dispatch Loop v1 — orchestrates capability-aware routing → adapter
dispatch with fallback, recording each attempt as a run record.

The top-level function ``auto_dispatch_task(task_id, ...)`` is the single
entry point for "just figure out what to do and do it."
"""

import datetime
import json

from agy_flow.adapter import dispatch as adapter_dispatch
from agy_flow.errors import AgyFlowError
from agy_flow.router import route_task_by_id
from agy_flow.state_machine import (
    set_task_state,
    transition_task_state,
    infer_event_from_run,
)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def auto_dispatch_task(task_id, dry_run=False, mock=False):
    """Capability-aware auto dispatch for *task_id*.

    Parameters
    ----------
    task_id : str
    dry_run : bool
        If True, only compute the route and show what *would* be dispatched
        without actually calling any adapter.
    mock : bool
        Passed through to adapters that support it (e.g. DeepSeek).

    Returns
    -------
    dict — orchestration record with keys:

        ``task_id``, ``route``, ``selected_agent``, ``attempts``,
        ``status`` (``success`` | ``failed`` | ``dry_run``), ``reason``.
    """
    route = route_task_by_id(task_id)
    mode = route.get("mode", "write")

    # Determine the candidate list: primary + fallbacks
    candidates = [route["primary"]] + route.get("fallbacks", [])
    # Deduplicate while preserving order
    seen = set()
    candidates_unique = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            candidates_unique.append(c)

    # Map mode → role
    if mode == "review":
        role = "reviewer"
    elif mode == "handoff":
        role = "writer"
    else:
        role = "writer"

    attempts = []

    if dry_run:
        return {
            "task_id": task_id,
            "route": route,
            "selected_agent": candidates_unique[0] if candidates_unique else None,
            "attempts": [
                {
                    "agent": agent,
                    "role": role,
                    "status": "dry_run",
                    "reason": "would dispatch (dry-run mode)",
                }
                for agent in candidates_unique
            ],
            "status": "dry_run",
            "reason": f"Dry run: would dispatch to {candidates_unique[0] if candidates_unique else 'none'} "
            f"with fallbacks {candidates_unique[1:] if len(candidates_unique) > 1 else []}",
            "executed_at": _now(),
        }

    last_error = None
    for agent in candidates_unique:
        try:
            record = adapter_dispatch(task_id, agent, mock=mock, role=role)
            attempt = {
                "agent": agent,
                "role": role,
                "status": record.get("status", "unknown"),
                "run_id": record.get("run_id"),
                "reason": record.get("error")
                or record.get("result", {}).get("summary", ""),
            }
            attempts.append(attempt)

            # success/handoff → stop
            if record.get("status") in ("success", "handoff"):
                # Update task state
                event = infer_event_from_run(record)
                if event:
                    try:
                        transition_task_state(task_id, event, run_record=record)
                    except Exception:
                        pass
                return {
                    "task_id": task_id,
                    "route": route,
                    "selected_agent": agent,
                    "attempts": attempts,
                    "status": "success",
                    "reason": f"Dispatched to {agent} ({record.get('status')})",
                    "executed_at": _now(),
                }

            last_error = (
                record.get("error")
                or f"dispatch returned status {record.get('status')}"
            )

        except AgyFlowError as e:
            attempts.append(
                {
                    "agent": agent,
                    "role": role,
                    "status": "error",
                    "reason": str(e),
                }
            )
            last_error = str(e)
        except Exception as e:
            attempts.append(
                {
                    "agent": agent,
                    "role": role,
                    "status": "error",
                    "reason": f"Unexpected error: {e}",
                }
            )
            last_error = str(e)

    # All attempts exhausted — update state to blocked
    try:
        set_task_state(
            task_id, "blocked", reason=f"All candidates exhausted: {last_error}"
        )
    except Exception:
        pass

    return {
        "task_id": task_id,
        "route": route,
        "selected_agent": None,
        "attempts": attempts,
        "status": "failed",
        "reason": f"All candidates exhausted: {last_error}",
        "executed_at": _now(),
    }


def auto_command(args):
    """CLI entry point for ``agy-flow auto``."""
    import json
    import sys

    try:
        result = auto_dispatch_task(
            args.task_id,
            dry_run=getattr(args, "dry_run", False),
            mock=getattr(args, "mock", False),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Auto-dispatch failed: {e}")
        sys.exit(1)
