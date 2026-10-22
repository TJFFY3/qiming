# 启鸣 AI · 教学 Agent 工作台

React + FastAPI 本地应用。导学案支持知识库检索、原生 Word 导出、对话局部修改与版本管理；互动课件支持独立备课设置、逐页预览、演示、可编辑 PPTX 导出和按页修订；限时练习支持独立优化设置、试题与答案预览、两份 Word 导出及连续修改。各 Agent 的业务状态、接口、存储和提示词分别管理。

代码阅读入口：[三个 Agent 的文件职责、分类与调用链](docs/agent-code-map.md)。后端关键模块使用中文职责标签，区分模型调用、知识库调用、规则处理、文档工具和状态存储。

## 启动

需要 Python 3.11+ 和 Node.js 22.12+。本机默认 `python3` 是3.9，开发验证使用 `python3.12`。

```sh
cd /Users/sealos/Desktop/qiming
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp backend/app/config.example.py backend/app/config.py  # 仅首次；不要覆盖已经填写的配置
npm --prefix frontend ci
npm --prefix frontend run build
./scripts/dev.sh
```

打开 http://127.0.0.1:8010 。只监听本机地址，不修改现有8000端口服务。

开发前端时，在第二个终端执行 `npm --prefix frontend run dev`，打开5173端口；后端仍用8010。前端修改后重新构建即可更新正式界面，后端配置修改后需重启服务。

## 直接通过代码配置

编辑 `backend/app/config.py` 末尾的 `settings = Settings(...)` 代码参数，不使用环境变量，没有单独的配置页面。`config.py` 已被 Git 忽略，仓库只保存无凭据的 `config.example.py`。

```python
settings = Settings(
    fastgpt_url='https://你的FastGPT域名/api',
    fastgpt_key='真实API密钥',
    datasets=[
        {'id': '知识库或文件夹ID', 'type': 'folder', 'category': 'reference', 'name': '教学资料'},
        # 独立教材库：{'id': '教材知识库ID', 'type': 'dataset', 'category': 'textbook', 'name': '教材'}
    ],
    model_provider='fastgpt',
    fastgpt_app_id='实际应用ID',
)
```

FastGPT 检索调用官方 `/api/core/dataset/searchTest`。知识库密钥必须具有相应权限，不能假定应用对话密钥拥有知识库权限。当前已接入用户提供的 FastGPT 应用，以 `appId` 调用 `/api/v1/chat/completions`，模型由工作流控制，完整结构要求作为任务输入传入。也可将 `model_provider` 改为 `openai`，填写 `model_url`、`model_key` 和 `model`，调用兼容接口（需支持 `response_format=json_object`）。凭据只在服务端使用。

可在代码中调整 `search_mode`（默认 mixedRecall）、`search_limit`（6000 tokens）、`similarity`（0.2）、`using_rerank`（默认 false）和 `timeout`（120秒）。`data_dir` 默认为项目下 `data/`。

导学案生成与修订使用流式模型请求，独立设置 `model_read_timeout`（默认连续300秒无数据）和 `model_total_timeout`（默认单次调用600秒）；不再继承检索请求的120秒超时。可在 `backend/app/config.py` 的 `Settings(...)` 中覆盖这两个值，重启后端生效。服务返回普通JSON时仍兼容接收；超时、断流和工作流错误直接报告，不作为内容格式错误自动重试。

## 使用流程

1. 选择或输入章节、课时，设置教材和年级，在优化提示中选择范围、用时、任务数量、难度、提示详略、重点和补充要求。
2. 可上传 TXT、MD、DOCX、文字 PDF（每文件20MB、每会话10份、提取文本每文件100000字符、PDF最多300页）。扫描 PDF 需先 OCR；上传资料只属于会话，不自动写入 FastGPT。拖拽和按钮上传均支持。
3. 提交后从真实 FastGPT 检索。在导学案对话页点击“本课引用来源”查看摘录与来源位置。资料库及引用来源界面不显示核验标识或核对操作；资料缺口与冲突作为资料说明展示。检索无命中不会自动拿格式样例充当教材。
4. Word 使用原包模板、原生可编辑表格、化学上下标/离子域和25行笔记区。标题、正文与下载文件名不附加核验状态标记。预览只展示部分笔记横线，完整区保留在 Word。
5. 继续对话进行修改。普通修改使用稳定块 ID 和哈希保护的局部补丁；改标题、目标或章节结构使用完整结构修订。每次产生独立版本，历史版本可查看和下载；只允许基于最新版本提交修改。
6. 来源快照不随后续资料操作回写。资料核验不阻止生成或下载；来源、化学内容和 Word/WPS 视觉可由教师结合原资料检查。

