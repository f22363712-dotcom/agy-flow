"""Write handoff to codex for video content review + modifications."""

from agent_relay.handoff import assign_current_task_agent
from agent_relay.mcp_handoff_store import HandoffStore, HandoffContext
import sys

sys.path.insert(0, "D:\\multi_agent_collaboration")

store = HandoffStore()
context = (
    "## 任务：视频内容审查 + 修改\n\n"
    "### 你需要做\n\n"
    "1. **内容审查** — 审查 agent-relay-promo.mp4 的以下五个维度：\n"
    "   - 内容合理性：叙事逻辑是否有漏洞？技术概念（worktree/MCP/黑板）对于非深度开发者是否可理解？\n"
    "   - 脚本/文案：文字是否多余或缺失？开头钩子够不够抓人？\n"
    "   - 动效与视觉：动画节奏是否流畅？画面是否清晰？手机小屏上文字是否可读？\n"
    "   - 音频：环境音是否合适？是否需要解说配音？\n"
    "   - 小红书适配：是否适合无声自动播放？开头1秒能否抓住注意力？封面预览如何？\n\n"
    "2. **给出修改清单** — 列出你认为必须改和可以改的项目\n\n"
    "3. **执行修改** — 直接修改源码（src/video/AgentRelayPromo.tsx 和 styles.css），然后重新渲染视频\n\n"
    "4. **输出** — 修改后的视频覆盖 agent-relay-promo.mp4\n\n"
    "### Claude 的审查意见（供参考，不需要完全遵循）\n"
    "- 内容对小红书泛技术用户偏专业，文字密度偏高\n"
    "- 缺少封面图（小红书必需）\n"
    "- 缺少解说配音（有更好，非必须）\n"
    "- 开头0.5秒可加中文标题卡用于封面预览截取\n"
    "- JSON卡片的22px代码文字在手机屏上可能太小\n\n"
    "### 验证\n"
    "- 修改后运行 `npm run render:promo` 重新渲染\n"
    "- 用 ffprobe 确认输出规格：1080x1920, 30fps, H.264+AAC\n"
    "- 抽样检查关键帧是否正常\n\n"
    "完成后通过 agy_handoff_write 交接回 claude（to_agent=claude）。\n"
)

ctx = HandoffContext(
    handoff_id="",
    task_id="task-018",
    from_agent="claude",
    to_agent="codex",
    summary="视频内容审查+修改（含小红书适配）",
    context=context,
)
store.write(ctx)
assign_current_task_agent(
    "codex", task_id="task-018", role="writer", reviewers=["claude"], mode="handoff"
)
print(f"Handoff written: {ctx.handoff_id}")
print("Guard updated: codex is now writer")
