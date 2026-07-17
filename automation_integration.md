# 多 Coding Agent 协同框架：自动化与无缝集成指南

本文件记录了我们如何将 `agent-relay` 协同框架深度集成到 AI Agent 的环境（如 Antigravity 全局 Skill、Claude Code 的 CLAUDE.md 引导）中，实现通过自然语言与斜杠命令（Slash Commands）自动驱动整个协同流的设计。

---

## 一、 Antigravity (Gemini) 的全局 Skill 自动化集成

我们在全局配置目录中创建了 `agent-relay` 的专属 Skill：
📂 [SKILL.md](file:///C:/Users/20651/.gemini/config/skills/agent_relay/SKILL.md)

### 1. 触发与机制
*   **触发条件**：当您在任何 Chat 会话中使用 `/task` 或 `/agent-relay` 开头的斜杠命令，或者在对话中提到“帮我创建任务”、“启动任务”、“提交任务”时，该 Skill 自动激活。
*   **Agent 执行规范**：
    *   **不要输出终端操作指令让用户去跑**。
    *   Agent 收到指令后，必须直接调用自身的 `run_command` 工具执行对应的 `agent-relay` 全局命令。
    *   如果任务指派给 Antigravity 自己，Agent 必须将 Cwd 限制在隔离工作区 `D:\multi_agent_worktrees\task-00X` 开展工作。

### 2. 映射关系
*   `/task status` -> 自动执行 `agent-relay status`
*   `/task create "<title>" --agent <name>` -> 自动执行 `agent-relay create`
*   `/task start <task-id>` -> 自动执行 `agent-relay start`
*   `/task submit <task-id>` -> 自动执行 `agent-relay submit`
*   `/task merge <task-id>` -> 自动执行 `agent-relay merge`

---

## 二、 Claude Code 的动态自提交集成

为了避免用户在 Claude 完成开发后手动去终端输入 submit 指令，我们修改了 `agent-relay.py` 的动态引导注入逻辑：

*   **实现方式**：在 `agent-relay start` 时生成针对 Claude Code 的 `CLAUDE.md` 指导书。
*   **注入指令**：
    ```markdown
    ## Instructions
    1. Please complete the requirements listed above. Ensure code compiles and all unit tests pass.
    2. AUTOMATED SUBMISSION: When you are finished and everything is verified, you MUST execute the following command in the terminal using your shell/bash tool to submit your changes automatically:
       agent-relay submit task-00X
    ```
*   **效果**：由于 Claude Code 会绝对服从 `CLAUDE.md` 中的步骤指引，它在完成编码和测试验证后，会**自动在它的沙箱终端中调用** `agent-relay submit task-00X`，主动将自己开发的分支提交，实现“无人值守开发”。

---

## 三、 Codex (VS Code) 的快捷键与任务集成

针对使用 VS Code 配合 Codex 插件手动开发的场景，我们可以在项目的 `.vscode/tasks.json` 中配置一键任务：

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "agent-relay: Submit Current Task",
            "type": "shell",
            "command": "agent-relay submit ${input:taskId}",
            "problemMatcher": [],
            "group": "build"
        }
    ],
    "inputs": [
        {
            "id": "taskId",
            "type": "promptString",
            "description": "Enter the Task ID to submit (e.g. task-001)"
        }
    ]
}
```
*   **效果**：在 VS Code 中按下 `Ctrl+Shift+B` 或在命令面板中运行 `Run Task`，即可直接选择 submit，无需手动在外部终端敲命令。

---

## 四、 智能 Agent 路由 (Intelligent Agent Routing)

在全局 Skill 中，我们为 Antigravity 注入了**智能路由逻辑**。当您下达自然语言指令（如 `/task create "编写一个快速排序算法"`）时，Antigravity 会根据任务特性做如下自动分类：
1.  **逻辑/算法/接口** -> 路由至 **Claude Code** (`--agent claude`)，以确保获得推理能力与超廉价 DeepSeek Token 的最大性价比。
2.  **UI/布局/多模态/视觉走查** -> 路由至 **Antigravity** (`--agent antigravity`)，以便发挥其 Vision 和 Browser 代理的多模态审查能力。
3.  **人工微调/手动交互** -> 路由至 **Codex** (`--agent codex`)，配合 VS Code 编辑器行级提示。

---

## 五、 Token 消耗量与成本跟踪 (Cost & Budget Tracker)

我们在 `agent-relay` 工具中实现了**项目预算与 Token 账单看板**，完美实现额度管理：

### 1. 成本定价模型
框架内嵌了高精度的计费模型（支持在 `.agents/config.json` 中自定义）：
*   **Claude Code (DeepSeek API)**: 输入 $0.14 / 1M, 输出 $0.28 / 1M.
*   **Antigravity (Gemini 3.5)**: 输入 $0.075 / 1M, 输出 $0.30 / 1M.
*   **Codex**: $0.00 (免费/IDE 订阅制).

### 2. 自动估算与手动校准
*   **自动估算**：在执行 `agent-relay submit` 时，CLI 会自动根据当前隔离区（Worktree）中的代码 diff 增量（1 行代码 ≈ 40 字符 ≈ 10 tokens）估算输出 token，并按 8 倍基数折算上下文输入 token，自动记录成本。
*   **手动校准**：您可以直接输入以下指令手动注入真实 Token 账单：
    ```bash
    agent-relay cost log task-001 --input 150000 --output 20000
    ```
*   **看板展示**：当您运行 `agent-relay status` 时，会在任务板下方输出精美的预算明细看板：
    ```
    💰 COST & BUDGET TRACKER
    ----------------------------------------------------------------------------------------------------
    Total Budget: $10.0000 | Total Expended: $0.0309 | Remaining Balance: $9.9691 (99.69% remaining)
    ----------------------------------------------------------------------------------------------------
    * task-001 (claude): $0.026600 (Input: ~150,000, Output: ~20,000 tokens)
    * task-003 (antigravity): $0.004275 (Input: ~45,000, Output: ~3,000 tokens)
    ====================================================================================================
    ```
*   **预算设置**：可以使用 `agent-relay cost budget 20.0` 设置总预算上限，超出预算或余额不足时将给予醒目提示。