知识库条目的 `type=folder` 会读取子库；目录和搜索响应均兼容 `data.list` 格式。混合模板和样例的文件夹使用 `category=reference`，不会冒充教材来源。

未配置 FastGPT 时，如有上传原文，可走本地参考资料生成；生成模型仍需配置。已配置 FastGPT 的检索错误不会被上传文件静默掩盖。

## 结构

- `backend/app/study_guide/`、`courseware/`、`timed_practice/`：三个 Agent，内部按 `api/`、`application/`、`llm/`、`domain/`、`knowledge/`、`tools/`、`storage/` 等职责分目录。
- `backend/app/shared/`：共享知识库、化学规则、课时提示和文件工具；`paths.py` 统一定位模板资源。
- `frontend/src/agents/`：三个独立 Agent，内部按 `pages/`、`components/`、`services/`、`domain/`、`styles/` 与 `__tests__/` 归类；共用界面组件在 `frontend/src/components/`。
- `vendor/chemistry/`：用户能力包的工具、schema、模板和原回归测试，原下载文件夹未改动。
- `data/`：SQLite、上传资料和不可变版本（Git 忽略）。
- `docs/superpowers/`：已确认的设计及实施计划。

原包只有 `chemistry_runs` 的 CPython 缓存而缺源码，项目补齐源码，使用原测试验证。详见 `vendor/chemistry/PORTING.md`；不依赖该缓存运行。

## 验证

```sh
./scripts/check.sh
```

后端测试包含 HTTP 适配、来源核对/缺口、真实 DOCX 生成与按块修改、旧版本冲突、下载、上传、重启恢复等。集成测试只替换远程 HTTP 服务，实际执行 schema 校验和 Word 生成。已通过真实 FastGPT 检索、应用生成和连续修改联调；模拟回归与真实联调分别记录，详见 `docs/verification.md`。

本系统不自动认证化学答案、教学难度或教材页码。Word EQ 域、表格分页及字体替换需在 Word/WPS 检查；结构检查通过不等于可直接印刷。

## 主要 API

交互式接口文档：http://127.0.0.1:8010/docs

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 就绪状态（不返回凭据） |
| `GET/POST /api/sessions` | 历史会话 / 新建 |
| `GET/PATCH /api/sessions/{id}` | 恢复会话 / 修改设置 |
| `GET/POST /api/sessions/{id}/resources` | 资料列表 / 上传 |
| `POST /api/sessions/{id}/sources/{source_id}/review` | 记录来源核对 |
| `POST /api/sessions/{id}/generate` | 提交生成，返回任务 ID |
| `POST /api/sessions/{id}/revise` | 基于最新版本提交修改 |
| `GET /api/jobs/{id}` | 持久阶段及结果，前端轮询 |
| `GET /api/sessions/{id}/versions/{version_id}` | 版本内容及报告 |
| `GET /api/sessions/{id}/versions/{version_id}/files/{kind}` | Word / 内容 JSON / 报告下载 |

面向本机或受信任内网单教师，不含登录与租户隔离；不直接作为多用户公网服务发布。服务重启时未完成任务标记中断，可重试，不自动重复调用收费模型。

### 资料库与生成来源

资料库通过 FastGPT 目录和片段列表接口，分页同步配置范围内的全部文件与全部已解析片段，支持嵌套文件夹。首次打开自动同步；后续点击“同步知识库”更新本地缓存。按文件名或知识库名筛选，展开文件后逐段查看，超过 20 个片段可继续显示。PPT/PPTX 与其他文件一并展示，可下载原文件，片段中的 Markdown 图片直接显示。内容以 FastGPT 实际解析结果为准，未解析出的公式或图片请查看原文件。

