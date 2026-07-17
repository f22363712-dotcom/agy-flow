#!/usr/bin/env python3
import sys

# Facade wrapper importing all modules for backward compatibility (Phase D)
from agent_relay.errors import AgentRelayError
from agent_relay.git_ops import run_cmd
from agent_relay.config import (
    DEFAULT_CONFIG,
    DEFAULT_BOARD_TEMPLATE,
    DEFAULT_TASK_TEMPLATE,
    PRICING,
    find_project_root,
    PROJECT_ROOT,
    AGENTS_DIR,
    TASKS_DIR,
    TEMPLATES_DIR,
    LOGS_DIR,
    CONFIG_FILE,
    BOARD_FILE,
    COSTS_FILE,
    get_config,
    get_agent_registry,
    get_llm_agent_settings,
    load_costs,
    save_costs,
)
from agent_relay.router import plan_task_command
from agent_relay.handoff import (
    load_task_plan,
    get_handoff_steps,
    find_next_handoff_step,
    assign_current_task_agent,
    assign_command,
    handoff_plan_command,
    canonical_assignment_agent,
)
from agent_relay.llm import (
    truncate_text,
    call_openai_compatible_chat,
    ask_agent_command,
    review_task_command,
)
from agent_relay.tasks import (
    load_board,
    save_board,
    parse_board_rows,
    update_board_row,
    create_task,
    start_task,
    submit_task,
    merge_task,
    status_tasks,
    estimate_and_log_cost,
    format_plan_summary,
    check_inside_project,
    init_project,
)
from agent_relay.gateway import (
    DASHBOARD_HTML,
    AgentRelayHTTPHandler,
    serve_gateway,
)
from agent_relay.cli import main

if __name__ == "__main__":
    main()
