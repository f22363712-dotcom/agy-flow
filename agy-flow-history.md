# Agy-Flow 跨平台 AI 协同框架开发会话备忘录

## 任务背景
在 `D:\multi_agent_collaboration` 中继续开发 `agy-flow` 协同框架。本项目旨在构建一个本地协同框架，将任务根据能力和成本高效路由给不同的 Agent（如 Codex、Antigravity、DeepSeek 等），实现便宜优先（cheap-first）、可审计、可接力的跨平台协同。

本次会话中，我们遵循计划一步步完成了以下核心阶段：
1. **Phase 5：本地最小 HTTP Gateway (已验证)**
2. **Phase 6：网关写入操作支持与进程保护 (已验证)**
3. **Phase 7：本地可视化看板 Dashboard 界面直接托管 (已验证)**

## 详细改动

### 1. HTTP 协议服务器实现 (读写全接口 & 静态页面托管)
修改文件：`agy-flow.py`
- 导入 Python 标准库 `urllib.parse`、`BaseHTTPRequestHandler` 和 `HTTPServer`。
- 实现 `AgyFlowHTTPHandler(BaseHTTPRequestHandler)`，定义以下端点：
  - **读端点**：
    - `GET /` 和 `GET /dashboard` (Phase 7 扩展)：返回内嵌 of 可视化交互看板 UI 界面。
    - `GET /health`：返回健康状态及项目根路径。
    - `GET /tasks`：读取任务看板，并返回任务列表。
    - `GET /tasks/{task_id}`：根据指定的任务 ID，读取任务描述 MD 以及对应的规划 JSON。
    - `GET /tasks/{task_id}/handoff-plan`：计算并返回该任务的交接细节（包括当前 Agent、交接路径、下一位 Agent 任务信息等）。
  - **写端点** (Phase 6 扩展)：
    - `POST /plan`：接收包含任务标题的 JSON，并返回计算好的智能路由计划。
    - `POST /tasks`：创建新任务。接收 `{"title": "...", "agent": "...", "desc": "..."}`。如果未指定 Agent 则由内部路由智能分类计算。返回状态 201。
    - `POST /tasks/{task_id}/start`：触发该任务隔离 Git 工作区及分支的创建。
    - `POST /tasks/{task_id}/submit`：接收可选的 `{"test_cmd": "..."}` 并提审代码、计算成本和处理接力。
- **SystemExit 防御捕获**：在 do_POST 写操作中，使用 `try...except SystemExit` 对核心调用进行包裹，拦截了 CLI 命令执行失败时的 `sys.exit` 行为，防止其导致整个 HTTP 网关服务崩溃退出，转而返回标准的 `400 Bad Request` 错误 JSON。
- **CORS 支持**：添加了通用的 CORS 支持（包括对 `OPTIONS` 预检请求的 204 回应），确保本地网页应用及 VS Code WebView 能够正常跨域请求。

### 2. 本地可视化看板 Dashboard 界面
- **玻璃拟态暗黑美学 (Glassmorphism Dark Mode)**：引入 Google 字体 `Outfit`、半透明发光卡片、渐变任务列头部，给开发者极具现代感的视觉体验。
- **全套 REST API 交互**：
  - **实时智能分类规划预测 (Live Planning Preview)**：在新建任务窗口中输入标题时，自带 500ms 防抖自动请求 `/plan` API，在输入框下方以树形接力步骤直观展示推荐的 Agent pipeline、置信度和任务类型评分。
  - **隔离区一键式控制**：在看板卡片上点击“启动任务”或“提审代码”，可在前端直接通过 API 呼叫网关，并有友好的弹窗供输入测试校验脚本，摆脱 CLI 终端繁复敲打的局限。
  - **任务接力图谱查看**：双击卡片或点击卡片标题，弹窗以图表和格式化文本直观展示任务具体描述、工作区路径、Git 分支以及详细的 `.plan.json` 属性。

### 3. 自动化集成测试脚本
修改文件：`test_serve.py`
- 使用 Python 动态模块加载技术载入带有连字符的 `agy-flow.py`。
- 使用 `unittest` 框架在后台启动一个独立线程运行 HTTP 服务器。
- 编写测试用例覆盖全部 11 个服务端点（新增了对 HTML 网页端点 `/` 和 `/dashboard` 的返回类型与标签内容的测试用例 `test_dashboard_endpoint`）。
