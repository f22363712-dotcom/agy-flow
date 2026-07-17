import os
import sys
import json
from pathlib import Path
from agent_relay_classify import DEFAULT_AGENT_REGISTRY

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
        "deepseek": {
            "provider": "litellm",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key_env": "DEEPSEEK_API_KEY",
            "capabilities": ["cheap_analysis", "planning", "review"],
        },
    },
    "agent_registry": DEFAULT_AGENT_REGISTRY,
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


PROJECT_ROOT = None
AGENTS_DIR = None
TASKS_DIR = None
TEMPLATES_DIR = None
LOGS_DIR = None
CONFIG_FILE = None
BOARD_FILE = None
COSTS_FILE = None
RUNS_DIR = None


def update_paths(new_root=None):
    global \
        PROJECT_ROOT, \
        AGENTS_DIR, \
        TASKS_DIR, \
        TEMPLATES_DIR, \
        LOGS_DIR, \
        CONFIG_FILE, \
        BOARD_FILE, \
        COSTS_FILE, \
        RUNS_DIR
    if new_root is not None:
        PROJECT_ROOT = Path(new_root).resolve()
    else:
        PROJECT_ROOT = find_project_root()
        if PROJECT_ROOT is None:
            PROJECT_ROOT = Path.cwd().resolve()

    AGENTS_DIR = PROJECT_ROOT / ".agents"
    TASKS_DIR = AGENTS_DIR / "tasks"
    TEMPLATES_DIR = AGENTS_DIR / "templates"
    LOGS_DIR = AGENTS_DIR / "logs"
    CONFIG_FILE = AGENTS_DIR / "config.json"
    BOARD_FILE = TASKS_DIR / "board.md"
    COSTS_FILE = AGENTS_DIR / "costs.json"
    RUNS_DIR = AGENTS_DIR / "runs"

    # Notify other submodules to synchronize their path references
    try:
        import agent_relay.tasks

        agent_relay.tasks.update_module_paths()
    except (ImportError, AttributeError):
        pass
    try:
        import agent_relay.handoff

        agent_relay.handoff.update_module_paths()
    except (ImportError, AttributeError):
        pass
    try:
        import agent_relay.llm

        agent_relay.llm.update_module_paths()
    except (ImportError, AttributeError):
        pass
    try:
        import agent_relay.adapter

        agent_relay.adapter.update_module_paths()
    except (ImportError, AttributeError):
        pass
    try:
        import agent_relay.connectors

        agent_relay.connectors.update_module_paths()
    except (ImportError, AttributeError):
        pass
    try:
        import agent_relay.workspaces

        agent_relay.workspaces.update_module_paths()
    except (ImportError, AttributeError):
        pass


# Initialize default paths
update_paths()

PRICING = {
    "claude": {"input": 0.14 / 1000000, "output": 0.28 / 1000000},
    "antigravity": {"input": 0.075 / 1000000, "output": 0.30 / 1000000},
    "codex": {"input": 0.0, "output": 0.0},
    "deepseek": {"input": 0.14 / 1000000, "output": 0.28 / 1000000},
}


def get_config():
    """Loads and returns the configuration json."""
    if not CONFIG_FILE.exists():
        print(
            f"Error: Config file not found at {CONFIG_FILE}. Run 'agent-relay init' first."
        )
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_agent_registry(config=None):
    """Returns configured agent capabilities, falling back to built-in defaults."""
    config = config or (get_config() if CONFIG_FILE.exists() else {})
    return config.get("agent_registry") or DEFAULT_AGENT_REGISTRY


def get_llm_agent_settings(agent, config=None):
    """Resolve OpenAI-compatible settings for an LLM API agent."""
    config = config or get_config()
    runtime_config = config.get("agents", {}).get(agent, {})
    registry_config = get_agent_registry(config).get(agent, {})

    if registry_config.get("kind") != "llm_api" and runtime_config.get(
        "provider"
    ) not in {
        "litellm",
        "openai_compatible",
    }:
        print(f"Error: Agent '{agent}' is not configured as an LLM API agent.")
        sys.exit(1)

    agent_prefix = agent.upper().replace("-", "_")
    base_url = (
        os.environ.get(f"{agent_prefix}_BASE_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or runtime_config.get("base_url")
        or registry_config.get("base_url")
        or "https://api.deepseek.com/v1"
    )
    model = (
        os.environ.get(f"{agent_prefix}_MODEL")
        or runtime_config.get("model")
        or registry_config.get("model")
        or "deepseek-chat"
    )
    api_key_env = (
        runtime_config.get("api_key_env")
        or registry_config.get("api_key_env")
        or f"{agent_prefix}_API_KEY"
    )
    api_key = os.environ.get(api_key_env)
    if not api_key and agent == "deepseek":
        api_key = os.environ.get("LITELLM_API_KEY")
        if api_key:
            api_key_env = "LITELLM_API_KEY"

    return {
        "agent": agent,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key_env": api_key_env,
        "api_key": api_key,
    }


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
