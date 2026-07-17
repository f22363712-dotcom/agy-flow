"""Capability-Aware Routing v1 — dynamic agent selection based on
connector availability, capabilities, and task classification.

Combines the static rule-based classifier (``plan_task`` from
agent_relay_classify) with live connector probes (``agents_report`` from
agent_relay.connectors) to produce a structured routing plan that adapts to
what is actually installed and configured on the current system.
"""

import json
from agent_relay_classify import classify_task, plan_task, DEFAULT_AGENT_REGISTRY
from agent_relay.config import CONFIG_FILE, get_agent_registry, get_config, TASKS_DIR
from agent_relay.connectors import agents_report, probe_all
from agent_relay.errors import AgentRelayError

# ---------------------------------------------------------------------------
# Built-in agent order preferences
# ---------------------------------------------------------------------------

_WRITE_PRIORITY = ["claude", "antigravity", "codex", "deepseek", "gemini"]
_REVIEW_PRIORITY = ["deepseek", "claude", "antigravity", "codex"]
_HANDOFF_PRIORITY = ["codex", "antigravity", "claude"]


def _get_agents_status():
    """Return a dict ``{name: info, ...}`` from agents_report()."""
    return agents_report()


def _classify_task_type(title):
    """Use the static classifier on *title* and return (task_type, legacy_agent, plan)."""
    plan = plan_task(
        title,
        agent_registry=(
            get_agent_registry(get_config()) if CONFIG_FILE.exists() else None
        ),
    )
    legacy = plan.get("legacy_agent", "claude")
    task_type = plan.get("task_type", "general")
    return task_type, legacy, plan


def _available(agent_status, name):
    """Shortcut: is *name* available?"""
    info = agent_status.get(name, {})
    return info.get("available", False)


def _supports(agent_status, name, feature):
    """Shortcut: does *name* support *feature*?"""
    info = agent_status.get(name, {})
    return info.get(feature, False)


def _kind(agent_status, name):
    return agent_status.get(name, {}).get("kind", "unknown")


def _first_available(priority_list, agent_status, require_feature=None):
    """Return the first agent in *priority_list* that is available.

    If *require_feature* is set (e.g. ``"supports_write"``), the agent
    must also have that capability.
    """
    for name in priority_list:
        if not _available(agent_status, name):
            continue
        if require_feature and not _supports(agent_status, name, require_feature):
            continue
        return name
    return None


def _build_warnings(agent_status, task_type, preferred_agents):
    """Collect capability/availability warnings for the user."""
    warnings = []
    for name in preferred_agents:
        info = agent_status.get(name, {})
        if not info.get("available", False):
            warnings.append(f"{name}: {info.get('reason', 'unavailable')}")
    # Check write availability
    has_write = any(
        _supports(agent_status, name, "supports_write")
        and _available(agent_status, name)
        for name in _WRITE_PRIORITY
    )
    if not has_write and task_type not in ("review", "research"):
        warnings.append(
            "No write-capable agent is currently available. "
            "Install Claude Code CLI or use Codex human-in-loop."
        )
    return warnings


def _gather_reviewers(agent_status, primary):
    """Return agents suitable as reviewers (available + supports_review)."""
    reviewers = []
    for name in _REVIEW_PRIORITY:
        if name == primary:
            continue
        if _available(agent_status, name) and _supports(
            agent_status, name, "supports_review"
        ):
            reviewers.append(name)
    # Always include codex if it supports review
    if "codex" not in reviewers and _available(agent_status, "codex"):
        reviewers.append("codex")
    return reviewers


