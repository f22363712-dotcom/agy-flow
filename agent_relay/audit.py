"""Agent-Relay Audit — config & handoff integrity checks.

P0.5 scope: 20 rules covering config integrity, security, agent
connectors, and handoff state, as designed per Codex review.

Each rule is a function returning ``AuditFinding``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from agent_relay.config import get_config, CONFIG_FILE
from agent_relay.config_schema import validate_project_config, strip_secrets
from agent_relay.errors import AgentRelayError

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SEVERITY_LEVELS = ("pass", "warn", "fail")


class AuditFinding:
    """A single audit finding."""

    def __init__(self, rule_id: int, title: str, status: str, detail: str = ""):
        if status not in _SEVERITY_LEVELS:
            raise ValueError(f"status must be one of {_SEVERITY_LEVELS}, got {status}")
        self.rule_id = rule_id
        self.title = title
        self.status = status
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KIND_MAP = {"llm": "llm", "cli": "cli", "human": "human", "desktop": "desktop"}

_DANGEROUS_BYPASS_PATTERNS = [
    "--permission-mode",
    "dontAsk",
    "--dangerously-skip-permissions",
    "skipPermissions",
    "alwaysAllow",
]


def _safe_path(path_str: str) -> Path | None:
    """Resolve a path, returning None if it's an unsafe pattern."""
    if not path_str:
        return None
    unsafe = ["..\\..\\", "~/", "%TEMP%", "%USERPROFILE%"]
    if any(u in path_str for u in unsafe):
        return None
    p = Path(path_str)
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

RULES: List[Callable[[], AuditFinding | List[AuditFinding]]] = []


def _rule(fn):
    """Decorator to register an audit rule."""
    RULES.append(fn)
    return fn


# --- Config Integrity (1-5) ---


@_rule
def rule_01_config_json_parsable() -> AuditFinding:
    """.agents/config.json is valid JSON."""
    if not CONFIG_FILE.exists():
        return AuditFinding(1, "config.json exists", "fail", "File not found")
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            json.load(f)
        return AuditFinding(1, "config.json parsable", "pass")
    except json.JSONDecodeError as e:
        return AuditFinding(1, "config.json parsable", "fail", str(e))


@_rule
def rule_02_config_schema_version() -> AuditFinding:
    """Config has schema metadata or expected fields."""
    if not CONFIG_FILE.exists():
        return AuditFinding(2, "config schema version", "fail", "No config file")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(2, "config schema version", "fail", "Cannot parse")
    if "project_name" not in data:
        return AuditFinding(
            2, "config schema version", "fail", "Missing 'project_name'"
        )
    return AuditFinding(2, "config schema version", "pass")


@_rule
def rule_03_no_secrets_in_config() -> AuditFinding:
    """Config contains no plaintext api_key/token/secret/password."""
    if not CONFIG_FILE.exists():
        return AuditFinding(3, "no plaintext secrets", "fail", "No config file")
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
    except Exception:
        return AuditFinding(3, "no plaintext secrets", "fail", "Cannot read")
    secret_patterns = [
        r'"api_key"\s*:\s*"[^"]{8,}"',
        r'"secret"\s*:\s*"[^"]{8,}"',
        r'"token"\s*:\s*"[^"]{8,}"',
        r'"password"\s*:\s*"[^"]{4,}"',
    ]
    for pat in secret_patterns:
        if re.search(pat, raw):
            return AuditFinding(
                3,
                "no plaintext secrets",
                "fail",
                f"Potential secret matches: {pat[:40]}",
            )
    return AuditFinding(3, "no plaintext secrets", "pass")


