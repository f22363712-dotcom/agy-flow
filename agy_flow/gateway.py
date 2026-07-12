import json
import traceback
import sys
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from agy_flow.errors import AgyFlowError
from agy_flow.config import PROJECT_ROOT, get_config, get_agent_registry, get_llm_agent_settings
from agy_flow.tasks import parse_board_rows, create_task, start_task, submit_task
from agy_flow.handoff import load_task_plan, get_handoff_steps, find_next_handoff_step, assign_current_task_agent
from agy_flow.llm import review_task_service, call_openai_compatible_chat
from agy_flow_classify import plan_task

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>agy-flow | 协同看板</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-grad: linear-gradient(135deg, #0f0c1b 0%, #15102a 50%, #090514 100%);
            --panel-bg: rgba(255, 255, 255, 0.03);
            --card-bg: rgba(255, 255, 255, 0.04);
            --card-hover: rgba(255, 255, 255, 0.08);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f1f9;
            --text-secondary: #9b98b0;
            --accent-glow: rgba(124, 77, 255, 0.5);
            --accent-purple: #7c4dff;
            --accent-cyan: #00e5ff;
            --accent-gold: #ffd700;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-grad);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }
        header {
            padding: 24px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: rgba(15, 12, 27, 0.5);
            backdrop-filter: blur(10px);
        }
        .logo-section h1 {
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 1px;
            background: linear-gradient(45deg, #ffd700, #ff007f, #7c4dff, #00e5ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: inline-block;
        }
        .logo-section p {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 2px;
        }
        .btn {
            background: linear-gradient(90deg, var(--accent-purple), var(--accent-cyan));
            border: none;
            color: #fff;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(124, 77, 255, 0.3);
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 229, 255, 0.4);
        }
        .container {
            display: flex;
            flex: 1;
            padding: 30px 40px;
            gap: 24px;
            overflow-x: auto;
            align-items: flex-start;
        }
        .column {
            flex: 0 0 320px;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            max-height: calc(100vh - 180px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        .column-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .column-title {
            font-size: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .column-count {
            background: rgba(255, 255, 255, 0.08);
            padding: 2px 8px;
            border-radius: 20px;
            font-size: 12px;
            color: var(--text-secondary);
        }
        .task-list {
            display: flex;
            flex-direction: column;
            gap: 14px;
            overflow-y: auto;
            flex: 1;
            padding-right: 4px;
        }
        .task-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            overflow: hidden;
        }
        .task-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; width: 4px; height: 100%;
            background: var(--accent-purple);
            opacity: 0.7;
        }
        .task-card:hover {
            background: var(--card-hover);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .task-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 8px;
            line-height: 1.4;
        }
        .task-meta {
            font-size: 11px;
            color: var(--text-secondary);
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .task-actions {
            margin-top: 12px;
            display: flex;
            gap: 8px;
        }
        .btn-sm {
            flex: 1;
            padding: 6px 0;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(255,255,255,0.05);
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn-sm:hover {
            background: var(--accent-purple);
            border-color: transparent;
        }
        .agent-badge {
            background: rgba(124, 77, 255, 0.15);
            color: #b388ff;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
            align-self: flex-start;
            margin-top: 4px;
        }
        /* Modal dialog styling */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(10, 6, 21, 0.8);
            backdrop-filter: blur(8px);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: #110d22;
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 30px;
            width: 500px;
            max-width: 90%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            position: relative;
        }
        .modal-header {
            margin-bottom: 20px;
            font-size: 18px;
            font-weight: 800;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
            font-weight: 600;
        }
        .form-group input, .form-group textarea, .form-group select {
            width: 100%;
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-primary);
            font-family: inherit;
            outline: none;
        }
        .form-group input:focus, .form-group textarea:focus {
            border-color: var(--accent-purple);
            box-shadow: 0 0 10px rgba(124, 77, 255, 0.2);
        }
        .form-actions {
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }
        .btn-cancel {
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
        }
        .btn-cancel:hover {
            color: var(--text-primary);
            background: rgba(255,255,255,0.05);
        }
        .plan-preview {
            background: rgba(255,255,255,0.02);
            border: 1px dashed var(--border-color);
            border-radius: 8px;
            padding: 12px;
            margin-top: 10px;
            font-size: 12px;
            color: var(--text-secondary);
        }
        .plan-preview-step {
            margin-top: 6px;
            padding-left: 10px;
            border-left: 2px solid var(--accent-purple);
        }
        .detail-item {
            margin-bottom: 12px;
            font-size: 13px;
        }
        .detail-label {
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }
        .detail-val {
            background: rgba(255,255,255,0.02);
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1>agy-flow 协同控制看板</h1>
            <p>基于 Git Worktrees 的多智能体流水线协同与自动接力系统</p>
        </div>
        <div>
            <button class="btn" onclick="openCreateModal()">新建任务</button>
        </div>
    </header>

    <div class="container" id="board-container">
        <!-- columns dynamically inserted -->
    </div>

    <!-- Create Task Modal -->
    <div class="modal" id="create-modal">
        <div class="modal-content">
            <div class="modal-header">新建协同开发任务</div>
            <div class="form-group">
                <label for="task-title">任务标题</label>
                <input type="text" id="task-title" placeholder="如：设计前端用户中心卡片，实现 API 接口对接..." oninput="triggerPlanPreviewDebounce()">
                <div class="plan-preview" id="plan-preview-box" style="display:none;">
                    <strong>🤖 智能路由器推荐规划预测：</strong>
                    <div id="plan-preview-content">暂无</div>
                </div>
            </div>
            <div class="form-group">
                <label for="task-desc">详细描述说明</label>
                <textarea id="task-desc" rows="4" placeholder="任务的具体需求、验收标准和相关注意事项..."></textarea>
            </div>
            <div class="form-group">
                <label for="task-agent">指定首发/协同 Agent (可选)</label>
                <select id="task-agent">
                    <option value="">自动检测 (Cheap-First 推荐路由)</option>
                    <option value="claude">Claude (精通系统架构/核心开发)</option>
                    <option value="antigravity">Antigravity (视觉走查/测试优化)</option>
                    <option value="codex">Codex (VS Code 本地手动协作开发)</option>
                    <option value="deepseek">DeepSeek/LiteLLM (常规逻辑/代码审查)</option>
                </select>
            </div>
            <div class="form-actions">
                <button class="btn-cancel" onclick="closeCreateModal()">取消</button>
                <button class="btn" onclick="submitCreateTask()">确认创建</button>
            </div>
        </div>
    </div>

    <!-- Task Detail Modal -->
    <div class="modal" id="detail-modal">
        <div class="modal-content" style="width: 600px; max-height: 90vh; overflow-y: auto;">
            <div class="modal-header" id="detail-title">任务详情</div>
            <div class="detail-item">
                <div class="detail-label">任务状态 & 协同智能体</div>
                <div style="display:flex; gap: 8px; align-items:center;">
                    <span id="detail-status" style="font-weight:600;">Todo</span>
                    <span id="detail-agent" class="agent-badge">claude</span>
                </div>
            </div>
            <div class="detail-item">
                <div class="detail-label">隔离分支 & 绝对工作区路径</div>
                <div class="detail-val" id="detail-workspace" style="font-family:monospace; font-size:11px;">-</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">交接路由细节</div>
                <div class="detail-val" id="detail-handoff" style="font-size:12px;">无</div>
            </div>
            
            <!-- Step 5: Handoff and Assign Section -->
            <div class="detail-item">
                <div class="detail-label">手动指派/协同交接 Agent</div>
                <div style="display:flex; gap: 10px; align-items: center; margin-top: 5px;">
                    <select id="detail-assign-select" style="flex: 1; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 12px; color: var(--text-primary); outline: none;">
                        <!-- Options dynamically loaded from registry -->
                    </select>
                    <button class="btn" style="padding: 8px 16px; font-size: 12px;" onclick="triggerHandoffAssign()">执行移交</button>
                </div>
            </div>

            <!-- Step 5: AI Code Review Section -->
            <div class="detail-item">
                <div class="detail-label" style="display:flex; justify-content:space-between; align-items:center;">
                    <span>DeepSeek AI 智能代码审查</span>
                    <div style="display:flex; gap: 8px;">
                        <button class="btn" style="padding: 6px 12px; font-size: 11px; background: rgba(0, 229, 255, 0.15); color: var(--accent-cyan); border: 1px solid rgba(0, 229, 255, 0.3);" onclick="triggerDeepseekReview(false)">AI 真实审查</button>
                        <button class="btn" style="padding: 6px 12px; font-size: 11px; background: rgba(255, 215, 0, 0.15); color: var(--accent-gold); border: 1px solid rgba(255, 215, 0, 0.3);" onclick="triggerDeepseekReview(true)">Mock 模拟审查</button>
                    </div>
                </div>
                <div id="detail-review-container" style="margin-top: 10px;">
                    <div id="detail-review-badge-row" style="display:none; margin-bottom: 6px;">
                        <span id="detail-review-badge" class="agent-badge" style="font-weight:600;">-</span>
                    </div>
                    <div class="detail-val" id="detail-review-box" style="font-size:12px; max-height: 200px; overflow-y: auto; background: rgba(255, 255, 255, 0.01); display: none;">暂无审查结果</div>
                </div>
            </div>

            <!-- Step 5: Agent Registry Configuration Section -->
            <div class="detail-item" style="border-top: 1px solid var(--border-color); padding-top: 15px; margin-top: 15px;">
                <div class="detail-label" style="cursor: pointer; display: flex; justify-content: space-between; align-items: center;" onclick="toggleRegistryCollapse()">
                    <span>🤖 系统智能体能力注册表 (agent_registry)</span>
                    <span id="registry-arrow">▼</span>
                </div>
                <div id="detail-registry-box" style="display: none; margin-top: 10px; font-size: 11px; color: var(--text-secondary); max-height: 150px; overflow-y: auto; font-family: monospace; white-space: pre-wrap; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; border: 1px solid var(--border-color);">
                    加载中...
                </div>
            </div>

            <div class="form-actions" style="margin-top: 20px;">
                <button class="btn-cancel" onclick="closeDetailModal()">关闭</button>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '';
        let debounceTimer = null;

        document.addEventListener('DOMContentLoaded', fetchTasks);

        function triggerPlanPreviewDebounce() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchPlanPreview, 500);
        }

        async function fetchPlanPreview() {
            const title = document.getElementById('task-title').value.trim();
            const previewBox = document.getElementById('plan-preview-box');
            const previewContent = document.getElementById('plan-preview-content');

            if (!title) {
                previewBox.style.display = 'none';
                return;
            }

            try {
                const res = await fetch(`${API_BASE}/plan`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title })
                });
                if (res.ok) {
                    const data = await res.json();
                    previewBox.style.display = 'block';
                    let stepsHtml = `<strong>[${data.task_type}]</strong> 预估置信度: ${data.confidence}<br>`;
                    if (data.recommended_pipeline && data.recommended_pipeline.length) {
                        data.recommended_pipeline.forEach((step, idx) => {
                            stepsHtml += `<div class="plan-preview-step">${idx + 1}. <strong>${step.agent}</strong> (${step.role}) - ${step.purpose}</div>`;
                        });
                    } else {
                        stepsHtml += `<div class="plan-preview-step">直接指派: <strong>${data.selected_agent}</strong></div>`;
                    }
                    previewContent.innerHTML = stepsHtml;
                }
            } catch (err) {
                console.error("Preview plan failed:", err);
            }
        }

        async function fetchTasks() {
            try {
                const res = await fetch(`${API_BASE}/tasks`);
                const tasks = await res.json();
                renderBoard(tasks);
            } catch (err) {
                alert("获取任务列表失败，请检查网关服务是否正常运行。");
            }
        }

        function renderBoard(tasks) {
            const columns = {
                'Todo': [],
                'In Progress': [],
                'Review': [],
                'Done': []
            };

            tasks.forEach(t => {
                let colName = 'Todo';
                if (t.status.startsWith('In Progress')) {
                    colName = 'In Progress';
                } else if (t.status === 'Review') {
                    colName = 'Review';
                } else if (t.status === 'Done') {
                    colName = 'Done';
                }
                if (columns[colName]) {
                    columns[colName].push(t);
                }
            });

            const board = document.getElementById('board-container');
            board.innerHTML = '';

            Object.keys(columns).forEach(colName => {
                const colTasks = columns[colName];
                const colHtml = `
                    <div class="column">
                        <div class="column-header">
                            <div class="column-title">
                                <span>${colName}</span>
                            </div>
                            <span class="column-count">${colTasks.length}</span>
                        </div>
                        <div class="task-list">
                            ${colTasks.map(t => `
                                <div class="task-card" onclick="viewTaskDetail('${t.id}')">
                                    <div class="task-title">${t.title}</div>
                                    <div class="task-meta">
                                        <div>ID: ${t.id}</div>
                                        <div class="agent-badge">${t.agent}</div>
                                        ${t.status.includes('(') ? `<div style="color:var(--accent-cyan); font-weight:600; margin-top:2px;">接力中: ${t.status}</div>` : ''}
                                    </div>
                                    <div class="task-actions" onclick="event.stopPropagation()">
                                        ${colName === 'Todo' ? `
                                            <button class="btn-sm" onclick="startTask('${t.id}')">启动任务</button>
                                        ` : ''}
                                        ${colName === 'In Progress' ? `
                                            <button class="btn-sm" onclick="submitTask('${t.id}')">提审代码</button>
                                        ` : ''}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
                board.innerHTML += colHtml;
            });
        }

        function openCreateModal() {
            document.getElementById('task-title').value = '';
            document.getElementById('task-desc').value = '';
            document.getElementById('task-agent').value = '';
            document.getElementById('plan-preview-box').style.display = 'none';
            document.getElementById('create-modal').style.display = 'flex';
        }

        function closeCreateModal() {
            document.getElementById('create-modal').style.display = 'none';
        }

        async function submitCreateTask() {
            const title = document.getElementById('task-title').value.trim();
            const desc = document.getElementById('task-desc').value.trim();
            const agent = document.getElementById('task-agent').value;

            if (!title) {
                alert("请输入任务标题。");
                return;
            }

            try {
                const res = await fetch(`${API_BASE}/tasks`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title, desc, agent: agent || null })
                });

                if (res.ok) {
                    closeCreateModal();
                    fetchTasks();
                } else {
                    const data = await res.json();
                    alert("创建失败: " + data.message);
                }
            } catch (err) {
                alert("请求失败，请检查后端网关状态。");
            }
        }

        async function startTask(taskId) {
            try {
                const res = await fetch(`${API_BASE}/tasks/${taskId}/start`, { method: 'POST' });
                if (res.ok) {
                    fetchTasks();
                } else {
                    const data = await res.json();
                    alert("启动失败: " + data.message);
                }
            } catch (err) {
                alert("请求出错。");
            }
        }

        async function submitTask(taskId) {
            const testCmd = prompt("请输入提交代码前执行的自动化校验测试命令(可选)：\n例如: python test_classify_task.py");
            if (testCmd === null) return; // 撤销

            try {
                const res = await fetch(`${API_BASE}/tasks/${taskId}/submit`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ test_cmd: testCmd })
                });
                if (res.ok) {
                    alert("提审/移交成功！状态已更新。");
                    fetchTasks();
                } else {
                    const data = await res.json();
                    alert("提交失败: " + data.message);
                }
            } catch (err) {
                alert("请求出错。");
            }
        }

        let currentViewingTaskId = null;
        let globalRegistry = null;

        document.addEventListener('DOMContentLoaded', () => {
            fetchTasks();
            fetchRegistry();
        });

        async function fetchRegistry() {
            try {
                const res = await fetch(`${API_BASE}/config/agent-registry`);
                if (res.ok) {
                    globalRegistry = await res.json();
                    
                    const select = document.getElementById('detail-assign-select');
                    select.innerHTML = '';
                    Object.keys(globalRegistry).forEach(agentKey => {
                        const agentInfo = globalRegistry[agentKey];
                        const option = document.createElement('option');
                        option.value = agentKey;
                        option.text = `${agentInfo.name || agentKey} (${agentInfo.role || 'Agent'})`;
                        select.appendChild(option);
                    });

                    document.getElementById('detail-registry-box').innerText = JSON.stringify(globalRegistry, null, 4);
                }
            } catch (err) {
                console.error("Failed to load agent registry:", err);
            }
        }

        function toggleRegistryCollapse() {
            const box = document.getElementById('detail-registry-box');
            const arrow = document.getElementById('registry-arrow');
            if (box.style.display === 'none') {
                box.style.display = 'block';
                arrow.innerText = '▲';
            } else {
                box.style.display = 'none';
                arrow.innerText = '▼';
            }
        }

        async function triggerHandoffAssign() {
            if (!currentViewingTaskId) return;
            const select = document.getElementById('detail-assign-select');
            const selectedAgent = select.value;
            
            try {
                const res = await fetch(`${API_BASE}/assign`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ agent: selectedAgent, task_id: currentViewingTaskId })
                });
                if (res.ok) {
                    alert(`任务已成功指派/移交给: ${selectedAgent}`);
                    fetchTasks();
                    viewTaskDetail(currentViewingTaskId);
                } else {
                    const data = await res.json();
                    alert("交接指派失败: " + (data.error || "未知错误"));
                }
            } catch (err) {
                alert("请求出错。");
            }
        }

        async function triggerDeepseekReview(mockFlag) {
            if (!currentViewingTaskId) return;
            const reviewBox = document.getElementById('detail-review-box');
            const badgeRow = document.getElementById('detail-review-badge-row');
            const badge = document.getElementById('detail-review-badge');

            reviewBox.style.display = 'block';
            reviewBox.innerText = "🔍 AI 智能代码审查中，正在对比分析工作区改动，请稍候……";
            badgeRow.style.display = 'none';

            try {
                const res = await fetch(`${API_BASE}/tasks/${currentViewingTaskId}/review`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mock: mockFlag })
                });

                const data = await res.json();
                badgeRow.style.display = 'block';

                if (res.ok) {
                    reviewBox.innerText = data.review || "无审查结果";
                    if (data.review_source === 'deepseek') {
                        badge.innerText = "Real DeepSeek";
                        badge.style.background = "rgba(0, 229, 255, 0.15)";
                        badge.style.color = "#00e5ff";
                    } else if (data.review_source === 'mock') {
                        badge.innerText = "Mock Review";
                        badge.style.background = "rgba(255, 215, 0, 0.15)";
                        badge.style.color = "#ffd700";
                    } else {
                        badge.innerText = "Missing API Key";
                        badge.style.background = "rgba(255, 64, 129, 0.15)";
                        badge.style.color = "#ff4081";
                    }
                } else {
                    reviewBox.innerText = data.review || data.error || "审查失败";
                    badge.innerText = "Missing API Key";
                    badge.style.background = "rgba(255, 64, 129, 0.15)";
                    badge.style.color = "#ff4081";
                }
            } catch (err) {
                reviewBox.innerText = "请求错误: " + err;
                badgeRow.style.display = 'block';
                badge.innerText = "Unavailable";
                badge.style.background = "rgba(255, 64, 129, 0.15)";
                badge.style.color = "#ff4081";
            }
        }

        async function viewTaskDetail(taskId) {
            currentViewingTaskId = taskId;
            
            document.getElementById('detail-review-box').style.display = 'none';
            document.getElementById('detail-review-box').innerText = '';
            document.getElementById('detail-review-badge-row').style.display = 'none';
            
            try {
                const detailRes = await fetch(`${API_BASE}/tasks/${taskId}`);
                const handoffRes = await fetch(`${API_BASE}/tasks/${taskId}/handoff-plan`);
                
                if (detailRes.ok) {
                    const t = await detailRes.json();
                    document.getElementById('detail-title').innerText = `任务详情: ${t.id}`;
                    document.getElementById('detail-status').innerText = t.status;
                    document.getElementById('detail-agent').innerText = t.agent;
                    document.getElementById('detail-workspace').innerText = `Git Branch : ${t.branch || 'None'}\nWorktree Path: ${t.worktree || 'None'}`;
                    
                    const select = document.getElementById('detail-assign-select');
                    if (select && t.agent) {
                        select.value = t.agent.split('->')[0].trim().toLowerCase();
                    }

                    if (handoffRes.ok) {
                        const h = await handoffRes.json();
                        let stepsText = `当前正在协作的智能体: ${h.active_agent}\n`;
                        stepsText += `工作流规划:\n`;
                        h.handoff_steps.forEach((step, idx) => {
                            const activeMark = step.agent === h.active_agent ? ' 👉' : '';
                            stepsText += `  ${idx + 1}. ${step.agent} (${step.role}) - ${step.purpose}${activeMark}\n`;
                        });
                        stepsText += h.next_step ? `\n下一交接目标: ${h.next_step.agent} (${h.next_step.role})` : `\n后续开发完毕即交由 review 进行验收。`;
                        document.getElementById('detail-handoff').innerText = stepsText;
                    } else {
                        document.getElementById('detail-handoff').innerText = "无详细交接规划。";
                    }

                    document.getElementById('detail-modal').style.display = 'flex';
                }
            } catch (err) {
                console.error("Fetch detail failed:", err);
            }
        }

        function closeDetailModal() {
            document.getElementById('detail-modal').style.display = 'none';
        }
    </script>
