# Task: task-017 - MCP共享黑板设计审查：扩展agent-relay MCP Server支持跨Agent交接（Phase 2）

## Metadata
- **ID**: task-017
- **Title**: MCP共享黑板设计审查：扩展agent-relay MCP Server支持跨Agent交接
- **Assigned Agent**: claude -> codex -> claude -> codex -> claude
- **Status**: Review（Phase 2）
- **Created Time**: 2026-07-16 21:11:12

## 协作流程（当前在 Phase 2）

1. ✅ **Phase 0** — Claude 写设计计划
2. ✅ **Phase 1** — Codex 审查设计计划，给出实施方案 ✅ **完成**（你在上一轮提出了 4 个关键问题，全部采纳）
3. ✅ **Phase 1.5** — Claude 实现了完整的 v2 MCP Server（代码已提交）
4. 🔄 **Phase 2（你现在）** — Codex 审查已实现的代码 + 写下一步计划
5. ⏳ **Phase 3** — Claude 执行下一步计划

## 已完成的工作

所有代码已实现并测试通过：

| 文件 | 说明 |
|------|------|
| `agent_relay/mcp_handoff_store.py` | **新文件** — HandoffContext dataclass + HandoffStore（per-task 文件 + 历史归档） |
| `agent_relay/mcp_server.py` | v2 升级 — 12 tools（+3 handoff tools）+ 3 resources + initialize resources capability |
| `agent_relay/handoff.py` | 新增 `build_handoff_mcp_context()` 薄包装（局部导入防循环） |
| `test_mcp_server.py` | 45 tests（无头测试 15 + 集成测试 30），覆盖 tools/resources/handoff 全链路 |
| `scripts/mcp_client_smoke.py` | 14/14 smoke steps（新增 resources + handoff 测试，修复计数累加） |

### 采纳你的审查意见后的设计决策
- ❌ **handoff_write 不触碰 writer guard**（不调 lease_writer / assign_current_task_agent）
- ✅ Resources 使用 URI 参数化（`handoff://current/{task_id}`, `handoff://history?limit=N`）
- ✅ 存储按 task_id 分文件（`.agents/handoffs/current/{task_id}.json`）
- ✅ 历史按时间归档（`.agents/handoffs/history/<ts>_<task_id>.json`）
- ✅ initialize 声明 `resources` capabilities

### 测试结果
- **45/45** pytest 通过
- **14/14** smoke 端到端通过
- **61/61** 相关模块全量通过、0 回归

## Codex（你）现在需要做的事

### 审查 1：代码质量审查
请审查以下文件，确认实现是否完善：

1. **`agent_relay/mcp_handoff_store.py`** — HandoffStore 的 write/read/ack/history/current_all 是否有 bug？
2. **`agent_relay/mcp_server.py`** — 新工具的 handler、resources/read 的正则匹配是否完备？
3. **`test_mcp_server.py`** — 新增的 20+ 个测试是否覆盖了足够的 edge case？
4. **`scripts/mcp_client_smoke.py`** — 修复后的计数逻辑是否正确？

### 审查 2：下一步计划
基于当前已实现的代码，写一份下一步计划，包含：

1. **Antigravity MCP 配置指导** — 如何配置 `~/.gemini/antigravity/mcp_config.json` 连接到 agent-relay MCP Server
2. **Codex CLI MCP 配置指导** — 如何配置 `~/.codex/config.toml`
3. **Dashboard 黑板可视化** — 在当前看板中显示 handoff 状态的思路
4. **短期改进建议** — 基于你现在的审查，还有哪些可以优化的

### 输出
将你的审查意见 + 下一步计划写入：`.agents/tasks/task-017-phase2-review.md`

完成后将 `current_task.json` 的 `agent` 改回 `claude`、`role` 改回 `writer`。

## 关键文件位置
- 设计文档：`.agents/tasks/mcp-blackboard-design-plan.md`（含实施状态）
- HandoffStore：`agent_relay/mcp_handoff_store.py`
- MCP Server：`agent_relay/mcp_server.py`
- 薄包装：`agent_relay/handoff.py`（末尾）
- 测试：`test_mcp_server.py`
- Smoke：`scripts/mcp_client_smoke.py`
