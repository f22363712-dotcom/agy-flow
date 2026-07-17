# Task: task-018 - agent-relay GitHub开源发布 + 宣发视频故事板

## Metadata
- **ID**: task-018
- **Title**: agent-relay GitHub开源发布 + 宣发视频故事板
- **Assigned Agent**: claude -> antigravity -> codex -> claude
- **Status**: In Progress
- **Created Time**: 2026-07-17 00:45:31

## Requirements & Spec

### Phase 1: GitHub 开源发布准备（Claude）
1. **安全审计** — 扫描仓库中硬编码的 API key/token/secret
2. **LICENSE** — MIT 许可证
3. **.gitignore** — Python 项目标准 + agent-relay 特定忽略
4. **README.md** — 项目定位、安装、使用、架构
5. **CONTRIBUTING.md** — 贡献指南

### Phase 2: 宣发视频故事板（Antigravity）
- 基于三端联通素材设计 30-40 秒竖屏视频故事板
- 视觉风格参考 agent-relay Dashboard 暗色玻璃拟态
- 输出：视频脚本、分镜、画面描述

### Phase 3: 视频制作（Codex）
- 用 Remotion 或现有管线渲染最终视频

### Phase 4: 最终发布（Claude）
- GitHub Release + 视频发布

## 文件改动清单
- [ ] `LICENSE` — MIT
- [ ] `.gitignore` — 标准 Python
- [ ] `README.md` — 完整项目文档
- [ ] `CONTRIBUTING.md` — 贡献指南
- [ ] 安全审计 — 移除敏感信息

## Acceptance Criteria
- [ ] GitHub 仓库准备完毕（README/LICENSE/.gitignore/CONTRIBUTING）
- [ ] 安全审计通过，无硬编码凭证
- [ ] 视频故事板由 Antigravity 完成
- [ ] 最终视频产出
- [ ] GitHub Release v1.0.0
