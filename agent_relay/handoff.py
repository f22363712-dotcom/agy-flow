import datetime
import json
import sys
from pathlib import Path
import agent_relay.config
from agent_relay.git_ops import run_cmd


def canonical_assignment_agent(agent):
    """Return the guard-file spelling expected by each agent integration."""
    normalized = agent.strip().lower()
    mapping = {
        "codex": "Codex",
        "antigravity": "antigravity",
        "claude": "claude",
        "deepseek": "deepseek",
    }
    return mapping.get(normalized, normalized)


def load_task_plan(task_id):
    """Loads a task routing plan if it exists."""
    plan_file = agent_relay.config.TASKS_DIR / f"{task_id}.plan.json"
    if not plan_file.exists():
        return None
    try:
        return json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: Failed to read routing plan {plan_file}: {e}")
        return None


def get_handoff_steps(task, config):
    """Returns worktree-capable handoff steps, preferring the saved plan."""
    plan = load_task_plan(task["id"])
    selected_agents = [a.strip() for a in task["agent"].split("->") if a.strip()]
    selected_set = set(selected_agents)

    if plan and plan.get("recommended_pipeline"):
        steps = []
        for step in plan["recommended_pipeline"]:
            agent = step.get("agent")
            agent_info = config.get("agents", {}).get(agent, {})
            is_worktree_agent = bool(
                agent_info.get("guide_file") or agent_info.get("interactive")
            )
            is_selected_agent = not selected_set or agent in selected_set
            if agent and is_worktree_agent and is_selected_agent:
                steps.append(step)
        if steps:
            return steps, plan

    fallback_steps = [
        {
            "agent": agent,
            "role": "worker",
            "purpose": "execute assigned task work",
        }
        for agent in selected_agents
    ]
    return fallback_steps, plan


def find_next_handoff_step(handoff_steps, active_agent):
    """Finds the next handoff step after the active agent."""
    agents = [step.get("agent") for step in handoff_steps]
    if len(agents) > 1 and active_agent in agents:
        idx = agents.index(active_agent)
        if idx + 1 < len(handoff_steps):
            return handoff_steps[idx + 1]
    return None


