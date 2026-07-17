# agy-flow

> **跨桌面 AI 工具的任务接力与共享黑板框架**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](pyproject.toml)

---

## 💡 这是什么？

**agy-flow** 是一个轻量级的协作框架，解决一个具体而现实的问题：

> 你同时使用 Claude Code、Antigravity、Codex 等多个 AI 编码工具，每个工具各有所长。
> 但一个任务需要多个工具接力时，上下文只能靠**手动复制粘贴**。

agy-flow 通过 **Git Worktree 隔离** + **MCP 共享黑板** + **Writer/Reviewer 守卫协议**，让这些工具在同一个项目中有序接力，而不需要你手动传递上下文。

### agy-flow vs ECC

| 维度 | ECC | agy-flow |
|------|-----|----------|
| 定位 | 跨平台**配置统一**层 | 跨工具**任务接力**框架 |
| 多 Agent 协同 | 同 session 内角色切换（prompt engineering） | 跨 session、跨工具、持久化接力 |
| 核心机制 | YAML agent 定义 + skill 复用 | Worktree 隔离 + MCP 黑板 + Handoff 协议 |
| 规模 | 278 skills / 67 agents | 聚焦核心，按需扩展 |

**简单说：ECC 告诉你"在每个工具里怎么干活"，agy-flow 告诉你"怎么把活在不同工具之间传来传去"。**

---

## ✨ 核心特性

### 🧩 三端 MCP 共享黑板
通过 MCP 协议在 Claude Code、Antigravity、Codex 之间共享 handoff 上下文。写入一次，所有工具可读。

```
Antigravity ──agy_handoff_write──→ .agents/handoffs/current/task-001.json
                                          ↓
                                    Claude Code / Codex ──agy_handoff_read──→ 上下文就绪
```

### 🔐 Writer/Reviewer 守卫协议
防止多个 Agent 同时修改同一文件。每个任务明确指定谁写、谁审。

### 🌿 Git Worktree 隔离
每个 Agent 在独立的 worktree 中工作，并发开发互不干扰。

### 📋 可视化看板
基于 HTTP Gateway 的玻璃拟态暗色看板，实时查看所有任务状态和 handoff 接力。

### 💰 Cheap-First 路由
任务根据类型自动分配到最经济的 Agent（DeepSeek 做规划/审查，Claude 做逻辑，Antigravity 做视觉）。

---

## 🚀 快速开始

### 安装

```bash
pip install agy-flow
```

或者直接从源码：

```bash
git clone https://github.com/yourusername/agy-flow.git
cd agy-flow
pip install -e .
```

### 在项目中使用

```bash
# 初始化
cd your-project
agy-flow init

# 创建任务（自动路由到最佳 Agent）
agy-flow create "编写用户登录 API"

# 启动任务（拉起 worktree 隔离区）
agy-flow start task-001

# 完成开发后提审
agy-flow submit task-001

# 查看所有任务看板
agy-flow status

# 启动可视化看板
agy-flow serve --port 8080
```

### MCP 黑板配置

**Antigravity** — 在 `~/.gemini/antigravity/mcp_config.json` 中添加：
```json
{
  "mcpServers": {
    "agy-flow": {
      "command": "python",
      "args": ["-m", "agy_flow.mcp_server"]
    }
  }
}
```

**Codex CLI** — 在 `~/.codex/config.toml` 中添加：
```toml
[mcp_servers.agy-flow]
command = "python"
args = ["-m", "agy_flow.mcp_server"]
```

Claude Code 通过内置的 `UserPromptSubmit` hook 自动加载 agy-flow 引导。

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────────┐
│                    agy-flow CLI (agy-flow.py)                 │
│    create / start / submit / merge / status / serve / mcp    │
└──────────────────────┬───────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │ Gateway  │  │  MCP     │  │  agy-flow    │
   │ REST API │  │  Server  │  │  Library     │
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

### 核心模块

| 模块 | 职责 |
|------|------|
| `agy_flow/mcp_server.py` | MCP Server v2 — 12 tools + 3 resources |
| `agy_flow/mcp_handoff_store.py` | 黑板存储 — per-task current + 历史归档 |
| `agy_flow/handoff.py` | 接力协议 — writer lease + agent 切换 |
| `agy_flow/router.py` | 智能路由 — 按能力分配 Agent |
| `agy_flow/tasks.py` | 任务生命周期 |
| `agy_flow/gateway.py` | HTTP Gateway + Dashboard UI |
| `agy_flow/workspaces.py` | Git Worktree 管理 |

---

## 🧪 测试

```bash
# 全部测试
python -m pytest

# 特定模块
python -m pytest test_mcp_server.py test_mcp_handoff_store.py -v

# 端到端 smoke 测试
python scripts/mcp_client_smoke.py
```

---

## 🔧 配置

项目根目录的 `.agents/config.json`：

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

## 📝 路线图

- [x] CLI 任务管理（create / start / submit / merge）
- [x] Git Worktree 隔离
- [x] Writer/Reviewer 守卫协议
- [x] HTTP Gateway + Dashboard
- [x] MCP 共享黑板 v2（write / read / ack + resources）
- [x] Antigravity & Codex CLI MCP 配置
- [ ] handoff://history 分页
- [ ] Dashboard handoff 深度可视化
- [ ] GitHub Actions CI
- [ ] PyPI 自动发布

---

## 🤝 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📄 许可证

[MIT](LICENSE) © 2026 agy-flow contributors