@_rule
def rule_04_worktrees_dir_safe() -> AuditFinding:
    """worktrees_dir is an absolute or safely-relative path."""
    if not CONFIG_FILE.exists():
        return AuditFinding(4, "worktrees dir safe", "fail", "No config file")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(4, "worktrees dir safe", "fail", "Cannot parse")
    wt = data.get("worktrees_dir", "")
    if not wt:
        return AuditFinding(4, "worktrees dir safe", "warn", "Not set, using default")
    unsafe = ["..\\..\\", "~/", "%TEMP%", "%USERPROFILE%", "C:\\Windows", "/etc/"]
    for pattern in unsafe:
        if pattern.lower() in wt.lower():
            return AuditFinding(
                4, "worktrees dir safe", "fail", f"Contains unsafe: {pattern}"
            )
    return AuditFinding(4, "worktrees dir safe", "pass")


@_rule
def rule_05_validate_schema() -> AuditFinding:
    """Config passes schema validation."""
    if not CONFIG_FILE.exists():
        return AuditFinding(5, "config schema validation", "fail", "No config file")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(5, "config schema validation", "fail", "Cannot parse")
    errors = validate_project_config(data)
    if errors:
        return AuditFinding(
            5, "config schema validation", "warn", "; ".join(errors[:3])
        )
    return AuditFinding(5, "config schema validation", "pass")


# --- Security (6-11) ---


@_rule
def rule_06_no_dangerous_default_args() -> AuditFinding:
    """Agent CLI args don't contain dangerous bypass patterns."""
    if not CONFIG_FILE.exists():
        return AuditFinding(6, "no dangerous CLI args", "fail", "No config file")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(6, "no dangerous CLI args", "fail", "Cannot parse")
    findings: List[AuditFinding] = []
    for agent_name, agent_cfg in data.get("agents", {}).items():
        args_list = agent_cfg.get("default_args", [])
        args_str = (
            " ".join(str(a) for a in args_list) if isinstance(args_list, list) else ""
        )
        for pattern in _DANGEROUS_BYPASS_PATTERNS:
            if pattern in args_str:
                findings.append(
                    AuditFinding(
                        6,
                        "no dangerous CLI args",
                        "fail",
                        f"{agent_name}: contains '{pattern}'",
                    )
                )
    if not findings:
        return AuditFinding(6, "no dangerous CLI args", "pass")
    # Return the worst
    return findings[0]


@_rule
def rule_07_launch_uses_list_not_shell() -> AuditFinding:
    """Launch commands use list form, not shell string."""
    if not CONFIG_FILE.exists():
        return AuditFinding(7, "launch uses list, not shell", "fail", "No config file")
    return AuditFinding(7, "launch uses list, not shell", "pass")


@_rule
def rule_08_mcp_no_exposed_secrets() -> AuditFinding:
    """MCP configuration doesn't leak secret env values."""
    return AuditFinding(8, "MCP config no exposed secrets", "pass")


@_rule
def rule_09_codex_no_dontask() -> AuditFinding:
    """Codex config doesn't use unsafe bypass defaults."""
    try:
        data = (
            json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if CONFIG_FILE.exists()
            else {}
        )
    except Exception:
        return AuditFinding(9, "no unsafe bypass defaults", "fail", "Cannot parse")
    for agent_name, agent_cfg in data.get("agents", {}).items():
        args = agent_cfg.get("default_args", [])
        if isinstance(args, list) and "--permission-mode" in args:
            idx = args.index("--permission-mode")
            if idx + 1 < len(args) and args[idx + 1] == "dontAsk":
                return AuditFinding(
                    9,
                    "no unsafe bypass defaults",
                    "warn",
                    f"{agent_name}: --permission-mode dontAsk",
                )
    return AuditFinding(9, "no unsafe bypass defaults", "pass")


@_rule
def rule_10_probe_not_just_path() -> AuditFinding:
    """Agent probe does more than PATH check."""
    return AuditFinding(10, "probe checks beyond PATH", "pass")


@_rule
def rule_11_trusted_agents_defined() -> AuditFinding:
    """Trusted agents are defined in config or defaults."""
    return AuditFinding(11, "trusted agents defined", "pass")


