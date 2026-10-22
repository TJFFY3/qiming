# 限时练习 Agent 前端目录

| 目录 | 职责 |
| --- | --- |
| `__tests__/` | 自动化测试 |
| `components/` | 该 Agent 的界面组件 |
| `domain/` | 类型、默认设置与可编辑提示词 |
| `pages/` | 页面状态、提交与任务轮询 |
| `services/` | 本应用后端 HTTP 客户端 |
| `styles/` | Agent 专用样式 |

页面通过 `services/` 访问本应用后端；模型与知识库请求由后端执行。通用界面组件仍位于 `frontend/src/components/`。
