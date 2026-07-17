"""HandoffStore — per-task persistent shared-blackboard for MCP.

Each handoff write creates two on-disk artifacts:

    .agents/handoffs/current/{task_id}.json     ← latest per task (overwritten)
    .agents/handoffs/history/<ts>_<task_id>.json ← append-only archive

All operations are idempotent and safe for concurrent read while
only one writer exists (guarded by agy-flow's lease mechanism).
"""

import datetime
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_HANDOFF_ID_RE = re.compile(r"^[a-f0-9]{16,32}$")


@dataclass
class HandoffContext:
    """A single handoff transfer between two agents."""

    handoff_id: str
    task_id: str
    from_agent: str
    to_agent: str
    summary: str
    context: str
    commit_hash: str | None = None
    timestamp: str = ""
    acked: bool = False
    acked_by: str | None = None
    acked_at: str | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().isoformat()


@dataclass
class AckResult:
    """Result of acknowledging a handoff."""

    status: str  # "acknowledged" | "already_acked" | "not_found"
    handoff_id: str
    acked_by: str
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class HandoffStore:
    """Persistent per-task handoff store backed by the project's ``.agents/``.

    Usage
    -----
    >>> store = HandoffStore()           # auto-discovers project root
    >>> store.write(HandoffContext(...))
    >>> ctx = store.read("task-001")
    >>> store.ack("task-001", "codex")
    """

    def __init__(self, agents_dir: str | Path | None = None):
        if agents_dir is None:
            # lazy import to break circular dependency at module level
            from agy_flow.config import AGENTS_DIR as _dir

            agents_dir = _dir
        self._agents_dir = Path(agents_dir)
        self._current_dir = self._agents_dir / "handoffs" / "current"
        self._history_dir = self._agents_dir / "handoffs" / "history"
        self._current_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

    # -- helpers -----------------------------------------------------------

    def _current_path(self, task_id: str) -> Path:
        """Path to the per-task current handoff file."""
        return self._current_dir / f"{task_id}.json"

    def _history_path(self, ctx: HandoffContext) -> Path:
        """Path to the history archive entry (idempotent: uses handoff_id)."""
        ts = ctx.timestamp.replace(":", "-").replace("T", "_")[:19]
        return self._history_dir / f"{ts}_{ctx.task_id}_{ctx.handoff_id[:12]}.json"

    @staticmethod
    def _generate_id() -> str:
        """Return a hex handoff id based on current time + small entropy."""
        import hashlib
        import os

        raw = f"{datetime.datetime.now().isoformat()}{os.urandom(4).hex()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    # -- public API --------------------------------------------------------

    def write(self, ctx: HandoffContext) -> HandoffContext:
        """Persist *ctx* and archive the previous current (if any).

        Both the per-task current file and the history archive are written.
        Returns the saved *ctx* (with handoff_id filled in if missing).
        """
        if not ctx.handoff_id or not _HANDOFF_ID_RE.match(ctx.handoff_id):
            object.__setattr__(ctx, "handoff_id", self._generate_id())
        if not ctx.timestamp:
            object.__setattr__(ctx, "timestamp", datetime.datetime.now().isoformat())

        # Write current (overwrite per task)
        current_path = self._current_path(ctx.task_id)
        current_path.write_text(
            json.dumps(asdict(ctx), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Archive to history (new file each time)
        history_path = self._history_path(ctx)
        if not history_path.exists():
            history_path.write_text(
                json.dumps(asdict(ctx), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return ctx

    def read(self, task_id: str) -> HandoffContext | None:
        """Return the latest handoff for *task_id*, or ``None``."""
        path = self._current_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return HandoffContext(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def ack(self, task_id: str, agent: str) -> AckResult:
        """Mark the latest handoff for *task_id* as acknowledged by *agent*.

        Idempotent — calling twice returns ``already_acked``.
        """
        current = self.read(task_id)
        if current is None:
            return AckResult(
                status="not_found",
                handoff_id="",
                acked_by=agent,
                timestamp=datetime.datetime.now().isoformat(),
            )

        if current.acked:
            return AckResult(
                status="already_acked",
                handoff_id=current.handoff_id,
                acked_by=agent,
                timestamp=datetime.datetime.now().isoformat(),
            )

        now = datetime.datetime.now().isoformat()
        object.__setattr__(current, "acked", True)
        object.__setattr__(current, "acked_by", agent)
        object.__setattr__(current, "acked_at", now)

        # Persist updated current
        current_path = self._current_path(task_id)
        current_path.write_text(
            json.dumps(asdict(current), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Sync ack to history archive (find by handoff_id prefix)
        self._sync_history_ack(current)

        return AckResult(
            status="acknowledged",
            handoff_id=current.handoff_id,
            acked_by=agent,
            timestamp=now,
        )

    def _sync_history_ack(self, ctx: HandoffContext) -> None:
        """Update the matching history file to reflect ack state."""
        prefix = ctx.handoff_id[:12]
        for fpath in self._history_dir.iterdir():
            if fpath.suffix != ".json":
                continue
            if prefix in fpath.stem and ctx.task_id in fpath.stem:
                try:
                    data = json.loads(fpath.read_text(encoding="utf-8"))
                    if data.get("handoff_id") == ctx.handoff_id and not data.get(
                        "acked"
                    ):
                        data["acked"] = True
                        data["acked_by"] = ctx.acked_by
                        data["acked_at"] = ctx.acked_at
                        fpath.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except (json.JSONDecodeError, OSError):
                    continue
                break  # only update the first match

    def history(
        self, task_id: str | None = None, limit: int = 5
    ) -> list[HandoffContext]:
        """Return archived handoffs, newest first.  Filter by *task_id* if given."""
        entries: list[HandoffContext] = []
        for fpath in sorted(self._history_dir.iterdir(), reverse=True):
            if fpath.suffix != ".json":
                continue
            if task_id and task_id not in fpath.stem:
                continue
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                entries.append(HandoffContext(**data))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
            if len(entries) >= limit:
                break
        return entries

    def current_all(self) -> dict[str, HandoffContext]:
        """Return all per-task current handoffs keyed by task_id."""
        result: dict[str, HandoffContext] = {}
        for fpath in self._current_dir.glob("*.json"):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                ctx = HandoffContext(**data)
                result[ctx.task_id] = ctx
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return result