def _normalize_reviewers(reviewers):
    if reviewers is None:
        return []
    if isinstance(reviewers, str):
        reviewers = [reviewers]
    normalized = []
    for reviewer in reviewers:
        canonical = canonical_assignment_agent(str(reviewer))
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def assign_current_task_agent(
    agent,
    task_id=None,
    role="writer",
    reviewers=None,
    mode="handoff",
):
    """Update .agents/current_task.json with writer/reviewer guard metadata.

    The legacy ``agent`` field is intentionally preserved for older agent
    guard instructions that only understand a single active agent.
    """
    agent_relay.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    current_task_path = agent_relay.config.AGENTS_DIR / "current_task.json"
    metadata = {}
    if current_task_path.exists():
        try:
            metadata = json.loads(current_task_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    canonical_agent = canonical_assignment_agent(agent)
    existing_reviewers = _normalize_reviewers(metadata.get("reviewers", []))
    incoming_reviewers = _normalize_reviewers(reviewers)

    if task_id:
        metadata["task_id"] = task_id
    if role == "reviewer":
        writer = metadata.get("writer") or metadata.get("agent") or canonical_agent
        metadata["writer"] = canonical_assignment_agent(writer)
        for reviewer in [canonical_agent] + incoming_reviewers:
            if reviewer not in existing_reviewers:
                existing_reviewers.append(reviewer)
        # Keep legacy guard compatible with the reviewer taking over this turn.
        metadata["agent"] = canonical_agent
    else:
        metadata["writer"] = canonical_agent
        for reviewer in incoming_reviewers:
            if reviewer not in existing_reviewers:
                existing_reviewers.append(reviewer)
        metadata["agent"] = canonical_agent

    metadata["reviewers"] = existing_reviewers
    metadata["mode"] = mode
    metadata["role"] = role
    metadata["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_task_path.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    return current_task_path, metadata


def assign_command(args):
    """Assign the current workspace guard file to another agent."""
    path, metadata = assign_current_task_agent(
        args.agent,
        task_id=args.task_id,
        role=args.role,
        reviewers=args.reviewer,
        mode=args.mode,
    )
    print(f"Updated routing metadata: {path}")
    print(json.dumps(metadata, indent=4, ensure_ascii=False))


def parse_board_rows_fallback():
    if not agent_relay.config.BOARD_FILE.exists():
        return []
    with open(agent_relay.config.BOARD_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tasks = []
    for line in lines:
        if "|" in line:
            if "---" in line or "Task ID" in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                tasks.append(
                    {
                        "id": parts[0],
                        "title": parts[1],
                        "agent": parts[2],
                        "status": parts[3],
                        "branch": parts[4] if len(parts) > 4 else "",
                        "worktree": parts[5] if len(parts) > 5 else "",
                    }
                )
    return tasks


def handoff_plan_command(args):
    """Print the worktree-capable handoff steps for a task."""
    config = get_config()
    tasks = parse_board_rows_fallback()
    task = next((t for t in tasks if t["id"] == args.task_id), None)
    if not task:
        print(f"Error: Task '{args.task_id}' not found.")
        sys.exit(1)

    handoff_steps, route_plan = get_handoff_steps(task, config)
    active_agent = handoff_steps[0]["agent"] if handoff_steps else task["agent"]
    worktree_path = Path(task.get("worktree", ""))
    current_task_path = worktree_path / ".agents" / "current_task.json"
    if current_task_path.exists():
        try:
            task_meta = json.loads(current_task_path.read_text(encoding="utf-8"))
            active_agent = task_meta.get("agent", active_agent)
        except Exception:
            pass

    next_step = find_next_handoff_step(handoff_steps, active_agent)
    result = {
        "task_id": args.task_id,
        "active_agent": active_agent,
        "handoff_steps": handoff_steps,
        "next_step": next_step,
        "source": "plan" if route_plan else "board",
    }
    print(json.dumps(result, indent=4, ensure_ascii=False))


def update_module_paths():
    global AGENTS_DIR, TASKS_DIR, BOARD_FILE, PROJECT_ROOT
    import agent_relay.config

    AGENTS_DIR = agent_relay.config.AGENTS_DIR
    TASKS_DIR = agent_relay.config.TASKS_DIR
    BOARD_FILE = agent_relay.config.BOARD_FILE
    PROJECT_ROOT = agent_relay.config.PROJECT_ROOT


# ---------------------------------------------------------------------------
# Lease writer & whoami
# ---------------------------------------------------------------------------


def lease_writer(agent, task_id=None, reason=None, force=False):
    """Lease the writer slot to *agent*.

    Behaviour
    ---------
    1. If the current writer is already *agent* → ``unchanged``.
    2. If the current slot is free / reviewer or handoff with no blocking
       run → ``leased``.
    3. If another agent holds the writer and ``force=False`` → ``conflict``.
    4. If ``force=True`` → ``forced`` (overwrite).

    Returns
    -------
    dict with keys ``status``, ``writer``, ``previous_writer``,
    ``reviewers`` (list), ``reason``.
    """
    agent_relay.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    guard_path = agent_relay.config.AGENTS_DIR / "current_task.json"
    current = {}
    if guard_path.exists():
        try:
            current = json.loads(guard_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    canonical = canonical_assignment_agent(agent)
    current_writer = current.get("writer")
    current_reviewers = current.get("reviewers", [])

    # 1. Already the writer
    if current_writer and current_writer == canonical:
        return build_lease_result(
            "unchanged", canonical, current_writer, current_reviewers, reason
        )

    # 2. Free slot / reviewer / handoff mode
    if not force:
        if not current_writer:
            pass  # free slot → lease
        elif current.get("role") in ("reviewer",) or current.get("mode") in ("review",):
            pass  # reviewer held → can take writer
        else:
            # 3. Conflict
            suggested = f"agent-relay lease {agent.lower()} --force"
            return {
                "status": "conflict",
                "writer": canonical,
                "previous_writer": current_writer,
                "reviewers": current_reviewers,
                "reason": reason or f"Writer slot held by {current_writer}",
                "suggested_command": suggested,
            }

    # Build new guard
    metadata = dict(current)
    metadata["writer"] = canonical
    metadata["agent"] = canonical
    metadata["role"] = "writer"
    metadata["mode"] = current.get("mode", "handoff")
    if task_id:
        metadata["task_id"] = task_id
    metadata["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Preserve reviewers
    if "reviewers" not in metadata:
        metadata["reviewers"] = []

    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    status = "forced" if force else "leased"
    return build_lease_result(
        status, canonical, current_writer, current_reviewers, reason
    )


def build_lease_result(status, writer, previous_writer, reviewers, reason=None):
    return {
        "status": status,
        "writer": writer,
        "previous_writer": previous_writer,
        "reviewers": reviewers,
        "reason": reason or "",
    }


def whoami():
    """Return the current writer/reviewer guard metadata.

    Returns
    -------
    dict with keys ``writer``, ``reviewers``, ``role``, ``mode``,
    ``agent`` (legacy), ``task_id``, ``timestamp``, ``can_write``,
    ``can_review``.
    """
    guard_path = agent_relay.config.AGENTS_DIR / "current_task.json"
    if not guard_path.exists():
        return {
            "writer": None,
            "reviewers": [],
            "role": None,
            "mode": None,
            "agent": None,
            "task_id": None,
            "can_write": False,
            "can_review": False,
            "timestamp": None,
        }

    try:
        metadata = json.loads(guard_path.read_text(encoding="utf-8"))
    except Exception:
        return {"writer": None, "reviewers": [], "error": "Failed to read guard"}

    writer = metadata.get("writer")
    role = metadata.get("role", "")
    reviewers = metadata.get("reviewers", [])
    agent = metadata.get("agent")

    return {
        "writer": writer,
        "reviewers": reviewers,
        "role": role,
        "mode": metadata.get("mode"),
        "agent": agent,
        "task_id": metadata.get("task_id"),
        "timestamp": metadata.get("timestamp"),
        "can_write": writer is not None and role == "writer",
        "can_review": agent in reviewers if agent else False,
    }


def build_handoff_mcp_context(
    target_agent: str,
    task_id: str,
    objective: str | None = None,
) -> dict:
    """Thin wrapper around ``prompt_pack.build_handoff_prompt``.

    Uses a local import to avoid circular dependencies at module level.
    Returns the same dict as ``build_handoff_prompt()``.
    """
    from agent_relay.prompt_pack import build_handoff_prompt

    return build_handoff_prompt(
        target_agent=target_agent,
        task_id=task_id,
        objective=objective,
        include_context=True,
    )
