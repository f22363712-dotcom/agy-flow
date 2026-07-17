"""Config Schema v1 — validate .agents/config.json and build effective config.

P0 scope:
  1. Validate project config structure and extension fields
  2. Build effective config: merge DEFAULT_CONFIG + project + probe
  3. Strip secrets before exposing via MCP
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_CONFIG_V1_REQUIRED_FIELDS = {
    "project_name": str,
}

_AGENT_REQUIRED_FIELDS = ["kind"]
_AGENT_VALID_KINDS = {"llm", "cli", "human", "desktop"}

_SECRET_KEYS = {"api_key", "secret", "token", "password"}

_WORKTREES_DIR_UNSAFE_PATTERNS = [
    "..\\..\\",
    "~/",
    "%USERPROFILE%",
    "%TEMP%",
    "C:\\Windows",
    "C:\\Program Files",
    "/etc/",
    "/usr/",
]


def _has_secret_key(key: str) -> bool:
    key_lower = key.lower()
    return any(s in key_lower for s in _SECRET_KEYS)


def _is_unsafe_worktrees(path: str) -> str | None:
    for pattern in _WORKTREES_DIR_UNSAFE_PATTERNS:
        if pattern in path:
            return f"worktrees_dir contains unsafe pattern: {pattern}"
    return None


def validate_project_config(
    data: Dict[str, Any],
) -> List[str]:
    """Validate a project config dict, returning a list of error messages.

    Checks:
    - Required top-level fields
    - Agent entries have kind + valid kind
    - Agent entries have capabilities (if provided)
    - No API keys stored directly in config
    - worktrees_dir is safe
    """
    errors: List[str] = []

    # Required fields
    for field, expected_type in _CONFIG_V1_REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}' should be {expected_type.__name__}, got {
                    type(data[field]).__name__
                }"
            )

    # No secrets at top level
    for key in data:
        if _has_secret_key(key):
            errors.append(f"Config contains potential secret at top level: '{key}'")

    # Agent entries
    agents = data.get("agents", {})
    if agents and not isinstance(agents, dict):
        errors.append("'agents' must be a dict")
    else:
        for agent_name, agent_cfg in agents.items():
            if not isinstance(agent_cfg, dict):
                errors.append(f"agents.{agent_name} must be a dict")
                continue

            # Required agent fields
            for req_field in _AGENT_REQUIRED_FIELDS:
                if req_field not in agent_cfg:
                    errors.append(
                        f"agents.{agent_name} missing required field: '{req_field}'"
                    )

            # Valid kind
            kind = agent_cfg.get("kind")
            if kind and kind not in _AGENT_VALID_KINDS:
                errors.append(
                    f"agents.{agent_name}.kind '{kind}' not in {_AGENT_VALID_KINDS}"
                )

            # Capabilities (if present)
            caps = agent_cfg.get("capabilities")
            if caps is not None and not isinstance(caps, list):
                errors.append(f"agents.{agent_name}.capabilities must be a list")

            # No secrets in agent config
            for key in agent_cfg:
                if _has_secret_key(key):
                    errors.append(f"agents.{agent_name} contains secret field: '{key}'")

    # worktrees_dir safety
    wt = data.get("worktrees_dir", "")
    if isinstance(wt, str) and wt:
        unsafe = _is_unsafe_worktrees(wt)
        if unsafe:
            errors.append(unsafe)

    return errors


# ---------------------------------------------------------------------------
# Strip secrets
# ---------------------------------------------------------------------------


def strip_secrets(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *data* with secret values masked.

    Recursively walks the dict and replaces values of keys matching
    ``api_key``, ``secret``, ``token``, ``password`` with ``"__REDACTED__"``.
    """
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if _has_secret_key(key) and isinstance(value, str) and value:
            result[key] = "__REDACTED__"
        elif isinstance(value, dict):
            result[key] = strip_secrets(value)
        elif isinstance(value, list):
            result[key] = [
                strip_secrets(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Effective config builder
# ---------------------------------------------------------------------------


def build_effective_config(
    project_config: Dict[str, Any] | None = None,
    probes: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Merge DEFAULT_CONFIG + project config + runtime probes into one dict.

    Layers (later wins):
      1. DEFAULT_CONFIG (built-in defaults)
      2. project_config (from .agents/config.json)
      3. probes (runtime detection results)

    Returns a dict safe to expose over MCP (secrets stripped).
    """
    from agent_relay.config import DEFAULT_CONFIG

    effective = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

    # Layer 2: project config
    if project_config:
        _deep_merge(effective, project_config)

    # Layer 3: probe results merged into agent entries
    if probes:
        agents = effective.setdefault("agents", {})
        for agent_name, probe in probes.items():
            if agent_name not in agents:
                agents[agent_name] = {}
            agents[agent_name]["probe"] = {
                "available": probe.get("available", False),
                "reason": probe.get("reason", ""),
                "executable_path": probe.get("executable_path"),
                "supports_cli": probe.get("supports_cli", False),
                "supports_worktree": probe.get("supports_worktree", False),
                "supports_review": probe.get("supports_review", False),
                "supports_write": probe.get("supports_write", False),
            }
            # Update capabilities from probe if config doesn't have them
            if not agents[agent_name].get("capabilities"):
                agents[agent_name]["capabilities"] = probe.get("capabilities", [])

    # Add schema metadata
    effective["schema_version"] = "1"
    effective["config_source"] = "merged"

    return strip_secrets(effective)


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    """Recursive dict merge: *overlay* values overwrite *base*."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
