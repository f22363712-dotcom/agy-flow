"""智能路由分类模块 — 根据任务标题自动判断最适合的 Agent。"""

# 视觉/UI/前端/布局 → Antigravity（多模态）
UI_KEYWORDS = [
    "ui",
    "界面",
    "布局",
    "页面",
    "前端",
    "css",
    "html",
    "视觉",
    "走查",
    "button",
    "component",
    "渲染",
    "layout",
    "style",
    "样式",
    "图标",
    "icon",
    "动画",
    "animation",
    "响应式",
    "responsive",
    "移动端",
    "mobile",
    "web",
    "首页",
    "登录",
    "登录页",
    "注册",
    "注册页",
    "仪表盘",
    "dashboard",
    "导航",
    "导航栏",
    "navbar",
    "侧边栏",
    "sidebar",
    "卡片",
    "card",
    "表格",
    "表单",
    "form",
    "弹窗",
    "modal",
    "对话框",
    "dialog",
    "颜色",
    "字体",
    "font",
    "color",
    "主题",
    "theme",
    "vue",
    "react",
    "angular",
    "svelte",
    "tailwind",
    "bootstrap",
]

# 算法/后端/逻辑 → Claude（推理引擎）
LOGIC_KEYWORDS = [
    "算法",
    "api",
    "接口",
    "后端",
    "逻辑",
    "排序",
    "搜索",
    "数据库",
    "认证",
    "auth",
    "crud",
    "数据处理",
    "爬虫",
    "spider",
    "scraper",
    "server",
    "服务端",
    "中间件",
    "middleware",
    "路由",
    "route",
    "模型",
    "model",
    "schema",
    "序列化",
    "serializer",
    "验证",
    "validation",
    "权限",
    "permission",
    "登录",
    "login",
    "注册",
    "register",
    "token",
    "jwt",
    "oauth",
    "加密",
    "encrypt",
    "hash",
    "缓存",
    "cache",
    "redis",
    "mq",
    "队列",
    "queue",
    "测试",
    "test",
    "单元测试",
    "unittest",
    "pytest",
    "命令行",
    "cli",
    "命令行工具",
    "脚本",
    "script",
    "数据分析",
    "data analysis",
    "机器学习",
    "ml",
    "深度学习",
    "deep learning",
    "ai",
    "llm",
]

# 人工微调/手动交互 → Codex（IDE 协作）
MANUAL_KEYWORDS = [
    "手动",
    "调试",
    "fix",
    "修复",
    "bug",
    "重构",
    "refactor",
    "优化",
    "optimize",
    "重构",
    "review",
    "code review",
    "迁移",
    "migrate",
    "升级",
    "upgrade",
    "配置",
    "config",
    "setup",
    "部署",
    "deploy",
    "ci/cd",
    "ci",
    "docker",
    "容器化",
]


def classify_task(title: str) -> str:
    """自动根据任务标题判断最适合的 Agent。

    Args:
        title: 任务标题。

    Returns:
        Agent 名称: "claude" | "antigravity" | "codex"
    """
    title_lower = title.lower()

    ui_score = sum(1 for kw in UI_KEYWORDS if kw in title_lower)
    logic_score = sum(1 for kw in LOGIC_KEYWORDS if kw in title_lower)
    manual_score = sum(1 for kw in MANUAL_KEYWORDS if kw in title_lower)

    print(
        f'[智能路由] 标题: "{title}" → '
        f"UI评分={ui_score}, 逻辑评分={logic_score}, 手动评分={manual_score}"
    )

    # 协同流水线规则：如果匹配到多个类别，且含有明确的“并/和/然后/and”等接力词
    has_coordination = any(w in title_lower for w in ["和", "并", "且", "然后", "接着", "and", "then"])

    if has_coordination:
        if logic_score >= 1 and ui_score >= 1:
            return "claude -> antigravity"
        elif logic_score >= 1 and manual_score >= 1:
            return "claude -> codex"
        elif ui_score >= 1 and manual_score >= 1:
            return "codex -> antigravity"

    # 单一 Agent 回退规则
    if manual_score > ui_score and manual_score > logic_score:
        return "codex"
    elif ui_score > logic_score and ui_score > manual_score:
        return "antigravity"
    else:
        return "claude"
