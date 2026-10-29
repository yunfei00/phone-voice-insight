# AI 智能助手 V1.0 设计说明

## 1. 目标

为登录用户提供基于真实最终有效 AI 语料的连续问答、产品对比、问题统计、趋势与证据查询。助手不执行采集、治理、删除、配置修改或任意数据库操作。

## 2. 架构

```text
Vue 助手工作台
  ├─ 模型/会话 REST API
  └─ Chat SSE + Cancel
          ↓
AssistantOrchestrator
  ├─ 原生工具规划（可用时）
  ├─ 受控路由回退
  ├─ Pydantic 参数校验
  └─ 只读业务工具
          ↓
apps.reports.services + final_corpus_reviews
          ↓
真实 Review / Governance / StructuredAnalysis 数据
```

## 3. 数据模型

- `AssistantModelProfile`：用户可保存多个模型配置，API Key 加密保存。
- `AssistantConversation`：当前用户、标题、所选模型、状态、上下文与最后消息时间。
- `AssistantMessage`：服务端 UUID、唯一请求 ID、消息状态、模型快照、证据、工具轨迹、用量和安全错误。

个人默认模型仍使用 `UserAIConfiguration`。助手配置不修改后台结构化分析任务所读取的配置。

## 4. 工具边界

| 工具 | 数据口径 |
| --- | --- |
| `get_product_overview` | 复用驾驶舱 overview |
| `get_issue_statistics` | 复用 issue_rows/categories，只含明确负面问题 |
| `compare_products` | 对 2～5 个产品分别使用统一 overview/categories |
| `search_feedback` | 仅搜索 final corpus，限制 30 条 |
| `get_issue_evidence` | 复用 issue_detail，证据可追溯 ReviewRecord |
| `get_feedback_trends` | 复用驾驶舱按日趋势 |

所有结果携带时间范围、样本量、数据截止时间和口径说明。

## 5. 对话与取消

- 前端生成请求 UUID；后端用唯一约束保证幂等。
- 同一用户最多一个正在执行的请求，Redis 锁自动过期。
- 每个会话限制消息总数，模型上下文只取最近消息和限定字符数。
- 取消接口立即把会话和消息置为 `CANCELLED`；流循环每个数据块检查状态并关闭上游连接。
- 浏览器断线触发生成器关闭，后端记录 `ASSISTANT_DISCONNECTED`。

## 6. 前端设计

工作台包含历史会话、模型切换、产品/来源/时间筛选、快捷问题、流式消息、停止生成、证据卡片和模型管理。Markdown 使用结构化文本节点渲染，不使用 `v-html`，防止脚本注入。窄屏下会话列表、筛选器和输入区改为单列布局。

## 7. 安全设计

- 全部 API 必须登录，模型和会话 QuerySet 绑定 `request.user`。
- API Key 永不出现在响应、日志、模型快照或工具结果。
- HTTP 请求 `trust_env=False`、不跟随重定向。
- 公网地址必须解析为全局 IP；私网 Ollama 仅允许管理员白名单主机。
- 工具参数严格校验并限制行数，不接受 SQL、模型名或 ORM 路径。
- 模型只接收工具快照，用户反馈内容明确视为不可信数据。

