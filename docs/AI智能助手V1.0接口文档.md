# AI 智能助手 V1.0 接口文档

所有接口前缀为 `/api/v1`，使用 `Authorization: Token <token>`。所有错误返回中文安全信息，不返回 API Key 或内部异常栈。

## 1. 模型配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/assistant/models/` | 查询当前用户模型及个人默认虚拟项；新增配置 |
| GET/PATCH/DELETE | `/assistant/models/{id}/` | 查询、修改或删除本人配置 |
| POST | `/assistant/models/{id}/test/` | 最小连接测试 |
| GET | `/assistant/models/{id}/ollama-models/` | 发现受信任 Ollama 模型 |

写入字段：`name`、`provider`、`base_url`、`model`、`api_key`、`thinking_mode`、`temperature`、`timeout_seconds`、`max_output_tokens`、`is_active`。`api_key` 仅写，响应只含 `api_key_configured` 和 `api_key_masked`。

## 2. 会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/assistant/conversations/` | 会话列表与新建 |
| GET/PATCH/DELETE | `/assistant/conversations/{id}/` | 本人会话详情、重命名、切换模型、删除 |
| GET | `/assistant/conversations/{id}/messages/` | 有上限的消息历史 |

选择个人默认模型：`{"use_default_model": true, "model_profile": null}`。选择保存模型：`{"use_default_model": false, "model_profile": 12}`。

## 3. 聊天 SSE

`POST /assistant/conversations/{id}/chat/`

```json
{
  "request_id": "1aaac9bb-c162-4579-8f77-047c3b856ae1",
  "content": "最近七天主要有哪些问题？",
  "product_id": 1,
  "source_id": null,
  "start_date": "2026-10-23",
  "end_date": "2026-10-29"
}
```

响应 `Content-Type: text/event-stream`，事件均为 `data: <JSON>`：

- `start`：已创建服务端消息。
- `tool`：已完成只读工具查询，可能附带证据。
- `delta`：回答文本增量。
- `done`：完成，包含模型与 Token 用量。
- `cancelled`：用户停止或连接断开。
- `error`：安全错误码和中文提示。

相同 `request_id` 的已完成请求会重放，不会重复保存。不同请求在同一用户已有生成任务时返回 429；同一会话冲突返回 409。

## 4. 取消

`POST /assistant/conversations/{id}/cancel/`

取消会立即更新会话和正在生成的消息状态。流式客户端还应关闭本地 `AbortController`。

## 5. 常见错误码

| 错误码 | 含义 |
| --- | --- |
| `AI_NOT_CONFIGURED` | 个人默认配置不存在或不完整 |
| `ASSISTANT_AUTH_FAILED` | Provider 凭据无效 |
| `ASSISTANT_TIMEOUT` | Provider 超时 |
| `ASSISTANT_RATE_LIMITED` | Provider 限流 |
| `ASSISTANT_TOOL_ARGUMENT_INVALID` | 工具参数未通过 Schema |
| `ASSISTANT_CANCELLED` | 用户停止生成 |
| `ASSISTANT_DISCONNECTED` | SSE 客户端断开 |

