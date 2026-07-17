# task-018 宣发视频故事板：agent-relay 三端联通演示

本故事板为 `agent-relay` 跨 AI 编码工具的协作框架量身打造，定位为 30-40 秒竖屏视频，适用于小红书、B站、抖音等平台。

---

## 一、 故事板分镜设计

| 镜头编号 | 时长 (s) | 画面描述 (Visuals) | 画外音文案 (Audio/VO) | 转场方式 (Transition) |
| :--- | :--- | :--- | :--- | :--- |
| **01. 痛点引入** | 0-3s | **画面**：左右三分屏，分别展示 Cursor 报错、Claude Code 爆满、Copilot 上下文丢失。一个卡通手绘风的“抓狂”表情浮现，伴随红色警告窗“Context Lost!”闪烁。<br>**视觉**：暗淡色调，警告窗使用高饱和红色。 | “在 Cursor、Claude Code 里来回切换，复制粘贴，上下文又丢了？” | 画面中心像黑色裂缝般撕开，快速卡点切入下一镜。 |
| **02. 解决方案** | 3-7s | **画面**：深海蓝黑背景，四周有炫酷的毛玻璃（Glassmorphism）质感。中央亮起极光绿与霓虹紫渐变的 `agent-relay` Logo。<br>**口号出现**：'一个任务，三倍智能'。 | “是时候结束这场复制粘贴的噩梦了。介绍 `agent-relay` —— 跨 AI 编码工具的多 Agent 协同框架。” | Logo 向中心收缩，化为一个闪光的“共享黑板”图标。 |
| **03. 起点接力** | 7-12s | **画面**：展示 `Antigravity` IDE/终端。输入命令 `agent-relay start task-018`。屏幕上泛起微弱的绿色发光线条，一个隔离的 git worktree 工作目录被瞬间拉起，且自动载入设计规范。 | “一个命令启动任务，Antigravity 自动进入隔离工作区，开始视觉与故事板设计。” | 镜头横向平移（Pan）到右侧，拉出数据通道。 |
| **04. 黑板传递** | 12-18s | **画面**：精美的 3D 线框动效。`task-018.json` 配置文件被写入 `handoffs/current`。数据流如同一道极光，穿过 MCP Server 管道，注入共享黑板（Blackboard）。 | “核心卖点：MCP 共享黑板。无需手动传输，你的任务进度、上下文 and 代码，自动在 AI 间接力传递。” | 极光流光穿过屏幕，流入终端光标处。 |
| **05. 终点接棒** | 18-25s | **画面**：展示 Claude Code 终端。Claude 运行 `agent-relay status`，秒级读取刚刚写入的黑板数据，后台自动执行 `pytest`，并一键完成交付。<br>**视觉**：代码高亮极速滚动，绿色测试通过字样 `PASSED` 闪烁。 | “Claude Code 接棒！零延迟读取黑板上下文，自动编写测试与核心逻辑。三端联通，无缝闭环。” | 终端卡片缩小，融入到 Dashboard 大图景中。 |
| **06. 价值总结** | 25-32s | **画面**：展示 `agent-relay` Dashboard 面板。亮眼的暗色玻璃拟态图表呈现任务接力链路、Token 成本分析。大字浮现：“跨AI工具的多Agent协同”。 | “不仅是工具的叠加，更是生产力的质变。让不同的 AI 专注于它们最擅长的事。” | 画面霓虹光晕向中心凝聚。 |
| **07. CTA 引导** | 32-35s | **画面**：极简黑色背景，中心浮现 GitHub 标志与地址：`github.com/your-repo/agent-relay`。下方一个黄色的 **Star** 按钮被点击，带起水波涟漪特效。 | “`agent-relay` 现已开源。即刻体验，点亮你的 Star，让 AI 协作飞起来！” | 渐暗淡出 (Fade out)。 |

---

## 二、 视觉风格指南

*   **色彩体系 (Color Palette)**：
    *   **背景色**：深海蓝黑 (`#0B0F19`)，搭配 `backdrop-filter: blur` 营造高大上的玻璃拟态（Glassmorphism）。
    *   **主色调**：极光绿渐变 (`#00F2FE` $\rightarrow$ `#4FACFE`)，用于代表数据流动、MCP Server 连线。
    *   **辅助色**：霓虹紫渐变 (`#B621FE` $\rightarrow$ `#1FD1F9`)，象征不同 AI Agent 之间的火花碰撞与无缝协作。
*   **字体规范 (Typography)**：
    *   **英文/数字**：`Outfit` 或 `Inter` (无衬线、几何感、粗体，现代科技感十足)。
    *   **中文**：`OPPO Sans` 或 `Alibaba PuHuiTi` (硬朗利落，高易读性)。
*   **动画特效 (Motion & Effects)**：
    *   **缓动曲线**：使用 `cubic-bezier(0.16, 1, 0.3, 1)`（超平滑淡入）。
    *   **流光效果**：数据在 MCP 管道传输时，使用发光线段（Glowing Line）沿路径运动的微动效。
    *   **卡片视差**：Dashboard 卡片随视频运镜有轻微的层级视差（Parallax）和悬浮阴影变化。

---

## 三、 录制素材清单

1.  **录屏素材**：
    *   开发者抓耳挠腮、在 VS Code 和各种终端之间“复制粘贴代码及上下文”的痛点实录（带快进）。
    *   在 powershell 终端中执行 `agent-relay start task-018` 动态生成 worktree 的全过程。
    *   运行 `pytest` 测试通过并完成 `agent-relay submit` 提审的极速滚动画面。
2.  **视觉/UI 动效**：
    *   `agent-relay` Dashboard 暗色毛玻璃 UI 录屏（包含动态 Token 消耗图表、任务看板卡片）。
    *   数据流从 `task-018.json` 经过管道存入黑板（Blackboard）的 2.5D 扁平风动效。
3.  **其他静态资源**：
    *   带发光描边的 GitHub Star 按钮图片。
    *   `agent-relay` 渐变色 Logo。
