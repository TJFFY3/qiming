# 三个 Agent 的新 FastGPT 工作流接入

三个 Agent 的默认生成链路统一调用应用 `6ae34b10b1b18f9bb876d8ac`。应用装配入口不再创建本地内容检索器，也不根据旧 `model_provider` 切换模型接口。

```text
教师要求／优化设置／上传资料／修订基线
  → 本地组装工作流变量
  → FastGPT 工作流：检索 + 生成
  → 本地读取内容 JSON 和响应引用元数据
  → 内容、题源、化学和修订范围校验
  → Word／PPTX 导出及独立版本保存
```

## 全局变量

变量名严格匹配工作流，包括 `Promot` 的原始拼写。

| 变量 | 请求中的类型 | 内容 |
| --- | --- | --- |
| `datasetIds` | 数组 | 选择器对象数组，例如 `[{"datasetId":"知识库ID"}]`；文件夹先展开，不本地检索正文 |
| `chapters` | 字符串 | 章节数组的 JSON，例如 `["钠及其化合物"]` |
| `repoLabelConfig` | 字符串 | 标签过滤对象的 JSON，默认 `{}` |
| `subject` | 字符串 | 当前选择的学科，旧会话默认 `化学` |
| `repoSearchInfo` | 字符串 | 知识库检索文本：本课教材、年级、章节、课时与教师要求中的教学内容／知识点；不包含 Schema、来源全文、历史成品或修复反馈 |
| `dynamicPromot` | 字符串 | 所选学科的动态提示词；化学传“化学表达”七条要求，其他学科尚未配置时传空字符串 |
| `agentCategory` | 字符串 | `导学案`、`互动课件`、`限时练习` |
| `basePromot` | 字符串 | 本次系统协议，包括生成／修订／定点修复的格式约束；Schema 也随任务消息传入 |
| `operation` | 字符串 | 首次生成 `初始化`；修订 `微调`。自动内容修复保留原任务操作，并传递修复协议 |

每次请求都发送完整变量；`messages` 的本次用户问题同时携带输出协议和最新修复反馈，兼容直接引用用户问题的工作流节点。不会依赖模型自动猜测本地字段，也不会静默重命名不合规的结果。

不使用 FastGPT `chatId` 自动历史，避免不同 Agent、会话和修复请求串用上下文。

## 请求与返回

调用 `/api/v1/chat/completions`，请求使用 `stream=true`、`detail=true` 和顶层 `variables`。模型由工作流节点配置控制。动态知识库输入已通过真实调用确认需要对象数组；直接传字符串数组会导致 `unExistDataset`。

回答正文保持既有结构：导学案的大纲／补丁、互动课件 Deck／页面补丁、限时练习完整试卷，不增加外层返回包装。

来源独立读取官方响应元数据：

- 普通 JSON 响应：`responseData` 中的 `quoteList`。
- SSE 响应：`event: flowResponses` 中的 `quoteList`，即使它晚于 `[DONE]` 也继续收集。
- 正文事件只接受 `answer`、`fastAnswer` 或兼容的无名事件；不混入节点状态和推理。
- 来源 ID 保留工作流切片 `id`，供练习 `source_ids` 定位；引用默认未核验。
- 不将模型正文里的 `sources` 或 `verified` 当作真实检索结果。

工作流需要让检索引用进入响应详情。若仅返回成品而不暴露引用，应用不会伪造来源；原题定位和图片来源检查可能因缺少证据而失败。已有图片 ID 继续有效。工作流新检索图片使用 `切片ID:image:序号`，序号按该切片原图 URL 去重后的首次出现顺序从1起计；本地仅依据可信引用中的原图转换为现有哈希ID。未知别名继续拒绝，不凭模型声明跳过图片校验。

网络故障、权限错误、工作流执行错误、超时和断流直接失败；完整响应的 JSON／内容错误才进入既有两轮修复。流式空增量允许 `content: null`，不会把它拼入正文。

知识库返回 `{"errorInfo":"其他学科即将开放，敬请期待。"}` 等非空错误说明时，三个 Agent 直接将该说明保存为任务失败原因，不触发内容自动修复，也不发布新版本。普通 JSON、流式正文及响应节点元数据均支持此错误结构；来源摘录中的示例文本不作为工作流错误执行。

## 配置

沿用实际 `backend/app/config.py` 中的 `fastgpt_url`、`fastgpt_key`、`datasets` 和超时参数。真实配置无需覆盖或复制。

