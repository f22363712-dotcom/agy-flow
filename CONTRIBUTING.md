# Contributing to agent-relay

感谢你考虑为 agent-relay 贡献！🎉

## 行为准则

本项目采用 [Contributor Covenant](https://www.contributor-covenant.org/) 行为准则。参与即表示你同意遵守其条款。

## 如何贡献

### 报告 Bug

1. 检查 Issue 列表中是否已有相同问题
2. 新建 Issue，包含：
   - 环境信息（OS、Python 版本、工具版本）
   - 复现步骤
   - 期望行为 vs 实际行为
   - 相关日志或截图

### 提交 PR

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/my-feature`
3. 提交改动：`git commit -m "feat: add my feature"`
4. 推送到你的 Fork：`git push origin feat/my-feature`
5. 提交 Pull Request

### 开发指南

**代码风格**：
- Python 代码使用 `black` + `ruff` 格式化
- 类型标注：使用 `str | None` 而非 `Optional[str]`
- 优先使用标准库，避免不必要的依赖

**测试**：
- 新功能必须有测试覆盖
- 运行 `python -m pytest` 确保所有测试通过
- 端到端：`python scripts/mcp_client_smoke.py`

**提交信息格式**：
```
<type>: <简短描述>

<可选详细说明>
```

类型：`feat` / `fix` / `docs` / `test` / `refactor` / `chore`

### PR 合并条件

- ✅ 所有测试通过
- ✅ 代码风格符合规范
- ✅ 有测试覆盖（新功能）
- ✅ 文档已更新（如适用）

## 项目结构

```
agent-relay/
├── agent_relay/           # 核心库
│   ├── mcp_server.py   # MCP Server
│   ├── handoff.py      # 接力协议
│   ├── router.py       # 路由
│   ├── tasks.py        # 任务管理
│   └── gateway.py      # Dashboard
├── test_*.py           # 测试文件
├── scripts/            # 工具脚本
└── .agents/            # 运行时状态（生成）
```
