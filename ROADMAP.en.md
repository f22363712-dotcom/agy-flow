# agy-flow Roadmap & Known Limitations

## Known Limitations

### MCP Blackboard is Reactive, Not Proactive

**Current state:** The MCP shared blackboard (v2) solves **context persistence and sharing** between three desktop AI tools (Claude Code, Antigravity, Codex). Agent A writes a handoff; Agent B can read it via `agy_handoff_read` or MCP Resources.

**The problem:** These desktop AI tools are **reactive** — they only respond to user prompts. They don't poll the blackboard, discover new tasks, or start working automatically.

**Ideal flow:**
```
Agent A completes → writes to blackboard → blackboard notifies Agent B → Agent B starts automatically
```

**Current reality:**
```
Agent A completes → writes to blackboard → user says "check the blackboard" → Agent B reads → starts
```

**Root cause:** The MCP protocol itself is pull-based, not push-based. Claude Code, Antigravity, and Codex don't implement MCP `notifications` events to listen for blackboard changes.

**Possible directions:**
1. Add a lightweight local daemon that polls `.agents/handoffs/current/` for changes
2. On new handoff detection, trigger a system toast notification reminding the user to switch tools
3. If MCP clients eventually support `notifications/resources/list_changed`, the blackboard can push changes

### Other Known Limitations

- **No real-time collaboration**: Two agents cannot edit the same file simultaneously (by design — Worktree isolation + guard protocol ensures safety)
- **No Web UI push**: Dashboard requires manual refresh or polling
- **Local environment dependency**: Python + FFmpeg (video_composer) must be pre-installed
- **Windows-first**: Path handling and shell commands primarily target Windows; cross-platform adaptation needed

## Future Roadmap

### v1.1 — Notification Layer (near-term)
- [ ] File system watcher that triggers OS notification on handoff write
- [ ] Auto-copy handoff context to clipboard
- [ ] Reduce the "go check the blackboard" manual step

### v1.2 — Dashboard Deep Integration
- [ ] Real-time handoff status on Dashboard (SSE or WebSocket)
- [ ] One-click agent switch from Dashboard (open target tool)
- [ ] Handoff timeline visualization

### v2.0 — Semi-Automatic Handoff
- [ ] Listen for handoff write → auto-launch target agent CLI
- [ ] Support MCP `notifications` (when clients implement it)
- [ ] Configurable handoff strategy (auto / confirm / manual)

## Contribution Areas

If you're interested in addressing these limitations, here are the most helpful areas:

- **Notification integration**: System tray notifications on handoff write
- **Cross-platform testing**: Verify path and shell compatibility on macOS/Linux
- **Dashboard enhancement**: Real-time refresh, accordion-style handoff expansion
- **CI/CD**: GitHub Actions auto-testing + PyPI publishing
