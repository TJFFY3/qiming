# 限时练习 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 独立实现限时练习输入、优化、生成、修订和学生卷/答案卷下载。
**Architecture:** 前后端独立 timed-practice 模块，独立数据库与文件目录；顶层只装配入口。共用无状态检索、资源提取与化学排版基础工具。
**Tech Stack:** React/TypeScript、FastAPI、SQLite、python-docx。
**Spec:** docs/superpowers/specs/2026-10-20-timed-practice-agent-design.md

## Global Constraints
- 不依赖导学案 Store/Pipeline/Options/outline；不覆盖工作区已有修改。
- API `/api/timed-practice`；独立 `data/timed-practice/`；独立浏览器持久化键。
- 默认35分钟、100分；题量默认14道单选+II卷44分+2道选做；明确教师自定义优先。
- 两份Word，沿用限时练模板与化学排版，不修改vendor固定校验器。

## Review Focus
- 课时草稿切换、任务运行时切换Agent及刷新恢复。
- 题型/分值/时间自定义与正文覆盖设置冲突。
- 只用原题的资料匹配，未知来源ID及模型伪造核验标记。
- 失败重试与历史基线，缺口报告不能冒充成功文件。
- 上传/下载的会话归属与资源修改并发。

### Task 1: 独立后端业务与Word
**Files:** `backend/app/timed_practice/{models,requirements,documents,store,model_client,pipeline}.py`、`backend/tests/test_timed_practice.py`
**Interfaces:** `PracticeStore(path)`；`PracticePipeline(settings,store,retriever,model)`；`render(content,sources,directory,draft)`。
- [x] 写并运行失败测试：5题+2题的50分20分钟、分值不齐、无效来源、非法run/路径、独立Word、事务串行和恢复。
- [x] 实现结构、要求解析、来源约束、独立存储、模型包装、校验修复和不可变版本。
- [x] 运行该测试文件，确认通过。

### Task 2: API装配
**Files:** `backend/app/timed_practice/api.py`、`backend/app/main.py`。
**Interfaces:** `make_router(settings,pipeline_factory=None)` 返回router/store；create_app新增可选 practice_factory。
- [x] 写并运行失败接口测试：跨Agent ID拒绝、上传删除、缺口/草案选择、实际下载、修订冲突、重启恢复。
- [x] 实现独立路由、资料库缓存和安全序列化；只在main中注册。
- [x] 测试接口全链路实际生成两份Word。

### Task 3: 独立前端
**Files:** `frontend/src/agents/timed-practice/*`、顶层App入口最少修改。
**Interfaces:** `TimedPracticeApp({onAgentChange})`，业务不导入导学案类型和组件。
- [x] 写并运行失败测试：默认/自定义优化、取消清空、多选互斥、重复填入、切换隔离及独立API调用。
- [x] 实现首页、弹窗、资料、历史、轮询、预览、下载、继续修改；作用域CSS和独立存储。
- [x] 运行前端测试与生产构建。

### Task 4: 验证与文档
**Files:** README、docs/verification.md（追加，不覆盖）。
- [x] 后端与vendor回归、前端全测、构建；浏览器核对首页弹窗、窄屏与结果页。
- [x] 进行独立代码审阅，修复重要问题并验证。
- [x] 记录通过项目及真实模型/Word视觉未验证的边界，交付本地源码。
