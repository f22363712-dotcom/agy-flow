# 多 Coding Agent 协同工作框架：调研与需求分析报告 (v2)

本报告旨在梳理三个 AI 编程助手（Codex, Claude Code, Antigravity）协同工作的技术调研、需求细化、方案选型以及具体的工作流设计。

---

## 一、 工作流合理性评估与审查

您提出的工作流：
> **调研 -> 细化需求 -> 寻找参考 -> 确定技术路线和方案 -> 执行 -> 版本管理 -> 日志保存 -> 过程记录与写作 -> 系统落地与测试**

这是一个非常完整、严谨且符合现代化软件工程（尤其是 AI 辅助工程）的开发闭环。针对您配置的三 Agent 协作场景，该工作流不仅合理，而且在以下几个方面具有关键的指导意义：
1. **调研与参考的必要性**：多 Agent 协同面临最大的挑战是**冲突（Git 冲突、文件写冲突）**与**上下文同步**。调研行业内关于多 Agent 协作的最佳实践可以让我们避免“重复造轮子”或陷入常见的死锁和覆盖深渊。
2. **确定技术路线和方案**：明确定义三个 Agent 的能力边界（如 Claude Code 负责逻辑与测试，Antigravity 负责视觉与宏观设计，Codex 负责实时交互与微调），并利用 Git 分支或 Worktree 进行物理隔离。
3. **日志与过程记录**：AI 协同中，由于存在异步运行、多次调用，完整的日志保存和“过程写作”（如更新任务板、记录 Prompt）是复盘与调试 AI 错误的关键。

---

## 二、 技术调研与参考 (Research & References)

根据最新的行业动态和技术社区实践，多 Agent 协同的核心痛点与解决方案如下：

### 1. 核心痛点
*   **上下文冲突（Context Bleeding & Write Collision）**：若多个 Agent 在同一目录并行运行，会互相读取到未完成的中间代码，或在保存时产生覆盖冲突。
*   **成本/能力失衡（Cost/Capability Mismatch）**：
    *   **Claude Code (DeepSeek API)**：单次 Token 极其廉价，推理与逻辑编写极强，但**没有视觉能力（Non-Vision）**，也无法直接渲染 UI 或查看截图。
    *   **Antigravity (Gemini)**：拥有强大的视觉能力、图片生成、浏览器子代理，但可能存在 API 调用次数或额度限制，需要将其用在“刀刃”上（如 UI 设计验证、多模态任务、高层决策）。
    *   **Codex/Copilot**：基于 IDE 内置，适合开发者进行“人机结对”的实时微调，不适合大规模自动化跑批。
*   **状态不可见（Lack of Observability）**：当 AI 异步跑任务时，开发者难以直观了解各个 Agent 的进度，且不易插手干预。

### 2. 行业优秀实践与可借鉴方案
*   **Git Worktree 隔离机制 (借鉴: Claude Code `--worktree`, STORM, Augment)**：主流 AI 并行开发框架采用 Git Worktree。它允许在同一个本地 Git 仓库下，将不同的分支检出到不同的物理文件夹，从而让不同的 Agent 在完全隔离的环境中运行，互不干扰，最后通过标准的 Git Merge/PR 汇总。
*   **Git-Native 任务管理 (借鉴: Beads, Agent-Tasks)**：将任务看板（Todo, In Progress, Blocked, Done）作为结构化文件（Markdown 或 JSON）直接提交到 Git 仓库中。由于是文本文件，所有 Agent 都可以利用其 File I/O 读写并更新任务状态，实现状态在分布式/多分支间的自然流转。
*   **动态 Agent 指导 (借鉴: CLAUDE.md 模式)**：Claude Code 在启动时会读取 `CLAUDE.md` 以获取项目规范。可以通过脚本**动态更新**该文件，将当前分支被分配的具体 Task Spec 注入进去，从而使 Agent 启动时就处于“专职工作状态”。对于 Antigravity，我们可以更新 `.agents/AGENTS.md` 文件。

---