生成导学案仍调用语义检索接口，仅将本次命中片段与本课上传资料作为来源；全量缓存不注入模型。导学案对话页可查看本课引用来源，历史版本的“查看来源”保留生成时的不可变快照。全量同步失败会保留上一次完整缓存。

“本课上传资料”卡片支持删除，删除后会从本课后续生成的参考资料中移除，已生成版本的来源快照保留。正在生成时暂不可删除。

“优化提示 → 填入”会将七项配置写入可编辑的中文提示词，并在提交后保留于对话记录。重复填入更新已有配置段；教师可以直接编辑提示词。模型收到的提示词包含同一份要求，任务同时保存提交时的课时设置快照。

生成时会保守补齐可确定的空表头；无法推断时只请求模型修复目标表头，保留表格数据和已有内容。修复仍需通过完整文档校验，失败时可展开查看技术详情。

导学案方程式校验失败时，会收集出错原文、精确位置、所在表格、教学要求和相关资料，交给模型修复整个反应。允许补齐或纠正反应物、生成物、系数、条件及气体沉淀标记，也支持逐行书写多步反应；服务端分别复算每一步的原子数和离子电荷。转化题中仅供学生判断的物质转化关系不会被误作完整反应式。模型只替换指定方程式字段，保持其他正文、表格与学生作答空白。生成及全部内容修复共用“初次调用＋最多两轮修复”预算，不无限重试，也不允许以删题、恒等式或无关反应绕过校验。原文及校验细节保存到任务的 diagnostics 目录。

知识库图片在发布前完整解码并检查 8 MiB、4000 万像素限制。有效但缺少 JFIF/Exif 文件头、导致 Word 解析器不识别的 JPEG，会无损转换成 PNG；预览与 Word 共用转换后的本地图片快照。损坏、无法解码和超限图片仍会明确报错。


导学案现支持检索原图：从本课来源的 Markdown 图片提取原图目录，模型用 `image_id` 在对应学习任务中插入图片块，网页预览与 Word 使用同一份版本图片快照。原图在后台下载、校验并缓存；支持 FastGPT 到官方文件 CDN 的受限跳转，不向图片请求发送 API 密钥。图片不存在或下载失败会明确报错，不再用“图片展示”构图文字冒充原图；已有版本的图片不依赖后续网络访问。

## 独立限时练习 Agent

打开 http://127.0.0.1:8010/#practice ，或点击首页“限时练习”。首页和优化弹窗按提供的两张设计图实现，支持用时、满分、题型数量、难度、出题方式、重点多选和补充要求；“填入”更新可编辑提示词，取消不生效、清空仅重置弹窗草稿。默认沿用本限时练习会话已有用时/满分，没有时为35分钟、100分。明确题量、分值和用时优先；无自定义时沿用技能包14道单选＋II卷44分＋2道选做的默认结构。

限时练习前端在 `frontend/src/agents/timed-practice/`，后端在 `backend/app/timed_practice/`，API前缀 `/api/timed-practice`，数据库及上传/版本保存在 `data/timed-practice/`。使用独立浏览器会话/草稿键，不调用导学案Store、Pipeline、Options或outline工具。不同Agent往返切换保留各自草稿和任务；只有顶层入口负责切换和装配，共用知识库连接、文字提取、模态框和化学排版等基础能力。

学生卷与独立答案解析卷分别提供Word下载，使用技能包限时练模板、原生可编辑正文、动态答题卡、作答横线和化学上下标/EQ域。支持独立资料库同步、本课上传与删除、来源核对记录、历史会话、刷新恢复、连续修改和不可变历史版本。新上传资料及当前核对记录可参与下一次修订，历史来源快照保留；后续修改继续约束原有题型数量和出题方式，除非教师明确改变。

限时练习直接生成，不要求先核对来源或补齐来源类别，也不需要额外选择草案模式。资料缺口仅作为说明；只用原题时仍检查题干和选项能否在实际引用中定位。当前文字资料流程不生成依赖缺失图片的残缺题。

