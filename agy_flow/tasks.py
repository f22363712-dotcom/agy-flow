import os
import sys
import json
import datetime
import subprocess
from pathlib import Path
from agy_flow.errors import AgyFlowError
from agy_flow.git_ops import run_cmd
from agy_flow.config import (
    BOARD_FILE,
    TASKS_DIR,
    PROJECT_ROOT,
    AGENTS_DIR,
    TEMPLATES_DIR,
    LOGS_DIR,
    CONFIG_FILE,
    COSTS_FILE,
    DEFAULT_BOARD_TEMPLATE,
    DEFAULT_TASK_TEMPLATE,
    DEFAULT_CONFIG,
    PRICING,
    get_config,
    get_agent_registry,
    load_costs,
    save_costs,
)
from agy_flow_classify import plan_task
from agy_flow.handoff import (
    assign_current_task_agent,
    canonical_assignment_agent,
    get_handoff_steps,
    find_next_handoff_step,
)

def load_board():
    """Loads the board.md file lines."""
    import agy_flow.config
    board_file = agy_flow.config.BOARD_FILE
    if not board_file.exists():
        print(
            f"Error: Board file not found at {board_file}. Run 'agy-flow init' first."
        )
        sys.exit(1)
    with open(board_file, "r", encoding="utf-8") as f:
        return f.readlines()

def save_board(lines):
    """Saves lines back to board.md."""
    import agy_flow.config
    board_file = agy_flow.config.BOARD_FILE
    with open(board_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

def format_plan_summary(plan):
    """Formats a structured plan for human-readable task specs."""
    pipeline_lines = []
    for idx, step in enumerate(plan.get("recommended_pipeline", []), start=1):
        pipeline_lines.append(
            f"{idx}. {step.get('agent')} ({step.get('role')}): "
            f"{step.get('purpose')}"
        )

    pipeline_text = "\n".join(pipeline_lines) if pipeline_lines else "None"
    policy = plan.get("policy", {})
    return f"""## Routing Plan
- **Task Type**: {plan.get("task_type")}
- **Confidence**: {plan.get("confidence")}
- **Selected Agent**: {plan.get("selected_agent", plan.get("legacy_agent"))}
- **Selection Source**: {plan.get("selection_source", "plan")}
- **Strategy**: {policy.get("strategy")}
- **Budget Bias**: {policy.get("budget_bias")}

### Recommended Pipeline
{pipeline_text}
"""

def estimate_and_log_cost(task_id, agent, manual_input=0, manual_output=0, input_prompt=""):
    """Calculates/logs API token pricing and appends cost record to costs.json."""
    pricing = PRICING.get(agent, {"input": 0.0, "output": 0.0})
    input_tokens = manual_input
    output_tokens = manual_output

    if not manual_input and input_prompt:
        input_tokens = len(input_prompt.split())

    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])

    costs = load_costs()
    task_costs = costs["tasks"].get(task_id, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0})
    task_costs["input_tokens"] += input_tokens
    task_costs["output_tokens"] += output_tokens
    task_costs["cost"] += cost
    costs["tasks"][task_id] = task_costs
    save_costs(costs)
    return cost, task_costs

def parse_board_rows():
    """Parses rows inside board.md to return detailed task dictionaries."""
    lines = load_board()
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

def update_board_row(task_id, status, branch="", worktree=""):
    """Updates a single row matching task_id inside board.md with the given fields."""
    lines = load_board()
    updated = False
    for i, line in enumerate(lines):
        if "|" in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if parts and parts[0] == task_id:
                new_branch = branch if branch else (parts[4] if len(parts) > 4 else "")
                new_worktree = worktree if worktree else (parts[5] if len(parts) > 5 else "")
                lines[i] = f"| {task_id} | {parts[1]} | {parts[2]} | {status} | {new_branch} | {new_worktree} |\n"
                updated = True
                break
    if not updated:
        print(f"Warning: Task '{task_id}' not found on the board. No changes made.")
    save_board(lines)