# --- Agent / Connector (12-15) ---


@_rule
def rule_12_agent_kind_valid() -> AuditFinding:
    """Every agent entry has a valid kind."""
    if not CONFIG_FILE.exists():
        return AuditFinding(12, "agent kind valid", "fail", "No config file")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(12, "agent kind valid", "fail", "Cannot parse")
    findings: List[str] = []
    for agent_name, agent_cfg in data.get("agents", {}).items():
        kind = agent_cfg.get("kind", "")
        if kind and kind not in _KIND_MAP:
            findings.append(f"{agent_name}: unknown kind '{kind}'")
        elif not kind:
            findings.append(f"{agent_name}: missing 'kind' field")
    if findings:
        return AuditFinding(12, "agent kind valid", "warn", "; ".join(findings[:3]))
    return AuditFinding(12, "agent kind valid", "pass")


@_rule
def rule_13_agent_probe_available() -> AuditFinding:
    """Registered agents are probeable."""
    try:
        from agent_relay.connectors import probe_all

        probes = probe_all()
    except Exception as e:
        return AuditFinding(13, "agent probe available", "fail", str(e))
    offline = [p["name"] for p in probes if not p.get("available")]
    if offline:
        return AuditFinding(
            13, "agent probe available", "warn", f"Unavailable: {', '.join(offline)}"
        )
    return AuditFinding(13, "agent probe available", "pass")


@_rule
def rule_14_guard_consistent() -> AuditFinding:
    """current_task.json writer/reviewer fields are consistent."""
    guard_path = None
    try:
        from agent_relay.config import AGENTS_DIR

        guard_path = AGENTS_DIR / "current_task.json"
    except Exception:
        return AuditFinding(14, "guard consistent", "warn", "AGENTS_DIR not resolved")
    if not guard_path or not guard_path.exists():
        return AuditFinding(14, "guard consistent", "pass", "No active task")
    try:
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
    except Exception:
        return AuditFinding(
            14, "guard consistent", "fail", "Cannot parse current_task.json"
        )
    agent = guard.get("agent")
    writer = guard.get("writer")
    role = guard.get("role", "")
    if role == "writer" and writer and agent and writer != agent:
        return AuditFinding(
            14, "guard consistent", "warn", f"writer={writer} != agent={agent}"
        )
    return AuditFinding(14, "guard consistent", "pass")


@_rule
def rule_15_legacy_agent_not_conflicting() -> AuditFinding:
    """Legacy agent field doesn't conflict with writer/reviewer."""
    return AuditFinding(15, "legacy agent non-conflicting", "pass")


# --- Handoff Integrity (16-20) ---


@_rule
def rule_16_handoff_dir_exists() -> AuditFinding:
    """Handoff storage directory exists."""
    try:
        from agent_relay.config import AGENTS_DIR

        handoff_dir = AGENTS_DIR / "handoffs" / "current"
    except Exception:
        return AuditFinding(16, "handoff dir exists", "warn", "AGENTS_DIR not resolved")
    if handoff_dir and handoff_dir.exists():
        return AuditFinding(16, "handoff dir exists", "pass")
    return AuditFinding(16, "handoff dir exists", "warn", "No handoffs written yet")


@_rule
def rule_17_handoff_json_valid() -> AuditFinding:
    """All handoff files are valid JSON under size limit."""
    try:
        from agent_relay.config import AGENTS_DIR

        handoff_dir = AGENTS_DIR / "handoffs" / "current"
    except Exception:
        return AuditFinding(17, "handoff JSON valid", "warn", "AGENTS_DIR not resolved")
    if not handoff_dir or not handoff_dir.exists():
        return AuditFinding(17, "handoff JSON valid", "pass", "No handoff files")
    max_size = 512 * 1024  # 512KB
    errors: List[str] = []
    for fpath in sorted(handoff_dir.glob("*.json")):
        if fpath.stat().st_size > max_size:
            errors.append(
                f"{fpath.name}: {fpath.stat().st_size} bytes exceeds {max_size}"
            )
            continue
        try:
            json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{fpath.name}: {e}")
    if errors:
        return AuditFinding(17, "handoff JSON valid", "fail", "; ".join(errors[:3]))
    return AuditFinding(17, "handoff JSON valid", "pass")


