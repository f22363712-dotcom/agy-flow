#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
import datetime
import re
from pathlib import Path
from agy_flow_classify import classify_task

# Defaults and Constants
DEFAULT_CONFIG = {
    "project_name": "multi_agent_project",
    "worktrees_dir": "../multi_agent_worktrees",
    "agents": {
        "claude": {
            "cli_command": "claude",
            "default_args": [
                "-p",
                "--allowedTools",
                "Edit,Read,Bash",
                "--permission-mode",
                "dontAsk",
            ],
            "guide_file": "CLAUDE.md",
        },
        "antigravity": {"guide_file": ".agents/AGENTS.md"},
        "codex": {"interactive": True},
    },
}

DEFAULT_BOARD_TEMPLATE = """# Project Task Board

| Task ID | Title | Agent | Status | Branch | Worktree Path |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

DEFAULT_TASK_TEMPLATE = """# Task: {task_id} - {title}

## Metadata
- **ID**: {task_id}
- **Title**: {title}
- **Assigned Agent**: {agent}
- **Status**: {status}
- **Created Time**: {created_time}

## Requirements & Spec
*Describe the functional requirements and technical specifications for this task here.*

## Acceptance Criteria
*List the test cases or verification steps that must pass.*
"""


def find_project_root():
    """Traverses upward from the current directory to find the nearest .agents folder."""
    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".agents").is_dir():
            return parent
    return None


# Dynamic Path Resolution
PROJECT_ROOT = find_project_root()
if PROJECT_ROOT is None:
    # If not found, default to current working directory (e.g. for init
    # command)
    PROJECT_ROOT = Path.cwd().resolve()

AGENTS_DIR = PROJECT_ROOT / ".agents"
TASKS_DIR = AGENTS_DIR / "tasks"
TEMPLATES_DIR = AGENTS_DIR / "templates"
LOGS_DIR = AGENTS_DIR / "logs"
CONFIG_FILE = AGENTS_DIR / "config.json"
BOARD_FILE = TASKS_DIR / "board.md"
COSTS_FILE = AGENTS_DIR / "costs.json"

PRICING = {
    "claude": {"input": 0.14 / 1000000, "output": 0.28 / 1000000},
    "antigravity": {"input": 0.075 / 1000000, "output": 0.30 / 1000000},
    "codex": {"input": 0.0, "output": 0.0},
}


def run_cmd(cmd, cwd=None):
    """Executes a command and returns the exit code, stdout, and stderr."""
    run_cwd = cwd or str(PROJECT_ROOT)
    print(f"Executing: {' '.join(cmd)} in {run_cwd}")
    res = subprocess.run(cmd, cwd=run_cwd, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def get_config():
    """Loads and returns the configuration json."""
    if not CONFIG_FILE.exists():
        print(
            f"Error: Config file not found at {CONFIG_FILE}. Run 'agy-flow init' first."
        )
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_board():
    """Loads the board.md file lines."""
    if not BOARD_FILE.exists():
        print(
            f"Error: Board file not found at {BOARD_FILE}. Run 'agy-flow init' first."
        )
        sys.exit(1)
    with open(BOARD_FILE, "r", encoding="utf-8") as f:
        return f.readlines()


def save_board(lines):
    """Saves lines back to board.md."""
    with open(BOARD_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def load_costs():
    """Loads costs from costs.json, or creates it with defaults if it doesn't exist."""
    if not COSTS_FILE.exists():
        COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_costs = {"total_budget": 10.0, "tasks": {}}
        with open(COSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_costs, f, indent=4)
        return default_costs
    try:
        with open(COSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"total_budget": 10.0, "tasks": {}}


