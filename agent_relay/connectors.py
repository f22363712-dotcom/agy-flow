"""Agent Connectors v0 — detect and describe external agent runtimes.

Each connector probes whether a given agent runtime is available on the
current system (CLI in PATH, API key in environment, etc.) without
launching or controlling the agent itself.
"""

import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from agent_relay.config import get_config, get_agent_registry
from agent_relay.errors import AgentRelayError

# ---------------------------------------------------------------------------
# Built-in capability / kind maps
# ---------------------------------------------------------------------------

AGENT_META = {
    "deepseek": {
        "display_name": "DeepSeek",
        "kind": "llm",
        "capabilities": ["cheap_analysis", "planning", "review", "classification"],
        "supports_worktree": False,
        "supports_review": True,
        "supports_write": False,
    },
    "claude": {
        "display_name": "Claude Code",
        "kind": "cli",
        "capabilities": ["code_edit", "logic", "test", "refactor", "review"],
        "supports_worktree": True,
        "supports_review": True,
        "supports_write": True,
    },
    "codex": {
        "display_name": "Codex",
        "kind": "human",
        "capabilities": ["code_edit", "debug", "review", "manual_tuning"],
        "supports_worktree": True,
        "supports_review": True,
        "supports_write": True,
    },
    "antigravity": {
        "display_name": "Antigravity",
        "kind": "desktop",
        "capabilities": ["vision", "browser", "ui_review", "large_context"],
        "supports_worktree": True,
        "supports_review": True,
        "supports_write": True,
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "kind": "cli",
        "capabilities": ["analysis", "review", "code_gen"],
        "supports_worktree": False,
        "supports_review": True,
        "supports_write": False,
    },
}


# ---------------------------------------------------------------------------
# Abstract connector
# ---------------------------------------------------------------------------


class AgentConnector(ABC):
    """Abstract connector for an external agent runtime.

    Subclasses override :meth:`_check_availability` to probe the
    environment and return a dict with ``available`` and ``reason``.
    """

    name = ""

    @property
    @abstractmethod
    def kind(self):
        """One of ``llm | cli | human | desktop``."""

    def is_available(self):
        """Return ``{"available": bool, "reason": str}``."""
        return self._check_availability()

    @abstractmethod
    def _check_availability(self): ...

    def capabilities(self):
        return AGENT_META.get(self.name, {}).get("capabilities", [])

    def prepare_dispatch(self, task_id, role="writer", **kwargs):
        """Return dispatch-ready metadata.

        Subclasses may override to inject connector-specific params.
        """
        avail = self.is_available()
        return {
            "connector": self.name,
            "kind": self.kind,
            "available": avail["available"],
            "reason": avail["reason"],
            "task_id": task_id,
            "role": role,
        }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _find_cli(name):
    """Return path to *name* on PATH, or ``None``."""
    return shutil.which(name)


def _check_env_var(var):
    """Return the value of *var*, or ``None``."""
    return os.environ.get(var)


# ---------------------------------------------------------------------------
# Built-in connectors
# ---------------------------------------------------------------------------


class DeepSeekConnector(AgentConnector):
    name = "deepseek"

    @property
    def kind(self):
        return "llm"

    def _check_availability(self):
        if _check_env_var("DEEPSEEK_API_KEY"):
            return {"available": True, "reason": "DEEPSEEK_API_KEY is set"}
        if _check_env_var("LITELLM_API_KEY"):
            return {"available": True, "reason": "LITELLM_API_KEY is set"}
        return {
            "available": False,
            "reason": "Neither DEEPSEEK_API_KEY nor LITELLM_API_KEY is set",
        }


class ClaudeConnector(AgentConnector):
    name = "claude"

    @property
    def kind(self):
        return "cli"

    def _check_availability(self):
        if _find_cli("claude"):
            return {"available": True, "reason": "claude CLI found on PATH"}
        return {
            "available": False,
            "reason": "claude CLI not found on PATH. Install Claude Code.",
        }


class CodexConnector(AgentConnector):
    name = "codex"

    @property
    def kind(self):
        return "human"

    def _check_availability(self):
        if _find_cli("codex"):
            return {"available": True, "reason": "codex CLI found on PATH"}
        return {
            "available": True,
            "reason": "codex CLI not found — human-in-loop handoff still works",
        }


class AntigravityConnector(AgentConnector):
    name = "antigravity"

    @property
    def kind(self):
        return "desktop"

    def _check_availability(self):
        if _find_cli("antigravity"):
            return {"available": True, "reason": "antigravity CLI found on PATH"}
        return {
            "available": True,
            "reason": "antigravity CLI not found — desktop handoff still works",
        }


