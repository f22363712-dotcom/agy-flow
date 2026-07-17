# agent-relay 路线图与已知不足

## 已知不足

### MCP 黑板是反应式的，不是自动执行的

**当前状态：** MCP 共享黑板（v2）解决了三个桌面 AI 工具（Claude Code、Antigravity、Codex）之间的**上下文持久化与共享**问题。Agent A 写入 handoff 后，Agent B 可以通过 `agy_handoff_read` 或 MCP Resource 读到完整上下文。

**但问题在于：** 这些桌面 AI 工具都是**反应式**的——它们只响应用户的 prompt，不会主动轮询黑板、发现新任务、自动开始工作。

**理想状态：**
```
Agent A 完成 → 写入黑板 → 黑板通知 Agent B → Agent B 自动开始
```

**当前现实：**
```
Agent A 完成 → 写入黑板 → 用户说"去看看黑板" → Agent B 读取 → 开始
```

**根本原因：** MCP 协议本身是"拉模式"（pull），不是"推模式"（push）。Claude Code、Antigravity、Codex 都没有实现 MCP 的 `notifications` 事件处理来监听黑板变化。

**可能的解决方向：**
1. 添加一个轻量级的本地守护进程（daemon），轮询 `.agents/handoffs/current/` 目录变化
2. 检测到新 handoff 后，调用系统通知（toast），提醒用户切换工具
3. 未来如果 MCP 客户端支持 `notifications/resources/list_changed`，黑板可以主动推送变更

### 其他已知局限

- **无实时协作**：两个 Agent 不能同时编辑同一文件（这是设计取舍——通过 Worktree 隔离 + 守卫协议保证安全）
- **无 Web UI 推送**：Dashboard 需要手动刷新或轮询
- **依赖本地环境**：Python + FFmpeg（video_composer）需要预装
- **Windows 优先**：路径处理和 Shell 命令主要针对 Windows，跨平台需要适配

## 未来路线图

### v1.1 — 通知层（排序近期）
- [ ] 文件系统 watcher，在 handoff 写入时触发系统通知
- [ ] 剪贴板自动填充交接上下文
- [ ] 减少"去看看黑板"的手动步骤

### v1.2 — Dashboard 深度集成
- [ ] Dashboard 实时更新 handoff 状态（SSE 或 WebSocket）
- [ ] 从 Dashboard 一键切换 Agent（打开对应工具）
- [ ] handoff 时间线可视化

### v2.0 — 半自动接力
- [ ] 监听 handoff 写入 → 自动拉起目标 Agent CLI
- [ ] 支持 MCP notifications （当客户端实现时）
- [ ] 可配置的自动接力策略（自动/确认后/手动）

## 贡献方向

如果你对解决这些不足感兴趣，以下是当前最需要帮助的领域：

- **通知集成**：系统托盘/通知栏，在 handoff 写入时弹窗提醒
- **跨平台测试**：在 macOS/Linux 上验证 Path 和 Shell 兼容性
- **Dashboard 增强**：实时刷新、手风琴式 handoff 展开
- **CI/CD**：GitHub Actions 自动测试 + PyPI 发布