## 三、 三 Agent 角色分工与协同机制

为了将成本与模型优势最大化，我们设计如下分工与协同机制：

### 1. 角色与能力模型

| Agent / 工具 | 核心优势 | 局限性 | 框架中的分工定位 |
| :--- | :--- | :--- | :--- |
| **Claude Code**<br>(DeepSeek API) | 极高性价比、超强逻辑推理、测试驱动、命令行执行速度快 | 无视觉功能，无法直接截图/看图，受限于 CLI | **"逻辑码农" (Logic Developer)**<br>负责纯代码编写、算法实现、单元测试、CI/CD 修复。通过 `CLAUDE.md` 指导。 |
| **Antigravity**<br>(Gemini 3.5) | 多模态视觉（看图/截屏）、浏览器子代理、图像生成、擅长高层架构设计 | 额度稀缺/有成本考量 | **"架构师兼视觉 QA" (Architect & Visual QA)**<br>负责生成任务 Spec、UI 视觉审查、复杂架构规划、多模态交互。通过 `.agents/AGENTS.md` 指导，通过在专属 Worktree 文件夹中运行命令来进行开发与走查。 |
| **Codex / Copilot**<br>(IDE 插件) | IDE 高度集成、实时行级补全、人机交互体验好 | 订阅额度有限，无法自动执行复杂的多步骤 CLI 任务 | **"人机接口" (Developer Copilot)**<br>供人类开发者在主工作区或专属 Worktree 快速微调、代码 Review 和解决合并冲突。 |

### 2. 协同联动机制 (The Orchestration Flow)
1. **任务分发**：用户运行 `agent-relay task create` 创建任务，并指定 `agent` 属性。
2. **工作区拉起**：运行 `agent-relay task start <task-id>`：
   - 自动生成专属 Git 分支 `agent/task-00X`。
   - 通过 `git worktree add` 在 `D:\multi_agent_worktrees\task-00X` 拉起独立隔离目录。
   - 写入针对该 Agent 的动态上下文文件（`CLAUDE.md` 或 `.agents/AGENTS.md`）。
3. **任务开发**：
   - **Claude Code**：在对应 Worktree 目录启动非交互式命令（如 `claude -p`），完成算法与测试。
   - **Codex**：用户在 VS Code 中将工作区切换至该 Worktree 目录，配合 Codex 插件进行手动微调。
   - **Antigravity**：由于 Antigravity 是本会话的 Host Agent，CLI 在激活 Antigravity 任务时，会输出提示引导用户在当前 Chat 中与 Antigravity 交互。Antigravity 收到指令后，会通过工具（如 `run_command` 的 `Cwd` 参数）把操作目录限定在 `D:\multi_agent_worktrees\task-00X` 内，从而在该 worktree 中完成审查、代码调整及浏览器测试。
4. **提交与审核**：运行 `agent-relay task submit` 跑通测试并进行自动 Commit，任务归档为 `Review`。
5. **合并与清理**：管理员运行 `agent-relay task merge`，将代码合并至 `main` 分支，删除 Worktree 物理文件夹，清理 Worktree 记录，任务归档为 `Done`。

---

## 四、 技术路线与方案选型

我们拟采用以下技术路线来实现该协同框架：
1. **宿主语言**：**Python 3.x**。生态丰富，易于编写 CLI，支持直接调用 `git` 命令，且所有 Agent 对 Python 均有极强的读写能力。
2. **数据存储**：**Git 仓库本身 + Markdown/JSON 文件**。不需要额外的数据库，完美适配 Git 冲突解决机制。
3. **隔离机制**：使用原生 `git worktree add <path> <branch>`。
4. **Agent 配置劫持**：
   - 写入 `CLAUDE.md` 自动引导 Claude Code。
   - 写入 `.agents/AGENTS.md` 自动引导 Antigravity。
5. **自动化运行**：
   - 使用 `subprocess` 执行 `claude -p "..." --allowedTools "Edit,Read,Bash" --permission-mode dontAsk` 来触发 Claude Code 的非交互式自动编码。
