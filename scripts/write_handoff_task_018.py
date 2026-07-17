import sys
from pathlib import Path

# 将项目根目录添加到 python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from agent_relay.mcp_handoff_store import HandoffStore, HandoffContext

# 初始化 HandoffStore，路径指向 .agents 文件夹
store = HandoffStore(project_root / ".agents")

# 创建 HandoffContext 并交接回 claude
ctx = HandoffContext(
    handoff_id="",  # 自动生成
    task_id="task-018",
    from_agent="antigravity",
    to_agent="claude",
    summary="交付宣发视频故事板设计：完成并输出至 .agents/tasks/task-018-storyboard.md",
    context="""我已按要求设计并完成了 agent-relay 的宣发视频故事板。

故事板大纲包括7个分镜，共计35秒的竖屏视频内容，涵盖痛点引入、口号展示、Antigravity起点接力、MCP黑板传递、Claude Code终点接棒、Dashboard价值总结和GitHub Star CTA。同时，我也输出了一套包含玻璃拟态风格的视觉指南和所需的素材清单。

完整的交付文件已成功保存到项目目录下的 `.agents/tasks/task-018-storyboard.md`。

请 Claude Code 接力并继续进行后续的 GitHub 开源发布和视频生成故事板细化。""",
    commit_hash=None
)

saved = store.write(ctx)
print(f"Handoff successfully written for {saved.task_id}!")
print(f"Handoff ID: {saved.handoff_id}")
print(f"From Agent: {saved.from_agent} -> To Agent: {saved.to_agent}")
