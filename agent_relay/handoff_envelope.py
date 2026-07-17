"""Handoff Envelope v1 — schema validation & security checks for handoffs.

P1 scope: validate a handoff before launching the target agent.
Each check returns an ``EnvelopeVerdict`` with pass/fail/warn status.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent_relay.errors import AgentRelayError

from agent_relay.mcp_handoff_store import HandoffContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HANDOFF_SIZE = 512 * 1024  # 512 KB
MAX_CONTEXT_SIZE = 200_000  # ~200K chars for context text
VALID_ENVELOPE_VERSIONS = {"1"}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SEVERITY = ("pass", "warn", "fail")


class EnvelopeVerdict:
    """Result of a single envelope check."""

    def __init__(self, check_id: str, title: str, status: str, detail: str = ""):
        if status not in _SEVERITY:
            raise ValueError(f"status must be in {_SEVERITY}, got {status}")
        self.check_id = check_id
        self.title = title
        self.status = status
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class LaunchPreview:
    """Preview of what would happen if the handoff is launched."""

    handoff_id: str
    task_id: str
    from_agent: str
    to_agent: str
    role: str  # derived from handoff or guard context
    summary: str
    context_preview: str  # first 200 chars
    context_size: int
    commit_hash: str | None
    allowed_actions: list[str] | None
    launch_command: str  # human-readable command summary
    verdicts: List[EnvelopeVerdict]
    passed: bool
    warnings: List[str]
    errors: List[str]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_envelope_version(ctx: HandoffContext) -> EnvelopeVerdict:
    """schema_version is a known value."""
    ver = ctx.schema_version or ""
    if ver in VALID_ENVELOPE_VERSIONS:
        return EnvelopeVerdict("ev-01", "envelope version", "pass", f"v{ver}")
    return EnvelopeVerdict(
        "ev-01", "envelope version", "fail", f"Unknown version: {ver}"
    )


def check_context_size(ctx: HandoffContext) -> EnvelopeVerdict:
    """context size does not exceed limit."""
    size = len(ctx.context) if ctx.context else 0
    if size <= MAX_CONTEXT_SIZE:
        return EnvelopeVerdict("ev-02", "context size", "pass", f"{size} chars")
    return EnvelopeVerdict(
        "ev-02",
        "context size",
        "fail",
        f"{size} chars exceeds {MAX_CONTEXT_SIZE}",
    )


def check_context_sha256(ctx: HandoffContext) -> EnvelopeVerdict:
    """context_sha256 matches actual context content."""
    if not ctx.context:
        return EnvelopeVerdict("ev-03", "context checksum", "pass", "no context")
    if not ctx.context_sha256:
        return EnvelopeVerdict("ev-03", "context checksum", "warn", "sha256 not set")
    actual = hashlib.sha256(ctx.context.encode()).hexdigest()
    if actual == ctx.context_sha256:
        return EnvelopeVerdict("ev-03", "context checksum", "pass")
    return EnvelopeVerdict(
        "ev-03", "context checksum", "fail", "sha256 mismatch — context may be tampered"
    )


def check_to_agent_registered(ctx: HandoffContext) -> EnvelopeVerdict:
    """to_agent is a known registered agent."""
    try:
        from agent_relay.connectors import get_all_connectors

        known = set(get_all_connectors().keys())
    except Exception:
        return EnvelopeVerdict(
            "ev-04", "to_agent registered", "warn", "connectors unavailable"
        )
    if ctx.to_agent in known:
        return EnvelopeVerdict("ev-04", "to_agent registered", "pass", ctx.to_agent)
    return EnvelopeVerdict(
        "ev-04", "to_agent registered", "fail", f"Unknown target: {ctx.to_agent}"
    )


def check_from_agent_authorized(ctx: HandoffContext) -> EnvelopeVerdict:
    """from_agent is the current writer or a reviewer."""
    try:
        from agent_relay.handoff import whoami

        guard = whoami()
    except Exception:
        return EnvelopeVerdict(
            "ev-05", "from_agent authorized", "warn", "guard unavailable"
        )
    writer = guard.get("writer", "")
    reviewers = guard.get("reviewers", [])
    if ctx.from_agent in (writer, *reviewers):
        return EnvelopeVerdict("ev-05", "from_agent authorized", "pass", ctx.from_agent)
    return EnvelopeVerdict(
        "ev-05",
        "from_agent authorized",
        "fail",
        f"{ctx.from_agent} is not writer({writer}) or reviewer({reviewers})",
    )


def check_task_exists(ctx: HandoffContext) -> EnvelopeVerdict:
    """task_id exists in the board."""
    try:
        from agent_relay.tasks import parse_board_rows

        tasks = parse_board_rows()
    except Exception:
        return EnvelopeVerdict("ev-06", "task exists", "warn", "board unavailable")
    for t in tasks:
        if t["id"] == ctx.task_id:
            return EnvelopeVerdict("ev-06", "task exists", "pass", ctx.task_id)
    return EnvelopeVerdict(
        "ev-06", "task exists", "fail", f"Task {ctx.task_id} not found"
    )


def check_handoff_file_safe(task_id: str) -> EnvelopeVerdict:
    """The handoff file on disk is not a symlink and is valid JSON."""
    try:
        from agent_relay.mcp_handoff_store import HandoffStore

        store = HandoffStore()
        path = store._current_path(task_id)
    except Exception:
        return EnvelopeVerdict(
            "ev-07", "handoff file safe", "warn", "store unavailable"
        )
    if not path.exists():
        return EnvelopeVerdict("ev-07", "handoff file safe", "fail", "File not found")
    if path.is_symlink():
        return EnvelopeVerdict("ev-07", "handoff file safe", "fail", "Symlink detected")
    if path.stat().st_size > MAX_HANDOFF_SIZE:
        return EnvelopeVerdict(
            "ev-07",
            "handoff file safe",
            "fail",
            f"Size {path.stat().st_size} exceeds limit",
        )
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return EnvelopeVerdict("ev-07", "handoff file safe", "pass")
    except json.JSONDecodeError as e:
        return EnvelopeVerdict("ev-07", "handoff file safe", "fail", str(e))


# ---------------------------------------------------------------------------
# All checks registry
# ---------------------------------------------------------------------------

_ENVELOPE_CHECKS = [
    ("ev-01", check_envelope_version),
    ("ev-02", check_context_size),
    ("ev-03", check_context_sha256),
    ("ev-04", check_to_agent_registered),
    ("ev-05", check_from_agent_authorized),
    ("ev-06", check_task_exists),
    ("ev-07", lambda ctx: check_handoff_file_safe(ctx.task_id)),
]

_CHECK_NAMES = {
    "ev-01": "Envelope version",
    "ev-02": "Context size",
    "ev-03": "Context checksum",
    "ev-04": "Target agent registered",
    "ev-05": "Source agent authorized",
    "ev-06": "Task exists",
    "ev-07": "Handoff file integrity",
}


def validate_envelope(ctx: HandoffContext) -> List[EnvelopeVerdict]:
    """Run all envelope checks against *ctx*.

    Returns a list of verdicts (one per check).
    """
    verdicts = []
    for check_id, check_fn in _ENVELOPE_CHECKS:
        try:
            verdicts.append(check_fn(ctx))
        except Exception as e:
            verdicts.append(
                EnvelopeVerdict(
                    check_id, _CHECK_NAMES.get(check_id, check_id), "fail", str(e)
                )
            )
    return verdicts


# ---------------------------------------------------------------------------
# Launch preview builder
# ---------------------------------------------------------------------------


def build_launch_preview(
    ctx: HandoffContext,
    verdicts: List[EnvelopeVerdict] | None = None,
) -> LaunchPreview:
    """Build a human-readable preview of a handoff launch.

    Parameters
    ----------
    ctx : HandoffContext
        The handoff to preview.
    verdicts : list of EnvelopeVerdict, optional
        Pre-computed verdicts.  Computed if omitted.

    Returns
    -------
    LaunchPreview dataclass.
    """
    if verdicts is None:
        verdicts = validate_envelope(ctx)

    errors = [v.detail for v in verdicts if v.status == "fail"]
    warnings = [v.detail for v in verdicts if v.status == "warn"]
    passed = all(v.status == "pass" for v in verdicts)

    # Derive role from the handoff context or guard
    role = "writer"
    if hasattr(ctx, "allowed_actions") and ctx.allowed_actions:
        # If context mentions review, treat as reviewer
        pass

    # Build human-readable launch command
    launch_cmd = f"{ctx.to_agent} — handoff from {ctx.from_agent} (task {ctx.task_id})"

    context_preview = (ctx.context or "")[:200]
    context_size = len(ctx.context or "")

    return LaunchPreview(
        handoff_id=ctx.handoff_id,
        task_id=ctx.task_id,
        from_agent=ctx.from_agent,
        to_agent=ctx.to_agent,
        role=role,
        summary=ctx.summary,
        context_preview=context_preview,
        context_size=context_size,
        commit_hash=ctx.commit_hash,
        allowed_actions=ctx.allowed_actions,
        launch_command=launch_cmd,
        verdicts=verdicts,
        passed=passed,
        warnings=warnings,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def preview_handoff(task_id: str) -> Dict[str, Any]:
    """Load a handoff by task_id, validate, and return a preview dict.

    Returns
    -------
    dict with keys ``ok``, ``preview``, ``verdicts``, ``errors``.
    """
    from agent_relay.mcp_handoff_store import HandoffStore

    store = HandoffStore()
    ctx = store.read(task_id)
    if ctx is None:
        return {"ok": False, "error": f"No handoff found for task {task_id}"}

    verdicts = validate_envelope(ctx)
    preview = build_launch_preview(ctx, verdicts)

    return {
        "ok": preview.passed,
        "preview": asdict(preview),
        "verdicts": [v.to_dict() for v in verdicts],
        "warnings": preview.warnings,
        "errors": preview.errors,
    }


def confirm_and_launch(task_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Validate, preview, and (if confirmed) dispatch the handoff.

    Parameters
    ----------
    task_id : str
    confirm : bool
        If True, skip interactive confirmation.  Default is confirm=False
        (print preview and require acknowledgement).

    Returns
    -------
    dict with keys ``ok``, ``action`` (preview|confirm_required|launched|blocked),
    ``preview``, ``result`` (if launched).
    """
    from agent_relay.mcp_handoff_store import HandoffStore

    store = HandoffStore()
    ctx = store.read(task_id)
    if ctx is None:
        return {
            "ok": False,
            "action": "error",
            "error": f"No handoff for task {task_id}",
        }

    verdicts = validate_envelope(ctx)
    preview = build_launch_preview(ctx, verdicts)

    if not preview.passed:
        # Blocked by failed checks
        return {
            "ok": False,
            "action": "blocked",
            "preview": asdict(preview),
            "verdicts": [v.to_dict() for v in verdicts],
            "errors": preview.errors,
        }

    if not confirm:
        return {
            "ok": True,
            "action": "confirm_required",
            "preview": asdict(preview),
            "verdicts": [v.to_dict() for v in verdicts],
            "message": "Pass all checks. Use --confirm to launch.",
        }

    # Proceed with dispatch via adapter
    from agent_relay.adapter import dispatch as adapter_dispatch

    try:
        result = adapter_dispatch(task_id, ctx.to_agent, role="writer", mock=False)
        return {
            "ok": True,
            "action": "launched",
            "preview": asdict(preview),
            "result": result,
        }
    except Exception as e:
        return {
            "ok": False,
            "action": "error",
            "preview": asdict(preview),
            "error": str(e),
        }
