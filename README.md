# 启鸣 AI · 化学导学案 Agent

React + FastAPI 本地应用，实现备课输入、优化提示、FastGPT 知识库检索、结构化教学内容生成、原生 Word 导出、对话局部修改与版本管理。界面依据三张用户设计图。互动课件与限时练为后续功能，当前不生成这些产物。

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

## 使用流程

1. 选择或输入章节、课时，设置教材和年级，在优化提示中选择范围、用时、任务数量、难度、提示详略、重点和补充要求。
2. 可上传 TXT、MD、DOCX、文字 PDF（每文件20MB、每会话10份、提取文本每文件100000字符、PDF最多300页）。扫描 PDF 需先 OCR；上传资料只属于会话，不自动写入 FastGPT。拖拽和按钮上传均支持。
3. 提交后从真实 FastGPT 检索。资料命中默认待核对；在导学案对话页点击“核对本课命中片段”查看摘录并记录核对结论。首次未核对时会保留来源并返回提示，可核对后重试，或显式选择“允许生成待核验草案”。检索无命中不会自动拿格式样例充当教材。
4. Word 使用原包模板、原生可编辑表格、化学上下标/离子域和25行笔记区。草案标题与下载文件名标记待核验。预览只展示部分笔记横线，完整区保留在 Word。
5. 继续对话进行修改。普通修改使用稳定块 ID 和哈希保护的局部补丁；改标题、目标或章节结构使用完整结构修订。每次产生独立版本，历史版本可查看和下载；只允许基于最新版本提交修改。
6. 来源核对不会回写已保存版本。正式生成要求至少一份核对过的教材/教师用书且无未解决缺口或冲突；来源、化学内容和 Word/WPS 视觉仍需教师复核。

知识库条目的 `type=folder` 会读取子库；目录和搜索响应均兼容 `data.list` 格式。混合模板和样例的文件夹使用 `category=reference`，不会冒充教材来源。

未配置 FastGPT 时，如有上传原文，可走本地参考资料生成；生成模型仍需配置。已配置 FastGPT 的检索错误不会被上传文件静默掩盖。

## 结构

- `backend/app/`：API、SQLite 存储、检索/模型适配、任务编排、文件提取、固定文档工具封装。
- `frontend/src/`：三张参考界面的 React 实现，结构化预览和来源核对。
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

生成导学案仍调用语义检索接口，仅将本次命中片段与本课上传资料作为来源；全量缓存不注入模型。来源核对在导学案对话页进行，历史版本的“查看来源”保留生成时的不可变快照。全量同步失败会保留上一次完整缓存。
