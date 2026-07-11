"""测试 classify_task 智能路由的测试脚本。"""

from agy_flow_classify import classify_task
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

test_cases = [
    # (title, expected_agent, description)
    # ===== 逻辑/算法任务 → Claude =====
    ("实现冒泡排序算法", "claude", "排序算法"),
    ("设计用户认证API接口", "claude", "后端API"),
    ("爬取链家二手房数据", "claude", "爬虫"),
    ("实现 Redis 缓存层", "claude", "缓存/中间件"),
    ("编写数据分析脚本", "claude", "数据处理"),
    ("实现 JWT 登录认证", "claude", "认证逻辑"),
    ("写单元测试覆盖所有模块", "claude", "测试"),
    ("创建命令行工具", "claude", "CLI工具"),
    ("机器学习模型训练", "claude", "ML/AI"),
    ("数据库表结构设计", "claude", "数据库"),
    # ===== UI/前端任务 → Antigravity =====
    ("设计用户登录页面", "antigravity", "登录页UI"),
    ("实现首页导航栏布局", "antigravity", "导航布局"),
    ("美化系统仪表盘界面", "antigravity", "仪表盘UI"),
    ("开发响应式前端组件", "antigravity", "响应式"),
    ("编写CSS样式美化按钮", "antigravity", "CSS样式"),
    ("创建 React 用户表单组件", "antigravity", "React组件"),
    ("页面视觉走查", "antigravity", "视觉走查"),
    ("侧边栏动画效果", "antigravity", "动画"),
    ("设计卡片式布局", "antigravity", "卡片布局"),
    ("弹窗对话框组件", "antigravity", "弹窗组件"),
    # ===== 手动/调试任务 → Codex（严格大于才路由） =====
    ("手动调试数据库连接问题", "codex", "手动>逻辑→codex"),
    ("重构用户模块代码", "codex", "重构→codex"),
    ("Docker 容器化部署", "codex", "容器化+部署→codex"),
    ("Code Review 代码审查", "codex", "review+code→codex"),
    ("手动配置 CI/CD 流水线", "codex", "CI/CD+手动→codex"),
    ("升级第三方依赖库", "codex", "升级→codex"),
    ("Setup 开发环境配置", "codex", "setup+配置→codex"),
    # ===== 平局/混合场景 → 默认归 Claude（保守策略） =====
    (
        "修复登录页面的 Bug",
        "antigravity",
        "页面+登录+登录页(ui=3)>修复+Bug(man=2)→antigravity",
    ),
    ("优化后端查询性能", "claude", "优化(man=1)=后端(logic=1)→平局归Claude"),
    ("迁移旧系统数据库", "claude", "迁移(man=1)=数据库(logic=1)→平局归Claude"),
    ("API 和 UI 都有", "claude -> antigravity", "API(1)=UI(1)→含有“和”→协同流水线"),
    ("UI 和 API 调试", "claude -> antigravity", "三方平局→含有“和”→协同流水线"),
    # ===== UI 严格胜出的混合场景 =====
    (
        "修复前端页面布局Bug",
        "antigravity",
        "前端+页面+布局(ui=3)>修复+Bug(man=2)→antigravity",
    ),
    # ===== 边界情况 =====
    ("创建一个项目", "claude", "无关键词→默认Claude"),
    ("帮我做个东西", "claude", "模糊请求→默认Claude"),
    ("!", "claude", "特殊字符→默认Claude"),
    ("", "claude", "空标题→默认Claude"),
]

passed = 0
failed = 0

for title, expected, desc in test_cases:
    result = classify_task(title)
    status = "✅" if result == expected else "❌"
    if result == expected:
        passed += 1
    else:
        failed += 1
    print(
        f'  {status} [{desc:16s}] "{title[:40]:40s}" → {result:12s} (期望: {expected})'
    )

print("\n" + "=" * 60)
print(f"结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 个测试")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
