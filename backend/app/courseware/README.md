# 互动课件 Agent 后端目录

按功能定位文件；包初始化文件不装配业务依赖。

| 目录 | 职责 |
| --- | --- |
| `api/` | HTTP 接口与响应 |
| `application/` | 生成／修订流程编排 |
| `configuration/` | Agent 专属配置适配 |
| `domain/` | 数据合同、业务规则、化学处理与修订保护 |
| `knowledge/` | 资料上下文节选与预算规则 |
| `llm/` | 模型请求、流式响应与提示词 |
| `storage/` | 会话、任务与版本存储 |
| `tools/` | Word／PPTX、原图与下载工具 |

阅读入口：`api/routes.py` → `application/pipeline.py`；实际模型请求在 `llm/client.py`。

共享知识库与文件处理位于 `../shared/`；三套会话、任务和版本仍独立保存。
