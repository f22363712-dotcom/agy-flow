"""Write handoff from claude to codex for video production phase."""

from agent_relay.mcp_handoff_store import HandoffStore, HandoffContext
from agent_relay.handoff import assign_current_task_agent

store = HandoffStore()
storyboard = open(".agents/tasks/task-018-storyboard.md", encoding="utf-8").read()
context = (
    "## 任务：用 Remotion 生成 agent-relay 宣发视频\n"
    "\n"
    "### 阶段\n"
    "Phase 1 (GitHub 文件) ✅ → Phase 2 (Antigravity 故事板) ✅ → **Phase 3 (你 — 视频制作)**\n"
    "\n"
    "### 输入素材\n"
    "1. **故事板**：`.agents/tasks/task-018-storyboard.md`（7 个分镜，精确到秒）\n"
    "2. **视觉风格**：暗色玻璃拟态（#0B0F19 背景，#00F2FE->#4FACFE 极光绿，#B621FE->#1FD1F9 霓虹紫）\n"
    "3. **字体**：Outfit（英文）、OPPO Sans（中文）\n"
    "4. **三端联通实际数据**：在 .agents/handoffs/current/task-017.json（Antigravity->Claude 的实际交接记录）\n"
    "\n"
    "### 技术规格\n"
    "- 分辨率：1080x1920（竖屏 9:16）\n"
    "- 帧率：30fps\n"
    "- 时长：35 秒\n"
    "- 输出格式：MP4（H.264 + AAC）\n"
    "- 工具：Remotion（Node.js 18+）\n"
    "\n"
    "### 分镜大纲\n"
    "镜头1（0-3s）：痛点展示 — 三分屏工具切换 + Context Lost 警告\n"
    "镜头2（3-7s）：Logo 出现 + '一个任务，三倍智能'\n"
    "镜头3（7-12s）：agent-relay start 命令执行 + worktree 拉起\n"
    "镜头4（12-18s）：MCP 数据流写入黑板\n"
    "镜头5（18-25s）：Claude Code 读取 + pytest 通过\n"
    "镜头6（25-32s）：Dashboard 看板概览\n"
    "镜头7（32-35s）：GitHub CTA + Star\n"
    "\n"
    "### 输出位置\n"
    "视频文件输出到项目根目录：agent-relay-promo.mp4\n"
    "\n"
    "完成后通过 agy_handoff_write 交接回 claude（to_agent=claude）。\n"
)

ctx = HandoffContext(
    handoff_id="",
    task_id="task-018",
    from_agent="claude",
    to_agent="codex",
    summary="使用 Remotion 制作宣发视频",
    context=context,
)
store.write(ctx)
assign_current_task_agent(
    "codex", task_id="task-018", role="writer", reviewers=["claude"], mode="handoff"
)
print(f"Handoff written: {ctx.handoff_id}")
print("Guard updated: codex is now writer")