新参数已声明在 `config.example.py`。旧配置类尚无这些字段时，可在 `settings = Settings(...)` 之后赋值：

```python
settings.workflow_app_id = "6ae34b10b1b18f9bb876d8ac"
settings.repo_label_config = {}  # 按需填写 tags 等过滤条件
```

不设置时，工作流 ID 使用上述新应用，标签过滤为空对象。旧 `fastgpt_app_id`、`model_provider`、`model_url` 等参数不决定默认生成链路。课件和练习的配置适配器也支持 `workflow_app_id`、`repo_label_config`。

文件夹目录展开需要目录读取权限；工作流调用密钥需要新应用权限。独立“资料库浏览与同步”仍使用原有目录 API，不参与生成前的正文检索。

## 代码入口

- `backend/app/shared/workflow/client.py`：变量、工作流 HTTP/SSE、响应 JSON 与引用元数据。
- `backend/app/shared/workflow/retrieval_query.py`：`repoSearchInfo` 的检索内容提取规则。
- `backend/app/shared/workflow/subject_prompts.py`：`dynamicPromot` 的学科提示词配置。
- `backend/app/shared/workflow/datasets.py`：知识库文件夹目录展开。
- `backend/app/shared/workflow/binding.py`：将单次任务绑定到工作流调用，合并引用并适配原有内容错误类型。
- `backend/app/main.py`、练习 `api/routes.py`：默认装配新工作流客户端。
- 三个 `application/pipeline.py`：保留各自的校验、修订和文档导出。

历史 `llm/client.py` 和检索适配器只供显式注入的旧测试／独立工具使用；默认应用不装配这些旧生成客户端。此兼容接口不会在新工作流失败时自动回退到旧服务。

接口依据：[FastGPT 官方对话接口](https://doc.fastgpt.io/en/openapi/chat)。

## 验证记录

- 新增25项协议与集成测试，覆盖8个变量、三套生成／修订、可信引用、原图Word导出、空增量、迟到元数据、错误分类及目录总预算。
- 后端391项、前端110项、文档工具83项通过，前端生产构建成功。
- 真实接口已确认三个分类能返回JSON并附带知识库引用；`datasetIds`对象数组是该工作流的实际入参形式。

真实端到端验收（临时数据目录，不写入正式历史）：

| Agent | 结果 | 来源数 | 导出 |
| --- | --- | --- | --- |
| 导学案 | completed | 8 | Word |
| 互动课件 | completed | 7 | PPTX |
| 限时练习 | completed | 6 | 学生卷 Word + 答案卷 Word |

真实验收覆盖初始化生成、现有Schema校验、可信引用保存和文档结构检查。修订及原图别名的完整链路通过MockTransport集成测试验证；本次未做Word/WPS/PowerPoint人工视觉验收。正式服务已在无活动任务时重启，三个健康接口均返回ready=true。

`repoSearchInfo` 由共享检索规则提炼，三个 Agent 共用，提取规则沿用原实现，不额外调用模型。`dynamicPromot` 从共享学科配置按 `subject` 读取，与检索词独立，初始化、修订和自动内容修复均传递。完整教师要求、输出协议、有效练习要求、上传证据、修订基线和修复反馈继续通过 `messages` 传给生成节点；`basePromot` 仍传系统规则。

工作流全局变量需声明 `repoSearchInfo`（字符串），知识库检索节点的检索内容改为引用 `repoSearchInfo`；生成节点引用 `dynamicPromot` 作为学科表达要求。`dynamicPromot` 不再用于检索输入。

学科路由：三个 Agent 会话设置包含 `subject`（旧会话默认化学）。服务端保留目录中的学科文件夹标签，解析为真实知识库 ID 后，仅把所选学科下的知识库传给 `datasetIds`，同时传递 `subject`。未找到匹配学科时失败，不扩大到其他学科。无学科标签的旧配置仅兼容默认化学。知识库界面按学科、知识库、文件分组；更换学科会开启新任务。

章节选项：已同步时，`/api/library/chapters` 从与右侧资料浏览相同的目录快照提取章节；尚无快照时才读取远端文件标题。前端不预设固定章节，目录未确认或读取失败时禁止新建生成，失败可重试。知识库同步完成后，三个 Agent 自动刷新章节；历史成品及其修订上下文保持原课题。

三个 Agent 的新建会话和设置更新接口均要求显式传入非空 `chapter`。后端不再提供固定化学章节默认值；缺失时返回 HTTP 422，不自动选择课题或把旧示例写入本次任务。
