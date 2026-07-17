# agent-relay 论文写作协同 Prompt 模板

您可将以下内容复制并直接发送给 VS Code 中的 Claude Code 扩展，引导其自动调用 `agent-relay` 框架开展期末论文的拆解与撰写。

---

## 📋 复制发送给 Claude 的 Prompt：

```markdown
你好！我当前的项目是一个课程项目，我需要你配合我们团队的 `agent-relay` 多 Agent 协同框架，帮我完成一篇课程期末论文。

`agent-relay` 是一个全局注册的 Git-Worktree 任务流工具，支持在终端直接调用。请你作为“指挥官（Conductor）”，按照以下步骤在后台执行命令开展工作：

1. **环境检查**：
   请在终端运行 `agent-relay status`，检查当前目录是否已初始化为 agent-relay 项目。
   - 如果未初始化，请运行 `agent-relay init` 进行初始化。

2. **规划论文任务**：
   我们这次的期末论文主题是：【在此处替换为您的论文主题，例如：基于 Git Worktree 的多智能体协同开发框架设计与实现】。
   请你将论文撰写工作拆解为以下 4 个子任务，并调用 `agent-relay create "<任务名称>" --agent claude` 命令创建它们：
   - 任务 1：撰写论文大纲与摘要 (Abstract & Outline)
   - 任务 2：撰写引言与文献综述 (Introduction & Literature Review)
   - 任务 3：撰写系统设计与协同框架核心机制 (System Design & Core Mechanism)
   - 任务 4：撰写系统测试与结论 (Testing & Conclusion)

3. **自动开发与提审**：
   创建完任务后，请你依次对每个任务执行以下步骤：
   - 运行 `agent-relay start task-00X` 启动任务。
   - 自动进入生成的 worktree 隔离区目录（如 `../multi_agent_worktrees/task-00X`），在其中创建对应的 Markdown 文件编写论文内容。
   - 编写完成后，在终端运行 `agent-relay submit task-00X` 自动提审。
   - 最后，回到主项目目录运行 `agent-relay merge task-00X` 将该章节合并到 master 分支中。

现在，请在终端执行 `agent-relay status`（或 `agent-relay init`），并向我报告项目看板初始化状态！
```