def save_costs(costs):
    """Saves costs dict back to costs.json."""
    with open(COSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(costs, f, indent=4)


def estimate_and_log_cost(
    task_id, agent, worktree_path=None, manual_input=None, manual_output=None
):
    """Estimates or logs the token usage and cost for a task."""
    costs = load_costs()

    # 1. Check manual input first
    if manual_input is not None and manual_output is not None:
        input_tokens = manual_input
        output_tokens = manual_output
    else:
        # Heuristic estimation based on worktree diff
        input_tokens = 12000  # Default base input tokens
        output_tokens = 800  # Default base output tokens

        if worktree_path and Path(worktree_path).exists():
            try:
                # Get list of modified files in worktree
                # Run git diff --numstat inside the worktree
                res = subprocess.run(
                    ["git", "diff", "--numstat"],
                    cwd=str(worktree_path),
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0 and res.stdout:
                    added_lines = 0
                    for line in res.stdout.strip().split("\n"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[0].isdigit():
                            added_lines += int(parts[0])
                    # Heuristics: 1 line of code = ~40 chars = ~10 tokens
                    output_tokens = max(800, added_lines * 10)
                    input_tokens = max(
                        12000, output_tokens * 8
                    )  # Context is ~8x output size
            except Exception:
                pass

    # Calculate cost
    rates = PRICING.get(agent.lower(), {"input": 0.0, "output": 0.0})
    cost_val = (input_tokens * rates["input"]) + (output_tokens * rates["output"])

    costs["tasks"][task_id] = {
        "agent": agent,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost_val, 6),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    save_costs(costs)
    # Automatically add costs.json to git
    run_cmd(["git", "add", str(COSTS_FILE.relative_to(PROJECT_ROOT))])


def parse_board_rows():
    """Parses board.md table rows and returns a list of dicts representing tasks."""
    lines = load_board()
    tasks = []
    for line in lines:
        if "|" in line:
            if "---" in line or "Task ID" in line:
                continue  # Skip header and separator
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


def update_board_row(task_id, status, branch="", worktree=""):
    """Updates a row in the board.md file."""
    lines = load_board()
    new_lines = []
    updated = False
    for line in lines:
        if "|" in line and task_id in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            parts[3] = status
            if branch:
                parts[4] = branch
            if worktree:
                parts[5] = worktree
            new_line = "| " + " | ".join(parts) + " |\n"
            new_lines.append(new_line)
            updated = True
        else:
            new_lines.append(line)
    if updated:
        save_board(new_lines)
    else:
        print(f"Warning: Task row {task_id} not found in board.md to update.")


def check_inside_project(command):
    """Ensures we are running inside an initialized project for non-init commands."""
    if find_project_root() is None:
        print(
            f"Error: The '{command}' command must be run inside a gy-flow project directory (or parent directory containing .agents/)."
        )
        print(
            "Please run 'agy-flow init' to initialize a new project in this directory."
        )
        sys.exit(1)


def init_project(args):
    """Initializes the agy-flow structure in the current working directory."""
    global \
        PROJECT_ROOT, \
        AGENTS_DIR, \
        TASKS_DIR, \
        TEMPLATES_DIR, \
        LOGS_DIR, \
        CONFIG_FILE, \
        BOARD_FILE, \
        COSTS_FILE
    PROJECT_ROOT = Path.cwd().resolve()
    AGENTS_DIR = PROJECT_ROOT / ".agents"
    TASKS_DIR = AGENTS_DIR / "tasks"
    TEMPLATES_DIR = AGENTS_DIR / "templates"
    LOGS_DIR = AGENTS_DIR / "logs"
    CONFIG_FILE = AGENTS_DIR / "config.json"
    BOARD_FILE = TASKS_DIR / "board.md"
    COSTS_FILE = AGENTS_DIR / "costs.json"

    print(f"Initializing agy-flow collaboration framework in {PROJECT_ROOT}...")

    # 1. Create directories
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Write defaults if they don't exist
    if not CONFIG_FILE.exists():
        # Set project name dynamically based on directory name
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

    # Load costs which automatically initializes costs.json
    load_costs()
    print(f"Created cost statistics registry: {COSTS_FILE}")

    # 3. Check Git repository
    code, stdout, stderr = run_cmd(["git", "status"], cwd=str(PROJECT_ROOT))
    if code != 0:
        print("Git repository not initialized. Initializing git...")
        run_cmd(["git", "init"], cwd=str(PROJECT_ROOT))
    else:
        print("Git repository already initialized.")

    # Add worktree output to gitignore if configured inside project
    config = get_config()
    worktrees_dir = Path(config["worktrees_dir"])
    if not worktrees_dir.is_absolute():
        worktrees_dir = (PROJECT_ROOT / worktrees_dir).resolve()

    # Setup .gitignore rules
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

    print("Initialization completed successfully.")


def create_task(args):
    """Creates a new task file and registers it in the board."""
    check_inside_project("create")
    config = get_config()
    title = args.title

    # 智能路由：如果没指定 --agent，自动判断
    if args.agent is None:
        agent = classify_task(title)
        print(f"🤖 已自动选择 Agent: {agent}")
    else:
        agent = args.agent.lower()

    agents_in_pipeline = [a.strip() for a in agent.split("->")]
    for a in agents_in_pipeline:
        if a not in config["agents"]:
            print(f"Error: Agent '{a}' in pipeline '{agent}' is not defined in config.json")
            sys.exit(1)

    # Determine new task ID
    existing_tasks = parse_board_rows()
    ids = []
    for t in existing_tasks:
        match = re.search(r"task-(\d+)", t["id"])
        if match:
            ids.append(int(match.group(1)))
    next_id = max(ids) + 1 if ids else 1
    task_id = f"task-{next_id:03d}"

    task_file = TASKS_DIR / f"{task_id}.md"

    # Read template
    template_path = TEMPLATES_DIR / "task_template.md"
    if template_path.exists():
        template_content = template_path.read_text(encoding="utf-8")
    else:
        template_content = DEFAULT_TASK_TEMPLATE

    # Format template
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_content = template_content.format(
        task_id=task_id, title=title, agent=agent, status="Todo", created_time=now_str
    )

    # Save task file
    task_file.write_text(task_content, encoding="utf-8")
    print(f"Created task file: {task_file}")

    # Append to board.md
    board_lines = load_board()
    new_row = f"| {task_id} | {title} | {agent} | Todo | | |\n"

    # Find last table row or end of file to append
    inserted = False
    for i in range(len(board_lines) - 1, -1, -1):
        if "|" in board_lines[i]:
            board_lines.insert(i + 1, new_row)
            inserted = True
            break
    if not inserted:
        board_lines.append(new_row)

    save_board(board_lines)
    print(f"Added task {task_id} to board.md")

    # Git Commit the new task documents
    run_cmd(
        [
            "git",
            "add",
            str(task_file.relative_to(PROJECT_ROOT)),
            str(BOARD_FILE.relative_to(PROJECT_ROOT)),
        ]
    )
    run_cmd(["git", "commit", "-m", f"docs(task): create {task_id} - {title}"])


def start_task(args):
    """Starts a task by checking out a branch and setting up Git Worktree."""
    check_inside_project("start")
    config = get_config()
    task_id = args.task_id

    # Find the task
    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        print(f"Error: Task '{task_id}' not found in board.md.")
        sys.exit(1)

    if task["status"] == "Done":
        print(f"Warning: Task '{task_id}' is already Done.")

    pipeline = [a.strip() for a in task["agent"].split("->")]
    agent = pipeline[0]
    branch_name = f"agent/{task_id}"

    worktree_parent = Path(config["worktrees_dir"])
    if not worktree_parent.is_absolute():
        worktree_parent = (PROJECT_ROOT / worktree_parent).resolve()

    worktree_path = worktree_parent / task_id

    # Ensure worktree parent exists
    worktree_parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting task {task_id} on branch {branch_name}...")

    # 1. Create and add worktree
    # Check if branch exists
    code, stdout, stderr = run_cmd(["git", "branch", "--list", branch_name])
    if branch_name in stdout:
        print(f"Branch {branch_name} already exists. Attempting to add worktree...")
        code, stdout, stderr = run_cmd(
            ["git", "worktree", "add", str(worktree_path), branch_name]
        )
    else:
        print(f"Creating new branch {branch_name} and worktree...")
        code, stdout, stderr = run_cmd(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)]
        )

    if code != 0:
        print(f"Error adding worktree: {stderr}")
        sys.exit(1)

    # 2. Update board.md
    update_board_row(
        task_id, "In Progress", branch=branch_name, worktree=str(worktree_path)
    )

    # Create .vscode/tasks.json inside the worktree for hotkey submission
    # (Ctrl+Shift+B)
    vscode_dir = worktree_path / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    tasks_json_path = vscode_dir / "tasks.json"
    tasks_json_content = {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "agy-flow: Submit This Task",
                "type": "shell",
                "command": f"agy-flow submit {task_id}",
                "problemMatcher": [],
                "group": {"kind": "build", "isDefault": True},
            }
        ],
    }
    try:
        with open(tasks_json_path, "w", encoding="utf-8") as f:
            json.dump(tasks_json_content, f, indent=4)
        print(f"Created VS Code tasks configuration at {tasks_json_path}")
    except Exception as e:
        print(f"Warning: Failed to create .vscode/tasks.json: {e}")

    # 3. Dynamic Context Injection
    agent_info = config["agents"].get(agent, {})
    guide_file_name = agent_info.get("guide_file")

    if guide_file_name:
        guide_file_path = worktree_path / guide_file_name
        # Create subdirectories if needed (e.g., .agents/AGENTS.md)
        guide_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Read the task file spec
        task_file = TASKS_DIR / f"{task_id}.md"
        task_spec = (
            task_file.read_text(encoding="utf-8")
            if task_file.exists()
            else f"Task ID: {task_id}\nTitle: {task['title']}"
        )

        guide_content = f"""# AGENT MISSION GUIDANCE
You are working on task: {task_id}
Title: {task["title"]}
Assigned Agent: {agent}

## Task Details
{task_spec}

## Instructions
1. Please complete the requirements listed above. Ensure code compiles and all unit tests pass.
2. AUTOMATED SUBMISSION: When you are finished and everything is verified, you MUST execute the following command in the terminal using your shell/bash tool to submit your changes automatically:
   agy-flow submit {task_id}
   (Or run `agy-flow submit {task_id} --test-cmd "<test_command>"` if you have a test script to verify before commit).
"""
        guide_file_path.write_text(guide_content, encoding="utf-8")
        print(f"Injected guidance file at {guide_file_path}")

    # Write .agents/current_task.json inside the worktree for agent enforcement
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

    # 4. Git Commit the board updates in main
    run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    run_cmd(["git", "commit", "-m", f"chore(task): start {task_id} - setup worktree"])

    # Auto-launch VS Code if the agent is Codex
    if agent == "codex":
        print("Launching VS Code workspace for Codex manual developer flow...")
        try:
            subprocess.Popen(["code", str(worktree_path)], shell=True)
        except Exception as e:
            print(f"Warning: Failed to automatically launch VS Code: {e}")

    # Output next-step prompt instructions
    print("\n" + "=" * 60)
    print(f"Task {task_id} is successfully started!")
    print(f"Worktree folder: {worktree_path}")
    print(f"Git Branch: {branch_name}")
    print("=" * 60)
    if agent == "claude":
        print(f"👉 To trigger Claude Code automated run, run:")
        print(f"   cd {worktree_path}")
        print(
            f'   claude -p "Read CLAUDE.md and implement the task. Then run tests and verify."'
        )
    elif agent == "antigravity":
        print(f"👉 Antigravity (this chat agent) is assigned.")
        print(
            f"   Please instruct Antigravity to run its operations inside Cwd: {worktree_path}"
        )
        print(
            f"   It will read .agents/AGENTS.md and execute coding, vision, or verification tasks."
        )
    elif agent == "codex":
        print(f"👉 Codex (IDE Manual) is assigned.")
        print(f"   Please open VS Code in the folder: {worktree_path}")
        print(f"   Implement the task manually, and write unit tests.")
    print("=" * 60 + "\n")


