# 导学案 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可运行的化学导学案应用，实现参考 UI、FastGPT 检索、结构化生成、Word 导出和连续版本修改。

**Architecture:** React/TypeScript 前端调用 FastAPI。SQLite 保存会话与任务，本地不可变目录保存版本；固定文档工具负责校验及装配，FastGPT 负责检索，兼容模型接口负责 JSON 内容生成。

**Tech Stack:** Python 3.11+、FastAPI、httpx、SQLite、pytest；React、TypeScript、Vite；用户包内 python-docx/lxml/jsonschema 工具。

**Spec:** `docs/superpowers/specs/2026-10-19-study-guide-agent-design.md`

## Global Constraints

- FastGPT 地址、API 密钥、知识库 ID 和模型直接写在服务端代码配置文件中，不使用环境变量，不提供配置页面。
- 首期只实现导学案，互动课件与限时练入口显示尚未开放，不模拟成功。
- 本期面向本机或受信任内网单教师使用，不实现账号体系、租户和公网部署。
- 来源默认 verified=false；检索文本、上传资料和模型输出均不可信。
- 无来源不得静默生成正式资料；用户显式接受后才能导出待核验草案。
- 结构校验最多两轮修复；所有版本不可覆盖，失败不得发布下载链接。
- 上传与产物通过服务端 ID 定位，密钥不得进入前端、响应或日志。

## Review Focus

- 浏览器刷新或服务重启：恢复持久任务状态，未完成任务明确标为中断（任务 1、4）。
- FastGPT 200 响应包含业务错误、空列表或异常字段：区分失败和零命中，不伪造资料（任务 2）。
- 扫描 PDF、超大资料、伪造扩展名：拒绝或明确提示，保留可操作错误（任务 3）。
- 并发修改旧版本：返回冲突，旧文件与最新版本均不被覆盖（任务 4）。
- 模型注入 HTML、路径和来源核验标记：前端不执行，服务端不接受自动升级来源（任务 2、4、5）。

## 文件职责

后端位于 `backend/app/`：`config.py` 代码配置，`models.py` 请求与响应契约，`store.py` SQLite，`retrieval.py` FastGPT，`model_client.py` 模型适配，`resources.py` 上传提取，`documents.py` 固定工具封装，`pipeline.py` 任务编排，`api.py` 路由，`main.py` 应用入口。后端测试位于 `backend/tests/`。

`vendor/chemistry/` 保留原包工具、schema、Word 模板和必要依赖；删除缓存，不修改原文件夹。`data/` 保存会话资源与版本，加入忽略规则。

前端位于 `frontend/src/`：`api.ts` 类型化客户端，`App.tsx` 页面状态，`components/Composer.tsx` 备课输入，`OptimizeDialog.tsx` 优化选项，`Conversation.tsx` 会话与进度，`OutlinePreview.tsx` 结构预览，`Resources.tsx` 来源及上传，`styles.css` 视觉样式。

### Task 1: 持久会话与应用基础

**Files:** `backend/requirements.txt`, `backend/app/{__init__,config,models,store,main}.py`, `backend/tests/test_store.py`, `.gitignore`

**Interfaces:** `Settings` 保存服务端代码常量；`Store(db_path: Path)` 提供 `create_session(payload: dict) -> dict`, `get_session(session_id: str) -> dict`, `list_sessions() -> list[dict]`, `create_job(session_id: str, payload: dict) -> dict`, `get_job(job_id: str) -> dict`, `recover_jobs() -> int`。API 与编排层共享这些类型。

- [ ] 写失败测试：`test_session_survives_reopen` 断言重开 SQLite 后会话参数完整；`test_recover_marks_running_interrupted` 断言运行任务转 failed 且包含中断原因；`test_one_active_job_per_session` 断言重复任务被拒绝。
- [ ] 运行 `python -m pytest backend/tests/test_store.py -q`，确认缺少实现导致失败。
- [ ] 实现参数契约、SQLite 建表及事务、未配置检测；配置默认空连接值和明确错误。初始化依赖与忽略规则，避免数据和真实密钥进入版本库。
- [ ] 重跑该测试，预期全部通过；`GET /api/health` 只返回就绪布尔值与缺失字段名。
- [ ] 若执行时初始化 Git，则提交本任务源码和测试；后续各任务同样按完成单元提交，不提交数据及凭据。