def check_inside_project(command):
    """Verify that we are executing from within an initialized agy-flow repository."""
    if not CONFIG_FILE.exists():
        print(
            f"Error: Not inside an initialized agy-flow repository. CONFIG_FILE: {CONFIG_FILE}"
        )
        print("Please run 'agy-flow init' in the project directory first.")
        sys.exit(1)

def init_project(args):
    """Initializes the agy-flow structure in the current working directory."""
    global PROJECT_ROOT, AGENTS_DIR, TASKS_DIR, TEMPLATES_DIR, LOGS_DIR, CONFIG_FILE, BOARD_FILE, COSTS_FILE

    print(f"Initializing agy-flow collaboration framework in {PROJECT_ROOT}...")

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        config_data = DEFAULT_CONFIG.copy()
        config_data["project_name"] = PROJECT_ROOT.name
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        print(f"Created config file: {CONFIG_FILE}")

    if not BOARD_FILE.exists():
        with open(BOARD_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_BOARD_TEMPLATE)
        print(f"Created task board: {BOARD_FILE}")

    template_path = TEMPLATES_DIR / "task_template.md"
    if not template_path.exists():
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_TASK_TEMPLATE)
        print(f"Created task template: {template_path}")

    load_costs()
    print(f"Created cost statistics registry: {COSTS_FILE}")

    code, stdout, stderr = run_cmd(["git", "status"], cwd=str(PROJECT_ROOT))
    if code != 0:
        print("Git repository not initialized. Initializing git...")
        run_cmd(["git", "init"], cwd=str(PROJECT_ROOT))
    else:
        print("Git repository already initialized.")

    config = get_config()
    worktrees_dir = Path(config["worktrees_dir"])
    if not worktrees_dir.is_absolute():
        worktrees_dir = (PROJECT_ROOT / worktrees_dir).resolve()

    gitignore = PROJECT_ROOT / ".gitignore"
    new_ignores = [".agents/current_task.json", "__pycache__/", "*.pyc"]
    try:
        rel_path = worktrees_dir.relative_to(PROJECT_ROOT)
        new_ignores.append(f"{rel_path}/")
    except ValueError:
        pass

    ignore_content = ""
    if gitignore.exists():
        ignore_content = gitignore.read_text(encoding="utf-8")

    appends = []
    for ig in new_ignores:
        if ig not in ignore_content:
            appends.append(ig)

    if appends:
        with open(gitignore, "a" if gitignore.exists() else "w", encoding="utf-8") as f:
            if gitignore.exists() and not ignore_content.endswith("\n"):
                f.write("\n")
            for ig in appends:
                f.write(f"{ig}\n")
        print(f"Updated .gitignore with rules: {', '.join(appends)}")
    else:
        print(".gitignore is already up-to-date.")

    # Synchronize back path updates
    import agy_flow.config
    agy_flow.config.PROJECT_ROOT = PROJECT_ROOT
    agy_flow.config.AGENTS_DIR = AGENTS_DIR
    agy_flow.config.TASKS_DIR = TASKS_DIR
    agy_flow.config.TEMPLATES_DIR = TEMPLATES_DIR
    agy_flow.config.LOGS_DIR = LOGS_DIR
    agy_flow.config.CONFIG_FILE = CONFIG_FILE
    agy_flow.config.BOARD_FILE = BOARD_FILE
    agy_flow.config.COSTS_FILE = COSTS_FILE

    print("Initialization completed successfully.")

