"""智能路由分类模块 — 根据任务标题自动判断最适合的 Agent。"""

from __future__ import annotations

from typing import Any


DEFAULT_AGENT_REGISTRY = {
    "claude": {
        "display_name": "Claude Code",
        "kind": "cli_agent",
        "entry": "claude",
        "capabilities": ["code_edit", "logic", "test", "refactor"],
        "cost_mode": "metered",
    },
    "antigravity": {
        "display_name": "Antigravity",
        "kind": "desktop_agent",
        "entry": "antigravity",
        "capabilities": ["vision", "browser", "ui_review", "large_context"],
        "cost_mode": "subscription",
    },
    "codex": {
        "display_name": "Codex",
        "kind": "human_in_loop",
        "entry": "vscode",
        "capabilities": ["code_edit", "debug", "review", "manual_tuning"],
        "cost_mode": "subscription",
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "kind": "llm_api",
        "entry": "litellm",
        "capabilities": ["cheap_analysis", "planning", "review", "classification"],
        "cost_mode": "metered_low",
    },
}

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


def score_task(title: str) -> dict[str, Any]:
    """Return keyword scores used by both legacy routing and structured plans."""
    title_lower = title.lower()
    ui_score = sum(1 for kw in UI_KEYWORDS if kw in title_lower)
    logic_score = sum(1 for kw in LOGIC_KEYWORDS if kw in title_lower)
    manual_score = sum(1 for kw in MANUAL_KEYWORDS if kw in title_lower)
    has_coordination = any(
        w in title_lower for w in ["和", "并", "且", "然后", "接着", "and", "then"]
    )

    return {
        "ui": ui_score,
        "logic": logic_score,
        "manual": manual_score,
        "has_coordination": has_coordination,
    }


def classify_task(title: str, verbose: bool = True) -> str:
    """自动根据任务标题判断最适合的 Agent。

    Args:
        title: 任务标题。

    Returns:
        Agent 名称: "claude" | "antigravity" | "codex"
    """
    scores = score_task(title)
    ui_score = scores["ui"]
    logic_score = scores["logic"]
    manual_score = scores["manual"]

    if verbose:
        print(
            f'[智能路由] 标题: "{title}" → '
            f"UI评分={ui_score}, 逻辑评分={logic_score}, 手动评分={manual_score}"
        )

    # 协同流水线规则：如果匹配到多个类别，且含有明确的“并/和/然后/and”等接力词
    has_coordination = scores["has_coordination"]

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


def _confidence(scores: dict[str, Any]) -> float:
    ranked = sorted([scores["ui"], scores["logic"], scores["manual"]], reverse=True)
    if ranked[0] == 0:
        return 0.35
    if ranked[0] == ranked[1]:
        return 0.55
    return min(0.95, 0.6 + ((ranked[0] - ranked[1]) * 0.12))


def _task_type(scores: dict[str, Any]) -> str:
    if scores["logic"] >= 1 and scores["ui"] >= 1:
        return "full_stack_or_ui_integrated"
    if scores["ui"] > scores["logic"] and scores["ui"] >= scores["manual"]:
        return "ui_or_visual"
    if scores["manual"] > scores["ui"] and scores["manual"] > scores["logic"]:
        return "debug_or_manual_tuning"
    if scores["logic"] > 0:
        return "logic_or_backend"
    return "ambiguous"


def _pipeline_for_route(legacy_route: str, task_type: str) -> list[dict[str, str]]:
    legacy_agents = [agent.strip() for agent in legacy_route.split("->")]
    pipeline: list[dict[str, str]] = []

    if task_type in {"full_stack_or_ui_integrated", "ambiguous"}:
        pipeline.append(
            {
                "agent": "deepseek",
                "role": "planner",
                "purpose": "cheap-first task decomposition and risk scan",
            }
        )

    role_by_agent = {
        "claude": "implementer",
        "codex": "human_in_loop_implementer",
        "antigravity": "visual_reviewer",
    }
    purpose_by_agent = {
        "claude": "logic-heavy coding, tests, and CLI execution",
        "codex": "IDE-assisted debugging, refactor, and manual polish",
        "antigravity": "browser, multimodal, and UI quality validation",
    }

    for agent in legacy_agents:
        pipeline.append(
            {
                "agent": agent,
                "role": role_by_agent.get(agent, "worker"),
                "purpose": purpose_by_agent.get(agent, "execute assigned work"),
            }
        )

    if task_type in {"logic_or_backend", "debug_or_manual_tuning"}:
        pipeline.append(
            {
                "agent": "deepseek",
                "role": "reviewer",
                "purpose": "low-cost diff review before final handoff",
            }
        )

    return pipeline


def plan_task(
    title: str, agent_registry: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Return a structured routing plan without changing existing task state."""
    scores = score_task(title)
    legacy_route = classify_task(title, verbose=False)
    task_type = _task_type(scores)
    confidence = _confidence(scores)
    pipeline = _pipeline_for_route(legacy_route, task_type)
    registry = agent_registry or DEFAULT_AGENT_REGISTRY

    return {
        "title": title,
        "task_type": task_type,
        "confidence": round(confidence, 2),
        "scores": {
            "ui": scores["ui"],
            "logic": scores["logic"],
            "manual": scores["manual"],
        },
        "legacy_agent": legacy_route,
        "recommended_pipeline": pipeline,
        "policy": {
            "strategy": "cheap-first, escalate-on-uncertainty",
            "requires_worktree": any(
                step["agent"] in {"claude", "codex", "antigravity"}
                for step in pipeline
            ),
            "budget_bias": "subscription_or_low_metered",
        },
        "agent_registry": registry,
    }
