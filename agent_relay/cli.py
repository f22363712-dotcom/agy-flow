import sys
import json
import argparse
from pathlib import Path
from agent_relay.config import (
    CONFIG_FILE,
    COSTS_FILE,
    PROJECT_ROOT,
    BOARD_FILE,
    load_costs,
    save_costs,
)
from agent_relay.git_ops import run_cmd
from agent_relay.tasks import (
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
from agent_relay.router import plan_task_command, route_command, route_task_command
from agent_relay.handoff import assign_command, handoff_plan_command
from agent_relay.adapter import dispatch as adapter_dispatch
from agent_relay.connectors import agents_report, probe_agent, probe_all
from agent_relay.llm import ask_agent_command, review_task_command
from agent_relay.gateway import serve_gateway
from agent_relay.orchestrator import auto_command
from agent_relay.adapter import get_run
from agent_relay.output_parser import parse_agent_output
from agent_relay.review_loop import continue_after_run
from agent_relay.state_machine import (
    get_task_state,
    set_task_state,
    transition_task_state,
)
from agent_relay.policy import get_policy_info, can_dispatch, can_continue
from agent_relay.quality_gate import evaluate_task_quality
from agent_relay.submit_pipeline import finalize_task
from agent_relay.doctor import doctor, task_status
from agent_relay.handoff import lease_writer, whoami
from agent_relay.prompt_pack import build_handoff_prompt
from agent_relay.workspaces import (
    list_workspaces,
    get_workspace,
    add_workspace,
    remove_workspace,
    set_default,
    resolve_workspace,
)
from agent_relay.trial_recorder import (
    trial_start,
    trial_event,
    trial_stop,
    trial_export,
)
from agent_relay.trial import value_report


def main():
    parser = argparse.ArgumentParser(
        description="agent-relay: Multi-Agent Coding Collaboration CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    subparsers.add_parser("init", help="Initialize agent-relay environment")

    # serve subcommand
    parser_serve = subparsers.add_parser(
        "serve", help="Start local HTTP gateway server"
    )
    parser_serve.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host address to bind to"
    )
    parser_serve.add_argument("--port", type=int, default=8000, help="Port to bind to")

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
    parser_create.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace name (from workspace registry)",
    )

    # task plan subcommand
    parser_plan = subparsers.add_parser(
        "plan", help="Preview structured routing without creating a task"
    )
    parser_plan.add_argument("title", type=str, help="Title or natural language task")

    # route subcommand (capability-aware)
    parser_route = subparsers.add_parser(
        "route", help="Capability-aware routing: recommend agent for a task"
    )
    parser_route.add_argument("title", type=str, help="Task title or description")
    parser_route.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON",
    )

    # route-task subcommand
    parser_route_task = subparsers.add_parser(
        "route-task", help="Capability-aware route for an existing task"
    )
    parser_route_task.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")

    # run subcommand (manual run import)
    parser_run = subparsers.add_parser("run", help="Manage run records")
    run_sub = parser_run.add_subparsers(dest="run_command", help="Run subcommands")
    parser_run_add = run_sub.add_parser("add", help="Manually import a run record")
    parser_run_add.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_run_add.add_argument(
        "--agent",
        type=str,
        required=True,
        choices=["claude", "codex", "antigravity", "deepseek", "gemini"],
        help="Agent that performed the work",
    )
    parser_run_add.add_argument(
        "--role",
        type=str,
        default="writer",
        choices=["writer", "reviewer"],
        help="Role of the agent",
    )
    parser_run_add.add_argument(
        "--status",
        type=str,
        default="completed",
        choices=["completed", "needs_review", "blocked", "failed"],
        help="Run status",
    )
    parser_run_add.add_argument(
        "--summary", type=str, default="", help="Summary of the work done"
    )
    parser_run_add.add_argument(
        "--next-action",
        type=str,
        default="manual",
        choices=["review", "revise", "submit", "manual", "none"],
        help="Next action after this run",
    )
    parser_run_add.add_argument(
        "--files-touched",
        action="append",
        default=None,
        help="File touched (repeatable)",
    )
    parser_run_add.add_argument(
        "--tests-run",
        action="append",
        default=None,
        help="Test command run (repeatable)",
    )
    parser_run_add.add_argument(
        "--risk", action="append", default=None, help="Risk item (repeatable)"
    )

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
    parser_assign.add_argument(
        "--role",
        choices=["writer", "reviewer"],
        default="writer",
        help="Whether the assigned agent is taking writer or reviewer control",
    )
    parser_assign.add_argument(
        "--reviewer",
        action="append",
        default=None,
        help="Additional reviewer agent allowed for this task; can be repeated",
    )
    parser_assign.add_argument(
        "--mode",
        type=str,
        default="handoff",
        help="Guard mode metadata, e.g. handoff or review",
    )

    # dispatch subcommand
    parser_dispatch = subparsers.add_parser(
        "dispatch", help="Dispatch a task to an agent via the Agent Adapter v1"
    )
    parser_dispatch.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_dispatch.add_argument(
        "--agent",
        type=str,
        required=True,
        choices=["codex", "antigravity", "deepseek", "claude", "gemini"],
        help="Agent to dispatch the task to",
    )
    parser_dispatch.add_argument(
        "--mock",
        action="store_true",
        help="Mock the dispatch (supported by deepseek adapter)",
    )

    # agents subcommand
    parser_agents = subparsers.add_parser(
        "agents", help="Show agent registry + connector availability"
    )
    parser_agents.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON",
    )

    # probe subcommand
    parser_probe = subparsers.add_parser("probe", help="Probe an agent connector")
    parser_probe.add_argument(
        "target",
        nargs="?",
        default="all",
        help="Agent name (e.g. codex, deepseek) or 'all'",
    )

    # auto subcommand
    parser_auto = subparsers.add_parser(
        "auto", help="Auto-dispatch a task using capability-aware routing"
    )
    parser_auto.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_auto.add_argument(
        "--dry-run",
        action="store_true",
        help="Only compute the route, don't actually dispatch",
    )
    parser_auto.add_argument(
        "--mock",
        action="store_true",
        help="Mock dispatch (supported by deepseek adapter)",
    )

    # parse-run subcommand
    parser_parse_run = subparsers.add_parser(
        "parse-run", help="Parse a run record's agent output"
    )
    parser_parse_run.add_argument("run_id", type=str, help="Run ID (e.g. run-xxxx)")

    # continue subcommand
    parser_continue = subparsers.add_parser(
        "continue", help="Continue after a writer run (dispatch reviewer)"
    )
    parser_continue.add_argument("run_id", type=str, help="Run ID (e.g. run-xxxx)")
    parser_continue.add_argument(
        "--mock",
        action="store_true",
        help="Mock the reviewer dispatch",
    )

    # state subcommand
    parser_state = subparsers.add_parser("state", help="View or set task state")
    parser_state.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_state.add_argument(
        "--json", action="store_true", help="Output structured JSON"
    )
    parser_state.add_argument(
        "--set",
        type=str,
        default=None,
        help="Set state (e.g. blocked) — requires --reason",
    )
    parser_state.add_argument(
        "--reason",
        type=str,
        default=None,
        help="Reason for state change",
    )

    # policy subcommand
    parser_policy = subparsers.add_parser("policy", help="Show policy info for a task")
    parser_policy.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")

    # quality subcommand
    parser_quality = subparsers.add_parser(
        "quality", help="Evaluate quality gate for a task"
    )
    parser_quality.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_quality.add_argument(
        "--json", action="store_true", help="Output structured JSON"
    )

    # finalize subcommand
    parser_finalize = subparsers.add_parser(
        "finalize", help="Finalise a task (quality gate + submit pipeline)"
    )
    parser_finalize.add_argument("task_id", type=str, help="Task ID (e.g. task-001)")
    parser_finalize.add_argument(
        "--dry-run", action="store_true", help="Only check quality gate, don't submit"
    )

    # doctor subcommand
    subparsers.add_parser("doctor", help="Run system health check")

    # value-report subcommand
    parser_vr = subparsers.add_parser(
        "value-report", help="Print a value trial comparison summary"
    )
    parser_vr.add_argument("filepath", type=str, help="Path to trial results JSON file")

    # lease subcommand
    parser_lease = subparsers.add_parser(
        "lease", help="Lease the writer slot to an agent"
    )
    parser_lease.add_argument(
        "agent",
        choices=["codex", "antigravity", "claude", "deepseek"],
        help="Agent to lease the writer slot to",
    )
    parser_lease.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Optional task ID to associate",
    )
    parser_lease.add_argument(
        "--reason",
        type=str,
        default=None,
        help="Optional reason for the lease",
    )
    parser_lease.add_argument(
        "--force",
        action="store_true",
        help="Force lease even if writer slot is held by another agent",
    )

    # whoami subcommand
    subparsers.add_parser("whoami", help="Show current guard metadata")

    # workspace subcommand
    parser_ws = subparsers.add_parser("workspace", help="Manage workspace registry")
    ws_sub = parser_ws.add_subparsers(dest="ws_command", help="Workspace subcommands")

    ws_sub.add_parser("list", help="List registered workspaces")
    ws_sub.add_parser("default", help="Show default workspace")

    parser_ws_add = ws_sub.add_parser("add", help="Register a workspace")
    parser_ws_add.add_argument("name", type=str, help="Workspace name (no spaces)")
    parser_ws_add.add_argument("path", type=str, help="Absolute path to the workspace")
    parser_ws_add.add_argument("--desc", type=str, default="", help="Description")

    parser_ws_remove = ws_sub.add_parser("remove", help="Unregister a workspace")
    parser_ws_remove.add_argument("name", type=str, help="Workspace name")

    parser_ws_default = ws_sub.add_parser("set-default", help="Set default workspace")
    parser_ws_default.add_argument("name", type=str, help="Workspace name")

    parser_ws_show = ws_sub.add_parser("show", help="Show workspace details")
    parser_ws_show.add_argument("name", type=str, help="Workspace name")

    # handoff-prompt subcommand
    parser_hp = subparsers.add_parser(
        "handoff-prompt", help="Generate a handoff prompt for an agent"
    )
    parser_hp.add_argument(
        "agent",
        choices=["claude", "codex", "antigravity"],
        help="Target agent for the handoff",
    )
    parser_hp.add_argument(
        "--objective",
        type=str,
        default=None,
        help="Free-text objective for the handoff",
    )
    parser_hp.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Task ID (defaults to active guard task)",
    )

    # trial subcommand
    parser_trial = subparsers.add_parser("trial", help="Manage value trials")
    trial_sub = parser_trial.add_subparsers(
        dest="trial_command", help="Trial subcommands"
    )

    parser_ts_start = trial_sub.add_parser("start", help="Start a new trial")
    parser_ts_start.add_argument("trial_id", type=str, help="Trial ID")
    parser_ts_start.add_argument("--task", type=str, default="", help="Task title")
    parser_ts_start.add_argument(
        "--track", choices=["manual", "agent-relay"], default="agent-relay"
    )

    parser_ts_event = trial_sub.add_parser("event", help="Record a trial event")
    parser_ts_event.add_argument("trial_id", type=str)
    parser_ts_event.add_argument(
        "event_type",
        choices=[
            "copy",
            "decision",
            "agent_switch",
            "friction",
            "error_caught",
            "artifact",
            "note",
        ],
    )
    parser_ts_event.add_argument("--note", type=str, default=None)
    parser_ts_event.add_argument("--count", type=int, default=1)

    trial_sub.add_parser("stop", help="Stop a trial").add_argument("trial_id", type=str)

    parser_ts_export = trial_sub.add_parser(
        "export", help="Export trial as value-report JSON"
    )
    parser_ts_export.add_argument("trial_id", type=str)
    parser_ts_export.add_argument("--output", type=str, default=None)

    # mcp subcommand
    subparsers.add_parser("mcp", help="Start MCP server (stdin/stdout JSON-RPC)")

    # status subcommand (task-specific, not the board)
    parser_ts = subparsers.add_parser(
        "status", help="Show task board or detailed task status"
    )
    parser_ts.add_argument(
        "task_id",
        type=str,
        nargs="?",
        default=None,
        help="Task ID (e.g. task-001) for detailed view; omit for board",
    )

    # handoff plan subcommand
    parser_handoff_plan = subparsers.add_parser(
        "handoff-plan", help="Preview saved-plan handoff steps for a task"
    )
    parser_handoff_plan.add_argument(
        "task_id", type=str, help="Task ID (e.g. task-001)"
    )

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

    # audit subcommand
    parser_audit = subparsers.add_parser(
        "audit", help="Run config, security & handoff integrity checks"
    )
    parser_audit.add_argument("--json", action="store_true", help="Output raw JSON")

    # launch subcommand
    parser_launch = subparsers.add_parser(
        "launch", help="Preview and confirm a handoff launch"
    )
    parser_launch.add_argument("task_id", type=str, help="Task ID (e.g. task-018)")
    parser_launch.add_argument(
        "--dry-run", action="store_true", help="Preview only, don't launch"
    )
    parser_launch.add_argument(
        "--confirm", action="store_true", help="Skip interactive confirmation"
    )

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
        if args.task_id:
            # Detailed task status
            info = task_status(args.task_id)
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            status_tasks(args)
    elif args.command == "doctor":
        result = doctor()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "value-report":
        sys.exit(value_report(args.filepath))
    elif args.command == "lease":
        result = lease_writer(
            args.agent,
            task_id=args.task_id,
            reason=args.reason,
            force=args.force,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "whoami":
        result = whoami()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "workspace":
        if args.ws_command == "list":
            ws_list = list_workspaces()
            if not ws_list:
                print(
                    "No workspaces registered. Use 'agent-relay workspace add <name> <path>'."
                )
            else:
                default = resolve_workspace()[0]
                print(f"{'Name':<20} {'Path':<50} {'Default':<10}")
                print("-" * 80)
                for name, info in sorted(ws_list.items()):
                    is_def = "✅" if name == default else ""
                    p = info.get("path", "")
                    print(f"{name:<20} {str(p):<50} {is_def:<10}")
        elif args.ws_command == "add":
            result = add_workspace(args.name, args.path, description=args.desc)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.ws_command == "remove":
            remove_workspace(args.name)
            print(f"Removed workspace '{args.name}'.")
        elif args.ws_command == "set-default":
            set_default(args.name)
            print(f"Default workspace set to '{args.name}'.")
        elif args.ws_command == "default":
            name = resolve_workspace()[0]
            if name:
                print(f"Default workspace: {name}")
            else:
                print("No default workspace set.")
        elif args.ws_command == "show":
            info = get_workspace(args.name)
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print("Usage: agent-relay workspace list|add|remove|set-default|show")
    elif args.command == "handoff-prompt":
        result = build_handoff_prompt(
            args.agent,
            task_id=args.task_id,
            objective=args.objective,
        )
        print(result["prompt"])
        print("\n--- context_files ---")
        for f in result.get("context_files", []):
            print(f"  {f}")
    elif args.command == "trial":
        if args.trial_command == "start":
            result = trial_start(args.trial_id, task_title=args.task, track=args.track)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.trial_command == "event":
            result = trial_event(
                args.trial_id, args.event_type, note=args.note, count=args.count
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.trial_command == "stop":
            result = trial_stop(args.trial_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.trial_command == "export":
            result = trial_export(args.trial_id, output_path=args.output)
            if result:
                print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "mcp":
        from agent_relay.mcp_server import run_mcp_server

        run_mcp_server()
    elif args.command == "audit":
        from agent_relay.audit import run_audit

        result = run_audit()
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            s = result["summary"]
            print(
                f"Audit: {s['passed']} passed, {s['warnings']} warnings, {
                    s['failed']
                } failed (score: {s['score']}%)"
            )
            for f in result["findings"]:
                status_sym = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(
                    f["status"], "?"
                )
                detail = f" — {f['detail']}" if f.get("detail") else ""
                print(f"  {status_sym} #{f['rule_id']:02d} {f['title']}{detail}")
    elif args.command == "launch":
        from agent_relay.handoff_envelope import preview_handoff, confirm_and_launch

        if args.dry_run:
            result = preview_handoff(args.task_id)
            if not result["ok"]:
                print(f"❌ {result.get('error', 'checks failed')}")
                for v in result.get("verdicts", []):
                    sym = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(
                        v["status"], "?"
                    )
                    print(f"  {sym} {v['check_id']} {v['title']}: {v['detail']}")
            else:
                p = result["preview"]
                print(f"\U0001f4cb Handoff Preview: {p['handoff_id'][:12]}")
                print(f"   Task:       {p['task_id']}")
                print(f"   From:       {p['from_agent']}")
                print(f"   To:         {p['to_agent']}")
                print(f"   Summary:    {p['summary']}")
                print(f"   Context:    {p['context_preview']}...")
                print(f"   Size:       {p['context_size']} chars")
        else:
            result = confirm_and_launch(args.task_id, confirm=args.confirm)
            action = result.get("action", "error")
            if action == "blocked":
                print(f"\U0001f6ab Launch blocked: {result.get('errors', [])}")
            elif action == "confirm_required":
                print(f"⚠️  Handoff passed all checks. Re-run with --confirm to launch.")
                p = result["preview"]
                print(f"   Will run: {p['to_agent']} on task {p['task_id']}")
            elif action == "launched":
                print(
                    f"\U0001f680 Launched: {
                        result.get('result', {}).get('run_id', '?')
                    }"
                )
            else:
                print(f"❌ {result.get('error', 'unknown error')}")
    elif args.command == "plan":
        plan_task_command(args)
    elif args.command == "route":
        route_command(args)
    elif args.command == "route-task":
        route_task_command(args)
    elif args.command == "run":
        if args.run_command == "add":
            from agent_relay.adapter import add_run_record

            record = add_run_record(
                task_id=args.task_id,
                agent=args.agent,
                role=args.role,
                status=args.status,
                summary=args.summary,
                next_action=getattr(args, "next_action", "manual"),
                files_touched=args.files_touched,
                tests_run=args.tests_run,
                risks=args.risk,
            )
            print(json.dumps(record, indent=2, ensure_ascii=False))
        else:
            print("Usage: agent-relay run add <task-id> [options]")
    elif args.command == "assign":
        assign_command(args)
    elif args.command == "dispatch":
        try:
            import agent_relay.adapter

            record = agent_relay.adapter.dispatch(
                args.task_id, args.agent, mock=getattr(args, "mock", False)
            )
            print(json.dumps(record, indent=2, ensure_ascii=False))
            if record.get("status") == "handoff" and record.get("result", {}).get(
                "instruction"
            ):
                print("\n" + record["result"]["instruction"])
        except Exception as e:
            print(f"Dispatch failed: {e}")
            sys.exit(1)
    elif args.command == "agents":
        report = agents_report()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'Agent':<15} {'Kind':<12} {'Available':<12} {'Supports':<30}")
            print("-" * 70)
            for name, info in sorted(report.items()):
                supports = []
                if info.get("supports_worktree"):
                    supports.append("worktree")
                if info.get("supports_review"):
                    supports.append("review")
                if info.get("supports_write"):
                    supports.append("write")
                avail = "✅" if info.get("available") else "❌"
                print(
                    f"{name:<15} {info.get('kind', ''):<12} {avail:<12} {
                        ', '.join(supports):<30}"
                )
            print()
    elif args.command == "probe":
        if args.target == "all":
            results = probe_all()
        else:
            results = [probe_agent(args.target)]
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.command == "auto":
        auto_command(args)
    elif args.command == "parse-run":
        record = get_run(args.run_id)
        if record is None:
            print(f"Error: Run '{args.run_id}' not found.")
            sys.exit(1)
        parsed = parse_agent_output(
            record.get("result", {}).get("stdout", "")
            or record.get("result", {}).get("full_review", "")
            or record.get("result", {}).get("instruction", "")
            or json.dumps(record.get("parsed_output", {}))
        )
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    elif args.command == "continue":
        try:
            result = continue_after_run(args.run_id, mock=getattr(args, "mock", False))
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Continue failed: {e}")
            sys.exit(1)
    elif args.command == "state":
        task_id = args.task_id
        if args.set:
            try:
                result = set_task_state(task_id, args.set, reason=args.reason)
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"State update failed: {e}")
                sys.exit(1)
        else:
            result = get_task_state(task_id)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Task: {task_id}")
                print(f"  State      : {result.get('state', 'unknown')}")
                print(f"  Previous   : {result.get('previous_state', '-')}")
                print(f"  Reason     : {result.get('reason', '-')}")
                print(f"  Updated    : {result.get('updated_at', '-')}")
                if result.get("source_run_id"):
                    print(f"  Source Run : {result.get('source_run_id')}")
    elif args.command == "policy":
        task_id = args.task_id
        info = get_policy_info(task_id)
        print(json.dumps(info, indent=2, ensure_ascii=False))
    elif args.command == "quality":
        quality = evaluate_task_quality(args.task_id)
        if args.json:
            print(json.dumps(quality, indent=2, ensure_ascii=False))
        else:
            print(f"Task: {quality['task_id']}  State: {quality['state']}")
            print(f"  Ready: {'✅' if quality['ready'] else '❌'}")
            if quality["blocking_issues"]:
                print("  Blocking Issues:")
                for issue in quality["blocking_issues"]:
                    print(f"    - {issue}")
            if quality["warnings"]:
                print("  Warnings:")
                for w in quality["warnings"]:
                    print(f"    ⚠ {w}")
            print(f"  Recommended: {quality['recommended_next_action']}")
            if quality["tests_run"]:
                print(f"  Tests: {'; '.join(quality['tests_run'])}")
            if quality["files_touched"]:
                print(f"  Files: {'; '.join(quality['files_touched'])}")
    elif args.command == "finalize":
        try:
            result = finalize_task(
                args.task_id, dry_run=getattr(args, "dry_run", False)
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Finalize failed: {e}")
            sys.exit(1)
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
            run_cmd(["agent-relay", "status"])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