def status_tasks(args):
    """Prints the current task status along with token cost summaries."""
    check_inside_project("status")
    tasks = parse_board_rows()
    if not tasks:
        print("No tasks found in the task board.")
        return

    print(f"\nGY-FLOW TASK STATUS BOARD (Project Root: {PROJECT_ROOT})")
    print("=" * 100)
    print(
        f"{'Task ID':<10} | {'Title':<35} | {'Agent':<12} | {'Status':<12} | {
            'Branch':<20}"
    )
    print("-" * 100)
    for t in tasks:
        print(
            f"{t['id']:<10} | {t['title'][:35]:<35} | {t['agent']:<12} | {t['status']:<12} | {t['branch']:<20}"
        )
    print("=" * 100)

    # Cost & Quota Tracker section
    costs = load_costs()
    total_budget = costs.get("total_budget", 10.0)

    total_expended = 0.0
    task_breakdown = []
    for tid, info in costs.get("tasks", {}).items():
        # Only show costs of active/listed tasks in this repository
        if any(t["id"] == tid for t in tasks):
            cost_val = info.get("cost", 0.0)
            total_expended += cost_val
            task_breakdown.append(
                f"* {tid} ({info.get('agent', 'unknown')}): ${cost_val:.6f} "
                f"(Input: ~{info.get('input_tokens', 0):,}, Output: ~{
                    info.get('output_tokens', 0):,} tokens)"
            )

    remaining_balance = max(0.0, total_budget - total_expended)
    remaining_pct = (remaining_balance / total_budget) * 100 if total_budget > 0 else 0

    print("💰 COST & BUDGET TRACKER")
    print("-" * 100)
    print(
        f"Total Budget: ${total_budget:.4f} | Total Expended: ${total_expended:.4f} | "
        f"Remaining Balance: ${remaining_balance:.4f} ({remaining_pct:.2f}% remaining)"
    )
    print("-" * 100)
    if task_breakdown:
        for item in task_breakdown:
            print(item)
    else:
        print("No cost records found for active tasks.")
    print("=" * 100 + "\n")