</body>
</html>
"""

class AgyFlowHTTPHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def send_json_error(self, code, message):
        self.send_response(code)
        self.send_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))

    def send_json_response(self, data, code=200):
        self.send_response(code)
        self.send_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in {'/', '/dashboard'}:
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
            return

        if path == '/health':
            self.send_json_response({"status": "ok", "project_root": str(PROJECT_ROOT)})
            return

        if path == '/config/agent-registry':
            try:
                registry = get_agent_registry(get_config())
                safe_registry = {}
                for agent_name, agent_cfg in registry.items():
                    safe_agent_cfg = agent_cfg.copy()
                    keys_to_delete = [
                        k for k in safe_agent_cfg.keys()
                        if any(x in k.lower() for x in ["api_key", "secret", "token", "password"])
                        and k != "api_key_env"
                    ]
                    for k in keys_to_delete:
                        del safe_agent_cfg[k]
                    safe_registry[agent_name] = safe_agent_cfg
                self.send_json_response(safe_registry)
            except Exception as e:
                self.send_json_error(500, f"Failed to get agent registry: {e}")
            return

        if path == '/tasks':
            try:
                tasks = parse_board_rows()
                self.send_json_response(tasks)
            except Exception as e:
                self.send_json_error(500, f"Failed to load board: {e}")
            return

        # Pattern matches /tasks/<task_id> and /tasks/<task_id>/handoff-plan
        import re
        task_match = re.match(r'^/tasks/(task-\d+)$', path)
        if task_match:
            task_id = task_match.group(1)
            try:
                tasks = parse_board_rows()
                task = next((t for t in tasks if t["id"] == task_id), None)
                if not task:
                    self.send_json_error(404, f"Task '{task_id}' not found.")
                    return

                # Fetch plan and content for task detail response (Phase D)
                import agy_flow.config
                plan_file = agy_flow.config.TASKS_DIR / f"{task_id}.plan.json"
                task_file = agy_flow.config.TASKS_DIR / f"{task_id}.md"

                plan_data = {}
                if plan_file.exists():
                    try:
                        plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                content_data = ""
                if task_file.exists():
                    try:
                        content_data = task_file.read_text(encoding="utf-8")
                    except Exception:
                        pass

                task_detail = task.copy()
                task_detail["plan"] = plan_data
                task_detail["content"] = content_data

                self.send_json_response(task_detail)
            except Exception as e:
                self.send_json_error(500, f"Error getting task details: {e}")
            return

        handoff_match = re.match(r'^/tasks/(task-\d+)/handoff-plan$', path)
        if handoff_match:
            task_id = handoff_match.group(1)
            try:
                tasks = parse_board_rows()
                task = next((t for t in tasks if t["id"] == task_id), None)
                if not task:
                    self.send_json_error(404, f"Task '{task_id}' not found.")
                    return
                config = get_config()
                handoff_steps, route_plan = get_handoff_steps(task, config)
                active_agent = handoff_steps[0]["agent"] if handoff_steps else task["agent"]
                worktree_path = Path(task.get("worktree", ""))
                current_task_path = worktree_path / ".agents" / "current_task.json"
                if current_task_path.exists():
                    try:
                        task_meta = json.loads(current_task_path.read_text(encoding="utf-8"))
                        active_agent = task_meta.get("agent", active_agent)
                    except Exception:
                        pass
                next_step = find_next_handoff_step(handoff_steps, active_agent)
                self.send_json_response({
                    "task_id": task_id,
                    "active_agent": active_agent,
                    "handoff_steps": handoff_steps,
                    "next_step": next_step
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json_error(500, f"Error calculating handoff-plan: {e}")
            return

        self.send_json_error(404, "Route Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""

        if path == '/plan':
            try:
                params = json.loads(post_data) if post_data else {}
                title = params.get("title", "")
                if not title:
                    self.send_json_error(400, "Missing 'title' in request body.")
                    return
                config = get_config()
                route_plan = plan_task(title, agent_registry=get_agent_registry(config))
                self.send_json_response(route_plan)
            except Exception as e:
                self.send_json_error(400, f"Failed to plan task: {e}")
            return

        if path == '/tasks':
            try:
                params = json.loads(post_data) if post_data else {}
                title = params.get("title", "")
                agent = params.get("agent")
                desc = params.get("desc", "")
                if not title:
                    self.send_json_error(400, "Missing 'title' in request body.")
                    return

                class WebCreateArgs:
                    def __init__(self, title, agent, desc):
                        self.title = title
                        self.agent = agent
                        self.desc = desc

                args = WebCreateArgs(title, agent, desc)
                result = create_task(args)
                self.send_json_response(result, code=201)
            except Exception as e:
                self.send_json_error(400, f"Failed to create task: {e}")
            return

        import re
        start_match = re.match(r'^/tasks/(task-\d+)/start$', path)
        if start_match:
            task_id = start_match.group(1)
            try:
                class WebStartArgs:
                    def __init__(self, task_id):
                        self.task_id = task_id

                args = WebStartArgs(task_id)
                start_task(args)
                self.send_json_response({"status": "started", "task_id": task_id})
            except Exception as e:
                self.send_json_error(400, f"Failed to start task: {e}")
            return

        submit_match = re.match(r'^/tasks/(task-\d+)/submit$', path)
        if submit_match:
            task_id = submit_match.group(1)
            try:
                params = json.loads(post_data) if post_data else {}
                test_cmd = params.get("test_cmd", "")

                class WebSubmitArgs:
                    def __init__(self, task_id, test_cmd):
                        self.task_id = task_id
                        self.test_cmd = test_cmd

                args = WebSubmitArgs(task_id, test_cmd)
                submit_task(args)
                self.send_json_response({"status": "submitted", "task_id": task_id})
            except Exception as e:
                self.send_json_error(400, f"Failed to submit task: {e}")
            return

        if path == '/assign':
            try:
                params = json.loads(post_data) if post_data else {}
                agent = params.get("agent", "")
                task_id = params.get("task_id")
                if not agent:
                    self.send_json_error(400, "Missing 'agent' in request body.")
                    return

                import agy_flow.handoff
                current_task_path, metadata = agy_flow.handoff.assign_current_task_agent(agent, task_id)
                self.send_json_response(metadata)
            except Exception as e:
                self.send_json_error(400, f"Failed to assign task: {e}")
            return

        if path == '/ask/deepseek':
            try:
                import os
                params = json.loads(post_data) if post_data else {}
                prompt = params.get("prompt", "")
                mock = bool(params.get("mock", False))

                if not prompt:
                    self.send_json_error(400, "Missing 'prompt' in request body.")
                    return

                config = get_config()
                settings = get_llm_agent_settings("deepseek", config)
                api_key_env = settings.get("api_key_env", "DEEPSEEK_API_KEY")
                api_key_val = os.environ.get(api_key_env)

                if mock:
                    mock_response = "[Mock Answer] 这里是模拟的 DeepSeek 智能代码建议，请确保 API 密钥已正确设置以获取真实的 AI 服务。"
                    self.send_json_response({
                        "status": "success",
                        "response": mock_response,
                        "review_source": "mock"
                    })
                    return

                if not api_key_val:
                    self.send_json_response({
                        "status": "unavailable",
                        "error": "DeepSeek API key is not configured.",
                        "review_source": "unavailable"
                    }, code=400)
                    return

                response = call_openai_compatible_chat(
                    "deepseek",
                    prompt,
                    system_prompt=(
                        "You are a helpful coding assistant inside agy-flow. "
                        "Be concise and concrete."
                    )
                )
                if response is None:
                    self.send_json_error(500, "Failed to call DeepSeek API completions.")
                    return

                self.send_json_response({
                    "status": "success",
                    "response": response,
                    "review_source": "deepseek"
                })
            except Exception as e:
                self.send_json_error(400, f"Failed to query DeepSeek: {e}")
            return

        review_match = re.match(r'^/tasks/(task-\d+)/review$', path)
        if review_match:
            task_id = review_match.group(1)
            try:
                params = json.loads(post_data) if post_data else {}
                mock = bool(params.get("mock", False))

                review_text, source = review_task_service(
                    task_id,
                    agent="deepseek",
                    mock=mock
                )

                if source == "unavailable":
                    self.send_json_response({
                        "status": "missing_api_key",
                        "review": "Missing API Key. DeepSeek review is unavailable.",
                        "review_source": "unavailable"
                    }, code=400)
                    return

                self.send_json_response({
                    "status": "success",
                    "review": review_text,
                    "review_source": source
                })
            except Exception as e:
                self.send_json_error(400, f"Failed to perform task review: {e}")
            return

        self.send_json_error(404, "Endpoint not found.")

def serve_gateway(args):
    """Start local HTTP gateway server."""
    host = args.host
    port = args.port
    server = HTTPServer((host, port), AgyFlowHTTPHandler)
    print("=" * 60)
    print(f"🚀 agy-flow API Gateway listening on http://{host}:{port}")
    print(f"👉 Access dashboard visually at http://{host}:{port}/dashboard")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()
