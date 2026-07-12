import datetime
import json
import sys
from pathlib import Path
import agy_flow.config
from agy_flow.git_ops import run_cmd

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
    plan_file = agy_flow.config.TASKS_DIR / f"{task_id}.plan.json"
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
            is_worktree_agent = bool(agent_info.get("guide_file") or agent_info.get("interactive"))
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

def assign_current_task_agent(agent, task_id=None):
    """Update .agents/current_task.json so another agent can take over."""
    agy_flow.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    current_task_path = agy_flow.config.AGENTS_DIR / "current_task.json"
    metadata = {}
    if current_task_path.exists():
        try:
            metadata = json.loads(current_task_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    if task_id:
        metadata["task_id"] = task_id
    metadata["agent"] = canonical_assignment_agent(agent)
    metadata["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_task_path.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    return current_task_path, metadata

def assign_command(args):
    """Assign the current workspace guard file to another agent."""
    path, metadata = assign_current_task_agent(args.agent, task_id=args.task_id)
    print(f"Updated routing metadata: {path}")
    print(json.dumps(metadata, indent=4, ensure_ascii=False))

def parse_board_rows_fallback():
    if not agy_flow.config.BOARD_FILE.exists():
        return []
    with open(agy_flow.config.BOARD_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tasks = []
    for line in lines:
        if "|" in line:
            if "---" in line or "Task ID" in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                tasks.append({
                    "id": parts[0],
                    "title": parts[1],
                    "agent": parts[2],
                    "status": parts[3],
                    "branch": parts[4] if len(parts) > 4 else "",
                    "worktree": parts[5] if len(parts) > 5 else "",
                })
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
    import agy_flow.config
    AGENTS_DIR = agy_flow.config.AGENTS_DIR
    TASKS_DIR = agy_flow.config.TASKS_DIR
    BOARD_FILE = agy_flow.config.BOARD_FILE
    PROJECT_ROOT = agy_flow.config.PROJECT_ROOT
