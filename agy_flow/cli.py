import sys
import json
import argparse
from pathlib import Path
from agy_flow.config import (
    CONFIG_FILE,
    COSTS_FILE,
    PROJECT_ROOT,
    BOARD_FILE,
    load_costs,
    save_costs,
)
from agy_flow.git_ops import run_cmd
from agy_flow.tasks import (
    init_project,
    create_task,
    start_task,
    status_tasks,
    submit_task,
    merge_task,
    parse_board_rows,
    estimate_and_log_cost,
    check_inside_project,
)
from agy_flow.router import plan_task_command
from agy_flow.handoff import assign_command, handoff_plan_command
from agy_flow.llm import ask_agent_command, review_task_command
from agy_flow.gateway import serve_gateway

def main():
    parser = argparse.ArgumentParser(
        description="agy-flow: Multi-Agent Coding Collaboration CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    subparsers.add_parser("init", help="Initialize agy-flow environment")

    # serve subcommand
    parser_serve = subparsers.add_parser("serve", help="Start local HTTP gateway server")
    parser_serve.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host address to bind to"
    )
    parser_serve.add_argument(
        "--port", type=int, default=8000, help="Port to bind to"
    )

    # task create subcommand
    parser_create = subparsers.add_parser("create", help="Create a new task")
    parser_create.add_argument("title", type=str, help="Title of the task")
    parser_create.add_argument(
        "--agent",
        type=str,
        required=False,
        default=None,
        choices=["claude", "antigravity", "codex", "deepseek"],
        help="Agent to assign the task to (auto-detected if omitted)",
    )
    parser_create.add_argument(
        "--desc", type=str, default="", help="Optional detailed description"
    )

    # task plan subcommand
    parser_plan = subparsers.add_parser(
        "plan", help="Preview structured routing without creating a task"
    )
    parser_plan.add_argument("title", type=str, help="Title or natural language task")

    # assignment subcommand
    parser_assign = subparsers.add_parser(
        "assign", help="Assign .agents/current_task.json to an agent"
    )
    parser_assign.add_argument(
        "agent",
        choices=["codex", "antigravity", "claude", "deepseek"],
        help="Agent to assign this workspace to",
    )
    parser_assign.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Optional active task ID to store in current_task.json",
    )

    # handoff plan subcommand
    parser_handoff_plan = subparsers.add_parser(
        "handoff-plan", help="Preview saved-plan handoff steps for a task"
    )
    parser_handoff_plan.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")

    # ask subcommand
    parser_ask = subparsers.add_parser("ask", help="Ask an LLM API agent")
    parser_ask.add_argument("agent", choices=["deepseek"], help="LLM API agent")
    parser_ask.add_argument("prompt", type=str, help="Prompt to send")
    parser_ask.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved settings and prompt without calling the API",
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

    # task review subcommand
    parser_review = subparsers.add_parser(
        "review", help="Review a task diff with an LLM API agent"
    )
    parser_review.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_review.add_argument(
        "--agent",
        choices=["deepseek"],
        default="deepseek",
        help="LLM API agent to use for review",
    )
    parser_review.add_argument(
        "--max-diff-chars",
        type=int,
        default=50000,
        help="Maximum diff characters to send",
    )
    parser_review.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved settings and prompt without calling the API",
    )

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
    elif args.command == "serve":
        serve_gateway(args)
    elif args.command == "create":
        create_task(args)
    elif args.command == "start":
        start_task(args)
    elif args.command == "status":
        status_tasks(args)
    elif args.command == "plan":
        plan_task_command(args)
    elif args.command == "assign":
        assign_command(args)
    elif args.command == "handoff-plan":
        handoff_plan_command(args)
    elif args.command == "ask":
        ask_agent_command(args)
    elif args.command == "submit":
        submit_task(args)
    elif args.command == "merge":
        merge_task(args)
    elif args.command == "review":
        review_task_command(args)
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
            run_cmd(["agy-flow", "status"])
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