def route_task(title, body="", labels=None, context=None):
    """Capability-aware routing for a task described by *title*.

    Parameters
    ----------
    title : str
        Task title / natural-language description.
    body : str, optional
        Extended task body.
    labels : list[str], optional
        Task labels.
    context : dict, optional
        Additional context (e.g. ``{"mode": "review"}``).

    Returns
    -------
    dict with keys: ``primary``, ``fallbacks``, ``reviewers``, ``mode``,
    ``reason``, ``capability_warnings``, ``task_type``.
    """
    agent_status = _get_agents_status()
    task_type, legacy_agent, base_plan = _classify_task_type(title)
    labels = labels or []
    forced_mode = (context or {}).get("mode")

    # Determine operating mode
    if forced_mode:
        mode = forced_mode
    elif task_type in ("review", "research", "analysis"):
        mode = "review"
    elif task_type in ("manual", "debug", "config"):
        mode = "handoff"
    elif legacy_agent == "antigravity":
        mode = "write"
    else:
        mode = "write"

    # Select primary agent
    primary = None
    fallbacks = []
    reason_parts = []
    preferred_for_mode = []

    if mode == "review":
        preferred_for_mode = _REVIEW_PRIORITY
        primary = _first_available(preferred_for_mode, agent_status)
        if primary:
            reason_parts.append(
                f"{primary} selected for review ({
                    agent_status.get(primary, {}).get('reason', 'available')
                })"
            )
        else:
            primary = "codex"
            reason_parts.append(
                "No review-capable agent available; falling back to codex human-in-loop"
            )
        # Fallbacks for review
        for name in preferred_for_mode:
            if (
                name != primary
                and _available(agent_status, name)
                and _supports(agent_status, name, "supports_review")
            ):
                fallbacks.append(name)
        if not fallbacks:
            fallbacks.append("codex")

    elif mode == "handoff":
        preferred_for_mode = _HANDOFF_PRIORITY
        primary = _first_available(preferred_for_mode, agent_status)
        if not primary:
            primary = "codex"  # always falls back to human
        reason_parts.append(
            f"{primary} selected for handoff ({
                agent_status.get(primary, {}).get('reason', 'available')
            })"
        )
        fallbacks = [
            n for n in _HANDOFF_PRIORITY if n != primary and _available(agent_status, n)
        ]

    else:  # write mode
        # Start with the classifier's legacy agent
        classifier_agent = base_plan.get("recommended_pipeline", [{}])[0].get(
            "agent", legacy_agent
        )

        if _available(agent_status, classifier_agent) and _supports(
            agent_status, classifier_agent, "supports_write"
        ):
            primary = classifier_agent
            reason_parts.append(f"{primary} preferred by classifier and available")
        else:
            # Fall back to first available write-capable agent
            primary = _first_available(
                _WRITE_PRIORITY, agent_status, require_feature="supports_write"
            )
            if not primary:
                primary = "codex"
                reason_parts.append(
                    "No write-capable agent available; falling back to codex human-in-loop"
                )
            elif primary != classifier_agent:
                reason_parts.append(
                    f"{classifier_agent} not available; routing to {primary} "
                    f"({agent_status.get(primary, {}).get('reason', 'available')})"
                )
            else:
                reason_parts.append(
                    f"{primary} selected ({
                        agent_status.get(primary, {}).get('reason', 'available')
                    })"
                )

        # Write fallbacks: other write-capable agents
        for name in _WRITE_PRIORITY:
            if (
                name != primary
                and _available(agent_status, name)
                and _supports(agent_status, name, "supports_write")
            ):
                fallbacks.append(name)
        if not fallbacks:
            fallbacks.append("codex")

    # Gather reviewers (always from the full review-capable pool)
    reviewers = _gather_reviewers(agent_status, primary)

    # Warnings
    warnings = _build_warnings(
        agent_status, task_type, [primary] + fallbacks + reviewers
    )

    return {
        "primary": primary,
        "fallbacks": fallbacks,
        "reviewers": reviewers,
        "mode": mode,
        "reason": " | ".join(reason_parts),
        "capability_warnings": warnings,
        "task_type": task_type,
        "legacy_agent": legacy_agent,
        "base_plan": {
            "task_type": base_plan.get("task_type"),
            "confidence": base_plan.get("confidence"),
            "recommended_pipeline": base_plan.get("recommended_pipeline", []),
            "selected_agent": base_plan.get(
                "selected_agent", base_plan.get("legacy_agent")
            ),
        },
    }


def route_task_by_id(task_id):
    """Load a task's saved plan from disk and run capability-aware routing on it.

    Falls back to the task title on the board if no plan file is found.
    """
    from agent_relay.tasks import parse_board_rows

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise AgentRelayError(f"Task '{task_id}' not found on the board.")

    title = task["title"]

    # Try to load the saved plan for context
    plan_file = TASKS_DIR / f"{task_id}.plan.json"
    saved_plan = None
    if plan_file.exists():
        try:
            saved_plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    route = route_task(title, context={"mode": None})
    route["task_id"] = task_id
    route["title"] = title
    route["board_status"] = task.get("status", "")
    route["board_agent"] = task.get("agent", "")

    if saved_plan:
        route["saved_plan"] = {
            "has_plan": True,
            "original_agents": saved_plan.get("recommended_pipeline", []),
        }
    else:
        route["saved_plan"] = {"has_plan": False}

    return route


def plan_task_command(args):
    """Legacy CLI entry point for ``agent-relay plan`` (prints raw plan)."""
    if CONFIG_FILE.exists():
        plan = plan_task(args.title, agent_registry=get_agent_registry())
    else:
        plan = plan_task(args.title)
    print(json.dumps(plan, indent=4, ensure_ascii=False))


def route_command(args):
    """CLI entry point for ``agent-relay route``."""
    route = route_task(args.title)
    if args.json:
        print(json.dumps(route, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 60}")
        print(f"  Task: {args.title}")
        print(f"{'=' * 60}")
        print(f"  Primary Agent : {route['primary']}")
        print(f"  Mode          : {route['mode']}")
        print(f"  Fallbacks     : {', '.join(route['fallbacks'])}")
        print(f"  Reviewers     : {', '.join(route['reviewers'])}")
        print(f"  Reason        : {route['reason']}")
        if route["capability_warnings"]:
            print(f"\n  Warnings:")
            for w in route["capability_warnings"]:
                print(f"    ⚠  {w}")
        print(f"{'=' * 60}\n")


def route_task_command(args):
    """CLI entry point for ``agent-relay route-task``."""
    route = route_task_by_id(args.task_id)
    print(json.dumps(route, indent=2, ensure_ascii=False))