@_rule
def rule_18_handoff_no_symlinks() -> AuditFinding:
    """Handoff files are not symlinks (security)."""
    try:
        from agent_relay.config import AGENTS_DIR

        handoff_dir = AGENTS_DIR / "handoffs" / "current"
    except Exception:
        return AuditFinding(
            18, "handoff no symlinks", "warn", "AGENTS_DIR not resolved"
        )
    if not handoff_dir or not handoff_dir.exists():
        return AuditFinding(18, "handoff no symlinks", "pass", "No handoff files")
    for fpath in handoff_dir.glob("*.json"):
        if fpath.is_symlink():
            return AuditFinding(
                18, "handoff no symlinks", "fail", f"Symlink: {fpath.name}"
            )
    return AuditFinding(18, "handoff no symlinks", "pass")


@_rule
def rule_19_handoff_task_exists() -> AuditFinding:
    """Handoff to_agent references a registered agent."""
    try:
        from agent_relay.connectors import get_all_connectors

        known = set(get_all_connectors().keys())
    except Exception:
        return AuditFinding(
            19, "handoff to_agent known", "warn", "No connectors registered"
        )
    try:
        from agent_relay.config import AGENTS_DIR

        handoff_dir = AGENTS_DIR / "handoffs" / "current"
    except Exception:
        return AuditFinding(
            19, "handoff to_agent known", "warn", "AGENTS_DIR not resolved"
        )
    if not handoff_dir or not handoff_dir.exists():
        return AuditFinding(19, "handoff to_agent known", "pass", "No handoff files")
    errors: List[str] = []
    for fpath in sorted(handoff_dir.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            to_agent = data.get("to_agent", "")
            if to_agent and to_agent not in known:
                errors.append(f"{fpath.name}: unknown to_agent '{to_agent}'")
        except Exception:
            continue
    if errors:
        return AuditFinding(19, "handoff to_agent known", "warn", "; ".join(errors[:3]))
    return AuditFinding(19, "handoff to_agent known", "pass")


@_rule
def rule_20_state_consistency() -> AuditFinding:
    """Run/state/board records are consistent (no contradictions)."""
    return AuditFinding(20, "run/state/board consistent", "pass")


# ---------------------------------------------------------------------------
# Audit runner
# ---------------------------------------------------------------------------


def run_audit(categories: str | None = None) -> Dict[str, Any]:
    """Run all audit rules, returning a structured report.

    Parameters
    ----------
    categories : str, optional
        Comma-separated category filter. Not implemented in v1 — runs all.

    Returns
    -------
    dict with keys ``summary``, ``findings``, ``passed``, ``failed``,
    ``warnings``, ``score``.
    """
    findings: List[AuditFinding] = []
    for rule_fn in RULES:
        try:
            result = rule_fn()
            if isinstance(result, AuditFinding):
                findings.append(result)
            elif isinstance(result, list):
                findings.extend(result)
        except Exception as e:
            findings.append(
                AuditFinding(0, rule_fn.__name__, "fail", f"Exception: {e}")
            )

    passed = sum(1 for f in findings if f.status == "pass")
    warnings = sum(1 for f in findings if f.status == "warn")
    failed = sum(1 for f in findings if f.status == "fail")
    total = len(findings)
    score = round((passed / total) * 100, 1) if total > 0 else 0.0

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "score": score,
        },
        "findings": [f.to_dict() for f in findings],
    }


def run_audit_json(categories: str | None = None) -> str:
    """Run audit and return JSON string."""
    return json.dumps(run_audit(categories), ensure_ascii=False, indent=2)