限时练习默认沿用公共模型连接，但有独立任务包装和提示词。若现有FastGPT应用固定输出导学案，应配置独立限时练习应用或支持JSON输出的兼容模型。在实际 `backend/app/config.py` 的 `settings = Settings(...)` 之后可添加：

```python
settings.timed_practice = {
    'model_provider': 'fastgpt',
    'fastgpt_app_id': '实际限时练习应用ID',
    'model_read_timeout': 300,  # 连续无数据的等待上限（秒）
    'model_total_timeout': 600,  # 单次模型调用的总预算（秒）
    # 可独立覆盖fastgpt_url/fastgpt_key/datasets，或model_url/model_key/model。
}
```

限时练习使用流式模型调用，任务记录接收字数与耗时；不继承公共请求的120秒等待限制。只向模型发送优先匹配当前章节/课时的资料片段，排除格式模板，原文上下文不超过12000字符；完整来源快照仍保存。网络错误不自动重复调用，内容格式错误才进行有限修复。

不得把实际密钥写进版本库。修改后重启后端。Word结构校验不等于分页、字体与EQ域视觉验收；请在Word/WPS中复核。

## 独立互动课件 Agent

点击首页“互动课件”，或访问 `/#courseware`。按参考图实现章节/课时选择、传统 PPT、资料库/上传、历史及优化提示弹窗。弹窗包括教学内容、课堂时长、课件页数、课堂练习、上课方式、重点多选和补充要求；“填入”更新可编辑提示词，取消不应用，清空只作用于弹窗草稿。

直接提交即可生成，无需额外勾选草案模式；课件、封面和下载文件名不添加核验标记。结果支持逐页预览、教师备注/答案、键盘翻页演示、版本切换和 PPTX/检查报告下载。预览展示内容结构，实际母版排版以下载 PPTX 为准。

课件使用 `vendor/chemistry/scripts/ppt_tools.py` 和原课件模板，保留母版背景、教学环节角标和化学语义 run；正文≥24pt、标题≥32pt，不通过缩字强行容纳内容。结构或版式问题最多请求模型修复两轮；固定页数冲突明确报告。局部修订使用页补丁合并，未涉及页面由服务端保留；在结果页选择“调整页数与结构”后允许整体修订，默认局部修改不会增删其他页。历史版本不覆盖。

- 前端：`frontend/src/agents/courseware/`，仅复用无业务状态的 Modal/图标等基础组件。
- 后端：`backend/app/courseware/`，独立模型、提示词、任务编排、存储和导出适配器，不调用导学案生成/修订链路。
- API：`/api/courseware/{health,sessions,jobs,library}`；会话下 `generate`、`revise`、`resources`、`versions/{id}/files/{pptx,content,report}`。
- 数据：`data/courseware/agent.sqlite`、`data/courseware/{session}/`；浏览器键为 `qiming-courseware-session`、`qiming-courseware-draft`。
- 资料：当前上传与知识库结果形成版本来源快照；修订继承原来源。长资料对模型使用均衡节选，报告明确说明，完整引用快照不因此截断；删除上传不改写历史版本。

默认沿用服务端连接参数，课件请求和提示词独立。若需课件专用 FastGPT 应用或模型，复制 `backend/app/courseware_config.example.py` 为 `backend/app/courseware_config.py` 后填写 `overrides`，重启后端生效；凭据文件已被 Git 忽略。无需新增 PPT 生成依赖。

课件模型使用流式响应接收，默认允许连续 300 秒无数据等待、单次生成最多 600 秒，避免长课件生成继承公共 120 秒超时。可在 `courseware_config.py` 中用 `model_read_timeout` 和 `model_total_timeout` 独立覆盖；流式连接中断、输出截断或超预算会明确失败，不会发布不完整课件。

## 核验状态展示策略（2026-10-20更新）

按用户要求，所有Agent取消核验相关标识和发布门槛。核验状态不阻止生成、继续修改或下载；旧版allow_draft字段仅兼容接收，不再控制发布。历史成果预览及下载也去除状态标记，Office下载生成去标记副本，保留原始历史文件及来源记录。来源未被自动设为已核验；内容结构、原题真实性、文件大小与并发保护等正常校验保留。
