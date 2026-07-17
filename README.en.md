# agent-relay

> **Task handoff & shared blackboard framework for cross-desktop AI tools**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](pyproject.toml)

---

## 💡 What is this?

**agent-relay** is a lightweight collaboration framework that solves one specific, practical problem:

> You use multiple AI coding tools — Claude Code, Antigravity, Codex — each with their own strengths.
> But when a task requires handoff between tools, context can only be transferred via **manual copy-paste**.

agent-relay enables orderly, persistent handoff between these tools through **Git Worktree isolation** + **MCP shared blackboard** + **Writer/Reviewer guard protocol** — so you never have to manually pass context again.

### agent-relay vs ECC

| Dimension | ECC | agent-relay |
|-----------|-----|----------|
| Focus | Cross-platform **config unification** | Cross-tool **task handoff** |
| Multi-agent | Role-switching within one session (prompt engineering) | Cross-session, cross-tool, persistent handoff |
| Core mechanism | YAML agent definitions + skill reuse | Worktree isolation + MCP blackboard + Handoff protocol |
| Scale | 278 skills / 67 agents | Focused core, extend as needed |

**In short: ECC tells you "how to work inside each tool." agent-relay tells you "how to pass work between tools."**

---

## ✨ Features

### 🧩 Three-Way MCP Shared Blackboard
Share handoff context between Claude Code, Antigravity, and Codex via MCP. Write once, read everywhere.

```
Antigravity ──agy_handoff_write──→ .agents/handoffs/current/task-001.json
                                          ↓
                          Claude Code / Codex ──agy_handoff_read──→ context ready
```

### 🔐 Writer/Reviewer Guard Protocol
Prevent multiple agents from editing the same file simultaneously. Each task explicitly defines who writes and who reviews.

### 🌿 Git Worktree Isolation
Each agent works in an isolated worktree — concurrent development without conflicts.

### 📋 Visual Dashboard
Glassmorphism dark-theme Kanban board powered by the HTTP Gateway. Real-time task status and handoff visualization.

### 💰 Cheap-First Routing
Tasks are automatically routed to the most cost-effective agent based on type (DeepSeek for planning/review, Claude for logic, Antigravity for visuals).

---

## 🚀 Quick Start

### Installation

```bash
pip install agent-relay
```

Or from source:

```bash
git clone https://github.com/yourusername/agent-relay.git
cd agent-relay
pip install -e .
```

### Usage

```bash
# Initialize in your project
cd your-project
agent-relay init

# Create a task (auto-routes to best agent)
agent-relay create "Implement user login API"

# Start the task (creates worktree isolation)
agent-relay start task-001

# Submit for review when done
agent-relay submit task-001

# View all tasks
agent-relay status

# Launch visual dashboard
agent-relay serve --port 8080
```

### MCP Blackboard Configuration

**Antigravity** — Add to `~/.gemini/antigravity/mcp_config.json`:
```json
{
  "mcpServers": {
    "agent-relay": {
      "command": "python",
      "args": ["-m", "agent_relay.mcp_server"]
    }
  }
}
```

**Codex CLI** — Add to `~/.codex/config.toml`:
```toml
[mcp_servers.agent-relay]
command = "python"
args = ["-m", "agent_relay.mcp_server"]
```

Claude Code loads agent-relay automatically via the `UserPromptSubmit` hook.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    agent-relay CLI (agent-relay.py)                 │
│    create / start / submit / merge / status / serve / mcp    │
└──────────────────────┬───────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │ Gateway  │  │  MCP     │  │  agent-relay    │
   │ REST API │  │  Server  │  │  Library      │
   │(dashboard)│  │(blackboard)│  │              │
   └──────────┘  └──────────┘  └──────┬───────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
           ┌──────────┐         ┌──────────┐         ┌──────────┐
           │ Router   │         │ Handoff  │         │ Tasks    │
           │(classify)│         │(protocol)│         │(state    │
           └──────────┘         └──────────┘         │ machine) │
                 ▼                    ▼              └──────────┘
           ┌──────────┐         ┌──────────┐
           │Executor  │         │ Guard    │
           │(dispatch)│         │(writer/  │
           └──────────┘         │ reviewer)│
                                └──────────┘
```

### Core Modules

| Module | Responsibility |
|--------|---------------|
| `agent_relay/mcp_server.py` | MCP Server v2 — 12 tools + 3 resources |
| `agent_relay/mcp_handoff_store.py` | Blackboard storage — per-task current + history archive |
| `agent_relay/handoff.py` | Handoff protocol — writer lease + agent switching |
| `agent_relay/router.py` | Smart routing — capability-based agent assignment |
| `agent_relay/tasks.py` | Task lifecycle management |
| `agent_relay/gateway.py` | HTTP Gateway + Dashboard UI |
| `agent_relay/workspaces.py` | Git Worktree management |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest

# Specific modules
python -m pytest test_mcp_server.py test_mcp_handoff_store.py -v

# End-to-end smoke test
python scripts/mcp_client_smoke.py
```

---

## 🔧 Configuration

Project-level config at `.agents/config.json`:

```json
{
  "project_name": "my-project",
  "worktrees_dir": "../multi_agent_worktrees",
  "agents": {
    "claude": {
      "cli_command": "claude",
      "guide_file": "CLAUDE.md"
    },
    "antigravity": {
      "guide_file": ".agents/AGENTS.md"
    },
    "codex": {
      "interactive": true
    }
  }
}
```

---

## 📝 Roadmap

See [ROADMAP.en.md](ROADMAP.en.md) for known limitations and future plans.

Key near-term items:
- [x] CLI task management (create/start/submit/merge)
- [x] Git Worktree isolation
- [x] Writer/Reviewer guard protocol
- [x] HTTP Gateway + Dashboard
- [x] MCP shared blackboard v2 (write/read/ack + resources)
- [x] Antigravity & Codex CLI MCP configuration
- [ ] Desktop notification on handoff write (v1.1)
- [ ] Dashboard real-time handoff stream (v1.2)
- [ ] Semi-automatic agent handoff (v2.0)

---

## 🤝 Contributing

See [CONTRIBUTING.en.md](CONTRIBUTING.en.md).

---

## 📄 License

[MIT](LICENSE) © 2026 agent-relay contributors