def create_task(args):
    """Creates a new task file and registers it in the board."""
    check_inside_project("create")
    config = get_config()
    title = args.title
    route_plan = plan_task(title, agent_registry=get_agent_registry(config))

    if args.agent is None:
        agent = "->".join(route_plan.get("recommended_pipeline", ["claude"]))
    else:
        agent = args.agent

    tasks = parse_board_rows()
    ids = []
    for t in tasks:
        try:
            ids.append(int(t["id"].split("-")[1]))
        except (ValueError, IndexError):
            pass
    next_id = max(ids) + 1 if ids else 1
    task_id = f"task-{next_id:03d}"

    task_file_name = f"{task_id}.md"
    task_file = TASKS_DIR / task_file_name
    
    desc_content = args.desc if hasattr(args, 'desc') and args.desc else "Not provided."
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read template if exists
    template_path = TEMPLATES_DIR / "task_template.md"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
        task_content = template.format(
            task_id=task_id,
            title=title,
            agent=agent,
            status="Todo",
            created_time=now_str
        )
    else:
        task_content = f"# Task: {task_id} - {title}\n\n## Metadata\n- **ID**: {task_id}\n- **Assigned Agent**: {agent}\n- **Created**: {now_str}\n"

    # Append routing plan details
    plan_text = format_plan_summary(route_plan)
    task_content += "\n" + plan_text

    task_file.write_text(task_content, encoding="utf-8")
    print(f"Created task specification file: {task_file}")

    plan_file = TASKS_DIR / f"{task_id}.plan.json"
    plan_file.write_text(json.dumps(route_plan, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"Created structured routing plan: {plan_file}")

    lines = load_board()
    lines.append(f"| {task_id} | {title} | {agent} | Todo | | |\n")
    save_board(lines)
    print(f"Registered task '{task_id}' inside board.md.")

    code, stdout, stderr = run_cmd(["git", "add", str(task_file.relative_to(PROJECT_ROOT)), str(plan_file.relative_to(PROJECT_ROOT)), str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    if code != 0:
        raise AgyFlowError(f"Git add failed in create_task: {stderr}")

    code, stdout, stderr = run_cmd(["git", "commit", "-m", f"docs(task): create {task_id} - {title}"])
    if code != 0:
        raise AgyFlowError(f"Git commit failed in create_task: {stderr}")

    print(f"\nTask {task_id} successfully created and committed in Git!")
    print(f"To start working on this task, run: agy-flow start {task_id}\n")

    return {
        "status": "created",
        "task_id": task_id,
        "task_file": str(task_file),
        "plan_file": str(plan_file),
        "agent": agent,
    }

def start_task(args):
    """Starts a task by setting up its local worktree environment."""
    check_inside_project("start")
    config = get_config()
    task_id = args.task_id

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise AgyFlowError(f"Task '{task_id}' not found.")

    if task["status"] != "Todo":
        raise AgyFlowError(f"Task '{task_id}' is already in status '{task['status']}'")

    handoff_steps, _ = get_handoff_steps(task, config)
    agent = handoff_steps[0]["agent"] if handoff_steps else task["agent"]

    branch_name = f"task-{task_id}"
    worktree_parent = Path(config["worktrees_dir"])
    if not worktree_parent.is_absolute():
        worktree_parent = (PROJECT_ROOT / worktree_parent).resolve()

    worktree_path = worktree_parent / task_id

    print(f"Setting up branch '{branch_name}' and worktree at '{worktree_path}'...")

    code, stdout, stderr = run_cmd(["git", "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"])
    if code != 0:
        raise AgyFlowError(f"Failed to create git worktree: {stderr}")

    update_board_row(task_id, "In Progress", branch=branch_name, worktree=str(worktree_path))

    guide_content = ""
    agent_info = config.get("agents", {}).get(agent, {})
    guide_file = agent_info.get("guide_file")
    if guide_file:
        guide_file_path = worktree_path / guide_file
        guide_content = f"""# Task Guidelines
This task is currently assigned to **{agent}** inside the task orchestration pipeline.

## Task Info
- **ID**: {task_id}
- **Title**: {task["title"]}
- **Active Branch**: {branch_name}
- **Worktree**: {worktree_path}

## Instructions
1. Please complete the requirements. Ensure code compiles and all unit tests pass.
2. When you are finished, you MUST execute the submit command inside the main repository:
   agy-flow submit {task_id}
"""
        guide_file_path.parent.mkdir(parents=True, exist_ok=True)
        guide_file_path.write_text(guide_content, encoding="utf-8")
        print(f"Injected guidance file at {guide_file_path}")

    current_task_path = worktree_path / ".agents" / "current_task.json"
    current_task_path.parent.mkdir(parents=True, exist_ok=True)
    task_metadata = {
        "task_id": task_id,
        "title": task["title"],
        "agent": agent,
        "status": "In Progress",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(current_task_path, "w", encoding="utf-8") as f:
            json.dump(task_metadata, f, indent=4)
        print(f"Created task metadata file for routing enforcement: {current_task_path}")
    except Exception as e:
        print(f"Warning: Failed to create current_task.json: {e}")

    code_add, _, err_add = run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    if code_add != 0:
        raise AgyFlowError(f"Git add failed in start_task: {err_add}")
    code_commit, _, err_commit = run_cmd(["git", "commit", "-m", f"chore(task): start {task_id} - setup worktree"])
    if code_commit != 0:
        raise AgyFlowError(f"Git commit failed in start_task: {err_commit}")

    if agent == "codex":
        print("Launching VS Code workspace for Codex manual developer flow...")
        try:
            subprocess.Popen(["code", str(worktree_path)], shell=True)
        except Exception as e:
            print(f"Warning: Failed to automatically launch VS Code: {e}")

    print(f"\nTask {task_id} started successfully!")
    print(f"Assigned Agent: {agent}")
    print(f"Worktree path: {worktree_path}\n")

def submit_task(args):
    """Submits the task worktree changes by running tests and committing."""
    check_inside_project("submit")
    config = get_config()
    task_id = args.task_id
    test_cmd = args.test_cmd

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise AgyFlowError(f"Task '{task_id}' not found.")

    if "In Progress" not in task["status"]:
        raise AgyFlowError(f"Task '{task_id}' is not in progress. Current status: '{task['status']}'")

    worktree_path = Path(task["worktree"])
    if not worktree_path.exists():
        raise AgyFlowError(f"Worktree path does not exist: {worktree_path}")

    current_task_path = worktree_path / ".agents" / "current_task.json"
    active_agent = task["agent"].split("->")[0]
    if current_task_path.exists():
        try:
            task_meta = json.loads(current_task_path.read_text(encoding="utf-8"))
            active_agent = task_meta.get("agent", active_agent)
        except Exception:
            pass

    if test_cmd:
        print(f"Running validation test script: {test_cmd} inside {worktree_path}...")
        test_args = test_cmd.split()
        res = subprocess.run(test_args, cwd=str(worktree_path), capture_output=True, text=True)
        print("Test Output:\n" + res.stdout)
        if res.returncode != 0:
            print(res.stderr)
            raise AgyFlowError(f"Validation tests failed (exit code: {res.returncode}). Submit aborted.")
        print("Validation tests passed successfully!")

    handoff_steps, _ = get_handoff_steps(task, config)
    next_step = find_next_handoff_step(handoff_steps, active_agent)

    if next_step:
        next_agent = next_step["agent"]
        role = next_step["role"]
        purpose = next_step["purpose"]

        print(f"Handoff target detected: transitioning from {active_agent} to {next_agent}...")

        assign_current_task_agent(next_agent, task_id)

        next_guide = worktree_path / config["agents"].get(next_agent, {}).get("guide_file", "CLAUDE.md")
        if next_guide.name != "CLAUDE.md" or next_agent == "claude":
            routing_plan_text = format_plan_summary({"recommended_pipeline": handoff_steps, "task_type": "handover"})
            next_guide_content = f"""# Task Handoff Guidance
This task has been handed off to **{next_agent}** ({role}).

## Task Info
- **ID**: {task_id}
- **Title**: {task["title"]}
- **Purpose**: {purpose}

{routing_plan_text}

## Instructions
1. Please complete the requirements listed above. Ensure code compiles and all unit tests pass.
2. AUTOMATED SUBMISSION: When you are finished and everything is verified, you MUST execute the following command:
   agy-flow submit {task_id}
"""
            try:
                next_guide.write_text(next_guide_content, encoding="utf-8")
                print(f"Injected guidance file for next agent at {next_guide}")
            except Exception as e:
                print(f"Warning: Failed to write guidance file: {e}")

        print("Staging and committing worktree changes for handover...")
        code_wadd, _, err_wadd = run_cmd(["git", "add", "."], cwd=str(worktree_path))
        if code_wadd != 0:
            raise AgyFlowError(f"Git add failed in worktree handover: {err_wadd}")
        code_wcommit, _, err_wcommit = run_cmd(["git", "commit", "-m", f"chore(task): handover task-{task_id} from {active_agent} to {next_agent}"], cwd=str(worktree_path))
        if code_wcommit != 0:
            raise AgyFlowError(f"Git commit failed in worktree handover: {err_wcommit}")

        next_status = f"In Progress ({next_agent})"
        update_board_row(task_id, next_status)
        code_badd, _, err_badd = run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
        if code_badd != 0:
            raise AgyFlowError(f"Git add board failed in handover: {err_badd}")
        code_bcommit, _, err_bcommit = run_cmd(["git", "commit", "-m", f"chore(task): transition {task_id} status to {next_agent}"])
        if code_bcommit != 0:
            raise AgyFlowError(f"Git commit board failed in handover: {err_bcommit}")

        print(f"\n🔄 AGENT PIPELINE TRANSITION SUCCESSFUL: {active_agent} -> {next_agent}\n")
        return

    # No further agents, submit to Review
    current_task_path = worktree_path / ".agents" / "current_task.json"
    if current_task_path.exists():
        try:
            current_task_path.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete current_task.json: {e}")

    print("Staging and committing worktree changes...")
    code_wadd, _, err_wadd = run_cmd(["git", "add", "."], cwd=str(worktree_path))
    if code_wadd != 0:
        raise AgyFlowError(f"Git add failed in worktree submit: {err_wadd}")

    code, stdout, stderr = run_cmd(["git", "status", "--porcelain"], cwd=str(worktree_path))
    if not stdout:
        print("No changes to commit in the worktree.")
    else:
        code, stdout, stderr = run_cmd(["git", "commit", "-m", f"feat({task_id}): implement requirements"], cwd=str(worktree_path))
        if code != 0:
            raise AgyFlowError(f"Git commit failed in worktree submit: {stderr}")
        print("Committed changes to task branch.")

    update_board_row(task_id, "Review")
    code_badd, _, err_badd = run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    if code_badd != 0:
        raise AgyFlowError(f"Git add board failed in submit: {err_badd}")
    code_bcommit, _, err_bcommit = run_cmd(["git", "commit", "-m", f"chore(task): submit {task_id} for review"])
    if code_bcommit != 0:
        raise AgyFlowError(f"Git commit board failed in submit: {err_bcommit}")

    print(f"\nTask {task_id} submitted successfully! Status updated to 'Review'.\n")

def merge_task(args):
    """Merges the task branch, removes the worktree, and cleans up."""
    check_inside_project("merge")
    task_id = args.task_id

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise AgyFlowError(f"Task '{task_id}' not found.")

    branch_name = task["branch"]
    worktree_path = Path(task["worktree"])

    print(f"Merging task {task_id} (branch: {branch_name})...")

    code, stdout, stderr = run_cmd(["git", "branch", "--show-current"])
    main_branch = stdout.strip()

    print(f"Merging {branch_name} into {main_branch}...")
    code, stdout, stderr = run_cmd([
        "git", "merge", branch_name, "--no-ff", "-m", f"merge(task): merge {task_id} - {task['title']}"
    ])
    if code != 0:
        raise AgyFlowError(f"Merge conflict or failure: {stderr}. Please resolve manually.")

    if worktree_path.exists():
        print(f"Removing worktree at {worktree_path}...")
        code, stdout, stderr = run_cmd(["git", "worktree", "remove", str(worktree_path), "--force"])
        if code != 0:
            import shutil
            shutil.rmtree(worktree_path, ignore_errors=True)
            run_cmd(["git", "worktree", "prune"])

    print(f"Deleting branch {branch_name}...")
    code_del, _, err_del = run_cmd(["git", "branch", "-d", branch_name])
    if code_del != 0:
        raise AgyFlowError(f"Failed to delete branch {branch_name}: {err_del}")

    update_board_row(task_id, "Done")
    code_badd, _, err_badd = run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    if code_badd != 0:
        raise AgyFlowError(f"Git add board failed in merge: {err_badd}")
    code_bcommit, _, err_bcommit = run_cmd(["git", "commit", "-m", f"chore(task): complete and merge {task_id}"])
    if code_bcommit != 0:
        raise AgyFlowError(f"Git commit board failed in merge: {err_bcommit}")

    print(f"\nTask {task_id} merged and cleaned up successfully! Status updated to 'Done'.\n")

def status_tasks(args):
    """Show detailed current task board status and token cost breakdown."""
    check_inside_project("status")
    tasks = parse_board_rows()

    print("\n" + "=" * 100)
    print(" ACTIVE TASK BOARD STATUS ".center(100, "="))
    print("=" * 100)
    print(f"{'Task ID':<10} | {'Title':<40} | {'Assigned Agent':<20} | {'Status':<15}")
    print("-" * 100)
    
    for t in tasks:
        print(f"{t['id']:<10} | {t['title'][:40]:<40} | {t['agent']:<20} | {t['status']:<15}")
    
    print("=" * 100)
    print(" ESTIMATED PROJECT COSTS ".center(100, "="))
    print("=" * 100)

    costs = load_costs()
    total_budget = costs.get("total_budget", 10.0)
    task_breakdown = []
    accumulated = 0.0

    for tid, entry in costs.get("tasks", {}).items():
        cost_val = entry.get("cost", 0.0)
        accumulated += cost_val
        task_breakdown.append(
            f"  - {tid:<10} : Input={entry.get('input_tokens'):<7} "
            f"Output={entry.get('output_tokens'):<7} "
            f"Cost=${cost_val:.5f}"
        )

    print(f"  Total Cost Limit Budget : ${total_budget:.2f} USD")
    print(f"  Accumulated Spend       : ${accumulated:.5f} USD")
    print(f"  Remaining Pool          : ${max(0.0, total_budget - accumulated):.5f} USD")
    print("-" * 100)
    if task_breakdown:
        for item in task_breakdown:
            print(item)
    else:
        print("No cost records found for active tasks.")
    print("=" * 100 + "\n")


def update_module_paths():
    global PROJECT_ROOT, AGENTS_DIR, TASKS_DIR, TEMPLATES_DIR, LOGS_DIR, CONFIG_FILE, BOARD_FILE, COSTS_FILE
    import agy_flow.config
    PROJECT_ROOT = agy_flow.config.PROJECT_ROOT
    AGENTS_DIR = agy_flow.config.AGENTS_DIR
    TASKS_DIR = agy_flow.config.TASKS_DIR
    TEMPLATES_DIR = agy_flow.config.TEMPLATES_DIR
    LOGS_DIR = agy_flow.config.LOGS_DIR
    CONFIG_FILE = agy_flow.config.CONFIG_FILE
    BOARD_FILE = agy_flow.config.BOARD_FILE
    COSTS_FILE = agy_flow.config.COSTS_FILE