### Task 2: FastGPT 检索与模型 JSON 适配

**Files:** `backend/app/{retrieval,model_client}.py`, `backend/tests/{test_retrieval,test_model_client}.py`

**Interfaces:** `FastGPTRetriever(settings: Settings, transport=None).search(query: str) -> list[dict]` 返回真实切片及来源字段；`ModelClient(settings: Settings, transport=None).generate_json(messages: list[dict]) -> dict` 返回可解析 JSON 或脱敏异常。

- [ ] 写失败测试：混合召回请求使用 `/api/core/dataset/searchTest` 且携带配置 datasetId；保留 q/a、来源和分数；200+非成功业务码报错；空命中返回空列表；基础地址已含 `/api` 时不重复；非 JSON 模型结果拒绝；日志错误不包含密钥。
- [ ] 运行 `python -m pytest backend/tests/test_retrieval.py backend/tests/test_model_client.py -q` 确认失败。
- [ ] 对照官方 FastGPT 文档实现 httpx 适配、超时、错误检查、去重与上下文预算；模型通过兼容 chat completions 接口返回 JSON。资料作为独立上下文，系统指令明确禁止执行资料指令。
- [ ] 重跑适配测试，预期通过；所有 HTTP 使用 MockTransport，不声称已线上联调。

### Task 3: 固定文档引擎与上传资料

**Files:** `vendor/chemistry/`, `backend/app/{documents,resources}.py`, `backend/tests/{test_documents,test_resources}.py`

**Interfaces:** `DocumentEngine.validate(payload: dict) -> dict`, `render(payload: dict, destination: Path, version: str, allow_draft: bool) -> dict`, `revise(current: Path, patch: dict, destination: Path, version: str) -> dict`；`extract_resource(path: Path, original_name: str) -> dict` 返回提取文本与定位信息。

- [ ] 写失败测试：样例结构能校验；无核验来源且未接受草案时拒绝；接受草案后 DOCX 标题含待核验；教学表格空格与行列保留、笔记区25行；版本目录不能覆盖；TXT/MD/DOCX/PDF 提取正常，扫描 PDF 明确无文本；扩展名不符和大小超限拒绝。
- [ ] 运行 `python -m pytest backend/tests/test_documents.py backend/tests/test_resources.py -q` 确认缺少实现时失败。
- [ ] 复制必需原工具与模板，封装固定入口；上传限制为每文件20MB、每会话10份、单文件提取文本100000字符，超限提示教师缩减资料，不静默截断教学内容。
- [ ] 重跑测试；执行 `python -m unittest discover -s vendor/chemistry/tests -v`（复制相关原回归测试），记录实际结果。原包已有缺陷如影响本任务，先定位并保留回归证据再做项目内修复。

### Task 4: 生成、来源核对、修改与 API

**Files:** `backend/app/{pipeline,api}.py`, 扩展 `models.py`, `store.py`, `main.py`, `backend/tests/{test_pipeline,test_api}.py`

**Interfaces:** `Pipeline.start_generation(session_id: str, request: dict) -> dict`, `start_revision(session_id: str, request: dict) -> dict`, `run(job_id: str) -> None`。版本记录包含 `id`, `number`, `parent_id`, `content_sha256`, `content`, `report`；任务包括 `id`, `status`, `stages`, `error`, `version_id`。

