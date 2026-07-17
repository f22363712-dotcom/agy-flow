"""Workspace Registry v1 — map workspace names to project directories.

Each workspace is a named entry pointing to an absolute path on disk.
The default workspace is used when no workspace is explicitly specified.
"""

import json
from pathlib import Path

import agent_relay.config
from agent_relay.errors import AgentRelayError

_DEFAULT_REGISTRY = {
    "default": None,
    "workspaces": {},
}

_VALID_KEYS = {"path", "description", "default_tests"}


def _registry_path():
    return agent_relay.config.AGENTS_DIR / "workspaces.json"


def _load():
    path = _registry_path()
    if not path.exists():
        return _default_copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "workspaces" not in data:
            data["workspaces"] = {}
        return data
    except Exception:
        return _default_copy()


def _default_copy():
    return {"default": None, "workspaces": {}}


def _save(data):
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_workspaces():
    """Return dict of ``{name: info, ...}`` for all registered workspaces."""
    data = _load()
    result = {}
    for name, info in data.get("workspaces", {}).items():
        result[name] = {
            "name": name,
            "path": info.get("path", ""),
            "description": info.get("description", ""),
            "default_tests": info.get("default_tests", []),
            "exists": (
                Path(info.get("path", "")).exists() if info.get("path") else False
            ),
        }
    return result


def get_workspace(name):
    """Return info dict for a single workspace, or raise."""
    data = _load()
    ws = data.get("workspaces", {}).get(name)
    if ws is None:
        raise AgentRelayError(
            f"Workspace '{name}' not found. Use 'agent-relay workspace list'."
        )
    return {
        "name": name,
        "path": ws.get("path", ""),
        "description": ws.get("description", ""),
        "default_tests": ws.get("default_tests", []),
        "exists": Path(ws.get("path", "")).exists() if ws.get("path") else False,
    }


def add_workspace(name, path, description="", default_tests=None):
    """Register a new workspace."""
    if not name or " " in name:
        raise AgentRelayError("Workspace name must be non-empty and contain no spaces.")
    abs_path = str(Path(path).resolve())
    data = _load()
    workspaces = data.setdefault("workspaces", {})
    workspaces[name] = {
        "path": abs_path,
        "description": description or "",
        "default_tests": [str(t) for t in (default_tests or [])],
    }
    if data.get("default") is None:
        data["default"] = name
    _save(data)
    return get_workspace(name)


def remove_workspace(name):
    """Unregister a workspace."""
    data = _load()
    workspaces = data.get("workspaces", {})
    if name not in workspaces:
        raise AgentRelayError(f"Workspace '{name}' not found.")
    del workspaces[name]
    if data.get("default") == name:
        keys = list(workspaces.keys())
        data["default"] = keys[0] if keys else None
    _save(data)


def set_default(name):
    """Set the default workspace."""
    data = _load()
    if name is not None and name not in data.get("workspaces", {}):
        raise AgentRelayError(f"Workspace '{name}' not found.")
    data["default"] = name
    _save(data)


def get_default():
    """Return the default workspace name, or None."""
    data = _load()
    return data.get("default")


def resolve_workspace(name=None):
    """Return the (workspace_name, workspace_path) for *name*.

    If *name* is None, uses the default.  If no default is set, returns
    (None, None).
    """
    if name:
        ws = get_workspace(name)
        return name, ws["path"]
    default_name = get_default()
    if default_name:
        ws = get_workspace(default_name)
        return default_name, ws["path"]
    return None, None


def update_module_paths():
    """No-op: kept for config.update_paths compatibility."""
    pass