class GeminiConnector(AgentConnector):
    name = "gemini"

    @property
    def kind(self):
        return "cli"

    def _check_availability(self):
        if _find_cli("gemini"):
            return {"available": True, "reason": "gemini CLI found on PATH"}
        return {
            "available": False,
            "reason": "gemini CLI not found on PATH. Install Google Gemini CLI.",
        }


# ---------------------------------------------------------------------------
# Registry and factory
# ---------------------------------------------------------------------------

_CONNECTORS = {}


def register_connector(connector):
    """Register a connector *instance* by its ``name``."""
    _CONNECTORS[connector.name] = connector


def get_connector(name):
    """Return the registered connector for *name*, or raise."""
    if name not in _CONNECTORS:
        available = ", ".join(sorted(_CONNECTORS))
        raise AgentRelayError(
            f"No connector registered for '{name}'. Available: {available}"
        )
    return _CONNECTORS[name]


def get_all_connectors():
    """Return dict of ``{name: connector, ...}``."""
    return dict(_CONNECTORS)


# Register built-in connectors
for _cls in (
    DeepSeekConnector,
    ClaudeConnector,
    CodexConnector,
    AntigravityConnector,
    GeminiConnector,
):
    register_connector(_cls())


# ---------------------------------------------------------------------------
# Probe utilities
# ---------------------------------------------------------------------------


def probe_agent(name):
    """Probe a single agent and return a structured report.

    Returns
    -------
    dict with keys: ``name``, ``kind``, ``display_name``, ``available``,
    ``reason``, ``capabilities``, ``config``, ``executable_path``,
    ``supports_cli`` (merged from agent_registry).
    """
    connector = get_connector(name)
    avail = connector.is_available()
    registry = get_agent_registry(get_config())
    config_entry = registry.get(name, {})
    meta = AGENT_META.get(name, {})
    is_cli = connector.kind == "cli"

    # Resolve executable path
    exec_path = None
    cli_name = config_entry.get("cli_command") or name
    # Check if this agent supports CLI launch
    if connector.kind in ("cli", "human"):  # human (codex) may also have CLI
        exec_path = _find_cli(cli_name)

    return {
        "name": name,
        "kind": connector.kind,
        "display_name": meta.get("display_name", name.capitalize()),
        "available": avail["available"],
        "reason": avail["reason"],
        "executable_path": str(exec_path) if exec_path else None,
        "executable": exec_path is not None,  # backwards compat
        "supports_cli": exec_path is not None,
        "capabilities": config_entry.get("capabilities", meta.get("capabilities", [])),
        "supports_worktree": config_entry.get(
            "supports_worktree", meta.get("supports_worktree", False)
        ),
        "supports_review": config_entry.get(
            "supports_review", meta.get("supports_review", False)
        ),
        "supports_write": config_entry.get(
            "supports_write", meta.get("supports_write", False)
        ),
        "config": {
            k: v
            for k, v in config_entry.items()
            if not any(
                x in k.lower() for x in ("api_key", "secret", "token", "password")
            )
        },
    }


def probe_all():
    """Probe every registered connector.  Returns a list of reports."""
    return [probe_agent(name) for name in sorted(_CONNECTORS)]


def agents_report():
    """Full agents report combining registry + connector probes."""
    registry = get_agent_registry(get_config())
    probes = {r["name"]: r for r in probe_all()}
    report = {}
    for name, entry in registry.items():
        probe = probes.get(name, {})
        report[name] = {
            "display_name": entry.get("display_name", name.capitalize()),
            "kind": entry.get("kind", probe.get("kind", "unknown")),
            "available": probe.get("available", False),
            "reason": probe.get("reason", "No connector registered"),
            "executable": probe.get("executable", False),
            "executable_path": probe.get("executable_path"),
            "supports_cli": probe.get("supports_cli", False),
            "capabilities": entry.get("capabilities", probe.get("capabilities", [])),
            "supports_worktree": entry.get(
                "supports_worktree", probe.get("supports_worktree", False)
            ),
            "supports_review": entry.get(
                "supports_review", probe.get("supports_review", False)
            ),
            "supports_write": entry.get(
                "supports_write", probe.get("supports_write", False)
            ),
        }
    # Add any connector-only agents not in registry
    for name, probe in probes.items():
        if name not in report:
            report[name] = probe
    return report


def update_module_paths():
    """No-op: kept for config.update_paths compatibility."""
    pass