def submit_task(args):
    """Submits the task worktree changes by running tests and committing."""
    check_inside_project("submit")
    task_id = args.task_id
    test_cmd = args.test_cmd

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        print(f"Error: Task '{task_id}' not found.")
        sys.exit(1)

    worktree_path = Path(task["worktree"])
    if not worktree_path.exists():
        print(
            f"Error: Worktree path {worktree_path} does not exist. Was it already merged?"
        )
        sys.exit(1)

    # 1. Run tests if command provided
    if test_cmd:
        print(f"Running tests in worktree: {test_cmd}...")
        # Split command for execution
        cmd_parts = test_cmd.split()
        code, stdout, stderr = run_cmd(cmd_parts, cwd=str(worktree_path))
        print(stdout)
        if code != 0:
            print(f"Test failure! Exit code: {code}")
            print(stderr)
            sys.exit(1)
        print("All tests passed successfully!")

    # Calculate and log cost before committing
    print("Estimating token usage and costs for this task run...")
    estimate_and_log_cost(task_id, task["agent"], worktree_path=worktree_path)

    # Parse pipeline and active agent
    agent_field = task["agent"]
    pipeline = [a.strip() for a in agent_field.split("->")]
    active_agent = pipeline[0]
    current_task_path = worktree_path / ".agents" / "current_task.json"

    if current_task_path.exists():
        try:
            with open(current_task_path, "r", encoding="utf-8") as f:
                task_meta = json.load(f)
                active_agent = task_meta.get("agent", active_agent)
        except Exception:
            pass

    has_next = False
    next_agent = None
    if len(pipeline) > 1 and active_agent in pipeline:
        idx = pipeline.index(active_agent)
        if idx + 1 < len(pipeline):
            has_next = True
            next_agent = pipeline[idx + 1]

    if has_next:
        print(f"🔄 Detected next agent in pipeline: {next_agent}. Performing handover...")

        # 1. Update current_task.json to next agent
        if current_task_path.exists():
            try:
                task_meta["agent"] = next_agent
                task_meta["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(current_task_path, "w", encoding="utf-8") as f:
                    json.dump(task_meta, f, indent=4)
            except Exception as e:
                print(f"Warning: Failed to update current_task.json: {e}")

        # 2. Write guide file for the next agent
        next_agent_info = config.get("agents", {}).get(next_agent, {})
        next_guide_file = next_agent_info.get("guide_file")
        if next_guide_file:
            next_guide_path = worktree_path / next_guide_file
            next_guide_path.parent.mkdir(parents=True, exist_ok=True)
            task_file = TASKS_DIR / f"{task_id}.md"
            task_spec = task_file.read_text(encoding="utf-8") if task_file.exists() else f"Task ID: {task_id}\nTitle: {task['title']}"
            next_guide_content = f"""# AGENT MISSION GUIDANCE (HANDOVER)
You are taking over task: {task_id} (Handed over to {next_agent} from {active_agent})
Title: {task["title"]}
Assigned Agent: {next_agent}

## Task Details
{task_spec}

## Instructions
1. Please complete the requirements listed above. Ensure code compiles and all unit tests pass.
2. AUTOMATED SUBMISSION: When you are finished and everything is verified, you MUST execute the following command:
   agy-flow submit {task_id}
"""
            try:
                next_guide_path.write_text(next_guide_content, encoding="utf-8")
                print(f"Injected guidance file for next agent at {next_guide_path}")
            except Exception as e:
                print(f"Warning: Failed to write guidance file: {e}")

        # 3. Stage and commit in worktree (keep current_task.json and guide file for the next agent)
        print("Staging and committing worktree changes for handover...")
        run_cmd(["git", "add", "."], cwd=str(worktree_path))
        run_cmd(["git", "commit", "-m", f"chore(task): handover task-{task_id} from {active_agent} to {next_agent}"], cwd=str(worktree_path))

        # 4. Update board in main repo
        next_status = f"In Progress ({next_agent})"
        update_board_row(task_id, next_status)
        run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
        run_cmd(["git", "commit", "-m", f"chore(task): transition {task_id} status to {next_agent}"])

        print("\n" + "=" * 80)
        print(f"🔄 AGENT PIPELINE TRANSITION SUCCESSFUL!")
        print(f"Task: {task_id} - {task['title']}")
        print(f"Transition: {active_agent} ➡️ {next_agent}")
        print(f"Status Updated: {next_status}")
        print("=" * 80)

        # Auto-launch VS Code if next agent is Codex
        if next_agent == "codex":
            print("Launching VS Code workspace for Codex manual developer flow...")
            try:
                subprocess.Popen(["code", str(worktree_path)], shell=True)
            except Exception as e:
                print(f"Warning: Failed to automatically launch VS Code: {e}")
        elif next_agent == "antigravity":
            print(f"👉 Please instruct Antigravity in your chat window to take over task-{task_id}!")
        print("=" * 80 + "\n")
        return

    # --- Otherwise, this is the end of the pipeline. Execute normal cleanup and submission ---
    print("No further agents in pipeline. Finalizing task submission...")

    # Revert or delete guide files so they do not contaminate the task commits
    print("Cleaning up task-specific guidance files before commit...")
    for agent_name, info in config.get("agents", {}).items():
        guide_file = info.get("guide_file")
        if guide_file:
            code, stdout, stderr = run_cmd(["git", "ls-files", "--error-unmatch", guide_file], cwd=str(worktree_path))
            if code == 0:
                print(f"Restoring tracked guide file to HEAD: {guide_file}")
                run_cmd(["git", "checkout", "HEAD", "--", guide_file], cwd=str(worktree_path))
            else:
                guide_path = worktree_path / guide_file
                if guide_path.exists():
                    print(f"Removing untracked guide file: {guide_file}")
                    try:
                        guide_path.unlink()
                    except Exception as e:
                        print(f"Warning: Failed to delete {guide_file}: {e}")

    # Also delete current_task.json to clean up worktree
    current_task_path = worktree_path / ".agents" / "current_task.json"
    if current_task_path.exists():
        print("Removing temporary current_task.json file...")
        try:
            current_task_path.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete current_task.json: {e}")

    # 2. Git commit in worktree
    print("Staging and committing worktree changes...")
    run_cmd(["git", "add", "."], cwd=str(worktree_path))
    # Check if there are changes to commit
    code, stdout, stderr = run_cmd(
        ["git", "status", "--porcelain"], cwd=str(worktree_path)
    )
    if not stdout:
        print("No changes to commit in the worktree.")
    else:
        code, stdout, stderr = run_cmd(
            ["git", "commit", "-m", f"feat({task_id}): implement requirements"],
            cwd=str(worktree_path),
        )
        if code != 0:
            print(f"Git commit failed: {stderr}")
            sys.exit(1)
        print("Committed changes to task branch.")

    # 3. Update board status in main repo
    update_board_row(task_id, "Review")
    run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    run_cmd(["git", "commit", "-m", f"chore(task): submit {task_id} for review"])

    print(f"\nTask {task_id} submitted successfully! Status updated to 'Review'.")
    print("Please review the changes in the branch before merging.\n")


def merge_task(args):
    """Merges the task branch, removes the worktree, and cleans up."""
    check_inside_project("merge")
    task_id = args.task_id

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        print(f"Error: Task '{task_id}' not found.")
        sys.exit(1)

    branch_name = task["branch"]
    worktree_path = Path(task["worktree"])

    print(f"Merging task {task_id} (branch: {branch_name})...")

    # 1. Merge branch to main
    # Find active branch in main repository (usually 'main' or 'master')
    code, stdout, stderr = run_cmd(["git", "branch", "--show-current"])
    main_branch = stdout.strip()

    # Merge the branch
    print(f"Merging {branch_name} into {main_branch}...")
    code, stdout, stderr = run_cmd(
        [
            "git",
            "merge",
            branch_name,
            "--no-ff",
            "-m",
            f"merge(task): merge {task_id} - {task['title']}",
        ]
    )
    if code != 0:
        print(f"Merge conflict or failure: {stderr}")
        print("Please resolve the conflict manually, then run task merge again.")
        sys.exit(1)

    # 2. Remove Git Worktree
    if worktree_path.exists():
        print(f"Removing worktree at {worktree_path}...")
        # Force remove is safer in case of untracked files
        code, stdout, stderr = run_cmd(
            ["git", "worktree", "remove", str(worktree_path), "--force"]
        )
        if code != 0:
            print(
                f"Warning: Failed to remove worktree using git command: {stderr}. Attempting filesystem deletion..."
            )
            # Fallback to general file deletion if git worktree command fails
            import shutil

            shutil.rmtree(worktree_path, ignore_errors=True)
            run_cmd(["git", "worktree", "prune"])

    # 3. Delete the local branch
    print(f"Deleting branch {branch_name}...")
    run_cmd(["git", "branch", "-d", branch_name])

    # 4. Update task board status to Done
    update_board_row(task_id, "Done")
    run_cmd(["git", "add", str(BOARD_FILE.relative_to(PROJECT_ROOT))])
    run_cmd(["git", "commit", "-m", f"chore(task): complete and merge {task_id}"])

    print(
        f"\nTask {task_id} merged and cleaned up successfully! Status updated to 'Done'.\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="gy-flow: Multi-Agent Coding Collaboration CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    subparsers.add_parser("init", help="Initialize agy-flow environment")

    # task create subcommand
    parser_create = subparsers.add_parser("create", help="Create a new task")
    parser_create.add_argument("title", type=str, help="Title of the task")
    parser_create.add_argument(
        "--agent",
        type=str,
        required=False,
        default=None,
        choices=["claude", "antigravity", "codex"],
        help="Agent to assign the task to (auto-detected if omitted)",
    )
    parser_create.add_argument(
        "--desc", type=str, default="", help="Optional detailed description"
    )

    # task start subcommand
    parser_start = subparsers.add_parser(
        "start", help="Start work on a task (branch + worktree)"
    )
    parser_start.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")

    # task status subcommand
    subparsers.add_parser("status", help="Show task board status")

    # task submit subcommand
    parser_submit = subparsers.add_parser("submit", help="Commit and submit task work")
    parser_submit.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_submit.add_argument(
        "--test-cmd",
        type=str,
        default="",
        help="Optional test command to run before submitting",
    )

    # task merge subcommand
    parser_merge = subparsers.add_parser(
        "merge", help="Merge task and cleanup worktree"
    )
    parser_merge.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")

    # cost subcommand
    parser_cost = subparsers.add_parser(
        "cost", help="Manage and view project token costs"
    )
    parser_cost_sub = parser_cost.add_subparsers(
        dest="cost_command", help="Cost subcommands"
    )

    # cost log sub-subcommand
    parser_cost_log = parser_cost_sub.add_parser(
        "log", help="Log manual token usage for a task"
    )
    parser_cost_log.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_cost_log.add_argument(
        "--input", type=int, required=True, help="Input token count"
    )
    parser_cost_log.add_argument(
        "--output", type=int, required=True, help="Output token count"
    )

    # cost budget sub-subcommand
    parser_cost_budget = parser_cost_sub.add_parser(
        "budget", help="Set total project cost budget limit"
    )
    parser_cost_budget.add_argument("amount", type=float, help="Budget amount in USD")

    args = parser.parse_args()

    if args.command == "init":
        init_project(args)
    elif args.command == "create":
        create_task(args)
    elif args.command == "start":
        start_task(args)
    elif args.command == "status":
        status_tasks(args)
    elif args.command == "submit":
        submit_task(args)
    elif args.command == "merge":
        merge_task(args)
    elif args.command == "cost":
        check_inside_project("cost")
        if args.cost_command == "log":
            tasks = parse_board_rows()
            task = next((t for t in tasks if t["id"] == args.task_id), None)
            if not task:
                print(f"Error: Task '{args.task_id}' not found.")
                sys.exit(1)
            estimate_and_log_cost(
                args.task_id,
                task["agent"],
                manual_input=args.input,
                manual_output=args.output,
            )
            print(f"Logged cost for {args.task_id} successfully.")
        elif args.cost_command == "budget":
            costs = load_costs()
            costs["total_budget"] = args.amount
            save_costs(costs)
            run_cmd(["git", "add", str(COSTS_FILE.relative_to(PROJECT_ROOT))])
            run_cmd(
                [
                    "git",
                    "commit",
                    "-m",
                    f"chore(cost): set budget limit to ${args.amount:.2f}",
                ]
            )
            print(f"Set project cost budget limit to ${args.amount:.2f} successfully.")
        else:
            # Default to showing stats if no subcommand
            run_cmd(["agy-flow", "status"])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