- [ ] 写失败测试：模拟检索→模型→校验→Word→版本发布成功；无配置/无命中/来源不足提供正确错误；非法 JSON/结构最多两轮修复；模型 verified=true 被丢弃；用户核对记录必须对应实际来源 ID；失败不发布版本。
- [ ] 补充失败测试：按真实哈希局部修改仅改变指定块，结构修改记录父版本；旧基线409；并发提交冲突；路径穿越404；刷新读到已持久化阶段；重启标记任务中断。
- [ ] 运行 `python -m pytest backend/tests/test_pipeline.py backend/tests/test_api.py -q` 确认失败。
- [ ] 实现固定阶段编排、后台线程、事务版本发布、来源快照及核对记录；将输出 schema 与错误路径反馈给模型，不执行模型脚本。
- [ ] 实现 `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/resources`, `/api/sessions/{id}/sources/{source_id}/review`, `/api/sessions/{id}/generate`, `/api/sessions/{id}/revise`, `/api/jobs/{id}`, `/api/sessions/{id}/versions/{version_id}`, `/api/sessions/{id}/versions/{version_id}/files/{kind}`；请求和响应使用显式模型，文件 kind 使用允许列表。
- [ ] 重跑所有后端测试，预期通过；用临时目录完成真实 DOCX 文件的模拟模型端到端流程，不替换文档生成器。

### Task 5: 三张参考图与完整前端交互

**Files:** `frontend/{package.json,index.html,vite.config.ts,tsconfig.json}`, `frontend/src/{main.tsx,App.tsx,api.ts,styles.css}`, `frontend/src/components/{Composer,OptimizeDialog,Conversation,OutlinePreview,Resources}.tsx`

**Interfaces:** `api.ts` 与任务4接口一致；`Composer` 提交章节课时及选项；`OptimizeDialog` 接收当前值并仅在填入时提交；`Conversation` 根据 job 状态更新，`OutlinePreview` 接收标准 outline 并以 React 元素渲染。

- [ ] 搭建 Vite React TypeScript 前端与 `/api` 开发代理；还原白底蓝色、顶部产物切换、大输入区和模态框布局，采用原生 SVG 图标与 CSS，不额外生成位图。
- [ ] 实现首页参数、自定义章节课时、历史会话、上传与来源查看、优化选择与清空/取消/填入；默认项与自定义输入互斥校验。
- [ ] 实现真实任务轮询、阶段显示、异常重试、预览、草案选择、来源核对、版本下载和快捷修改。关闭页面取消轮询，后台任务继续持久运行，重新进入恢复状态。
- [ ] 化学 runs 用受控上下标元素渲染；表格保留空单元格，不使用 `dangerouslySetInnerHTML`；模型含 `<script>` 的段落只能显示文本。
- [ ] 执行 `npm --prefix frontend run build`，预期类型检查及构建通过。
- [ ] 浏览器验证三张设计对应页面，以及窄屏、模态框滚动、取消不保存、生成禁重入、刷新恢复、错误状态、草案确认、版本切换与下载；若接口未连接，真实显示未配置，不做假进度。

### Task 6: 启动交付与整体验证

**Files:** `README.md`, `backend/app/main.py` 静态产物服务, `scripts/dev.sh`, `scripts/check.sh`, `docs/verification.md`

**Interfaces:** 文档给出 Python 虚拟环境、依赖安装、服务端代码参数位置、前端开发与生产启动命令；默认本地监听127.0.0.1。

- [ ] 编写启动脚本和 README，区分 FastGPT 检索凭据与模型凭据，说明如何直接编辑服务端代码常量；说明上传限制、Word 视觉复核和单用户范围。
- [ ] 构建产物存在时由 FastAPI 提供前端；缺失时 `/api` 仍正常且首页提示构建方法，不把 API 错误降级为 HTML。
- [ ] 执行后端全量测试、原工具相关回归测试、前端生产构建；通过浏览器跑一遍可控服务的生成与修改，验证下载 DOCX 可解析。
- [ ] 如提供真实连接值，运行实际 FastGPT 教材召回与模型生成；尚未提供则在验证报告明确线上联调未执行，保留可运行测试结果。
- [ ] 执行可用文档渲染检查，记录有无字体及 Office 支持；无可用渲染则标记“仅通过结构检查，视觉效果待核验”，不声称已可印刷。
- [ ] 完成整体代码审查，修复影响需求的问题；提供源码位置、启动方式、测试结果和实际剩余限制。

## 执行方式

建议由当前会话直接逐任务实现，所有任务共享配置、来源和版本协议，连续执行便于保持一致。也可选择子代理逐任务实施和独立审查；该方式增加上下文和审核成本。实施开始前由用户审阅此计划并选择执行方式。
