# AI 智能助手 V1.0 架构审计

## 1. 审计范围与基线

- 审计日期：2026-10-29
- 开发基线：`origin/main@38a0815`
- 开发分支：`feat/ai-assistant-v1`
- 审计范围：账户 AI 配置、Provider、结构化分析、驾驶舱统计、权限、前端路由、Docker Compose 与 CI。

## 2. 可复用能力

| 能力 | 现有实现 | 复用方式 |
| --- | --- | --- |
| 个人默认模型 | `apps.accounts.UserAIConfiguration` | 作为助手模型选择器中的虚拟默认项，不改变其一对一语义 |
| 凭据加密 | `apps.accounts.crypto` | 多模型配置继续使用 Fernet 加密，只返回末四位掩码 |
| Provider 配置 | `apps.accounts.ai_service`、`ai.providers` | 默认模型沿用原配置；后台结构化分析调用链保持不变 |
| Ollama | `OllamaModelsView`、OpenAI 兼容协议 | 助手模型配置提供独立发现接口并增加 SSRF 校验 |
| 业务统计 | `apps.reports.services` | 六个只读工具直接组合统一统计口径，不重复实现指标 |
| 最终有效语料 | `reviews.services.final_corpus` | 搜索和证据仅使用治理、AI 决策和结构化校验后的最终语料 |
| 权限 | TokenAuthentication、DRF Permission | 所有助手 API 强制登录，查询集按当前用户隔离 |
| 深色主题 | 驾驶舱主题变量与组件样式 | 助手工作台沿用深蓝黑、科技蓝和青绿色体系 |
| CI 与部署 | GitHub Actions、三套 Compose | 新功能纳入现有 Ruff、Mypy、Pytest、ESLint、TypeScript、Vitest 与构建门禁 |

## 3. 现有 Provider 能力结论

审计时的 `AIProvider` 只定义 `analyze_review()` 和 `check_connectivity()`，OpenAI 兼容实现使用同步非流式 JSON 请求；不存在通用聊天、原生工具调用、SSE 流式输出或请求级取消接口。因此不能直接把结构化分析 Provider 当作聊天引擎。

本次采用独立的助手 Provider Client：

1. 保持原结构化分析 Provider 接口不变，避免模型切换影响后台任务。
2. 对支持工具调用的 OpenAI 兼容模型，先请求一次原生工具规划。
3. 模型不支持工具调用或返回格式不可用时，进入受控关键词路由；模型文本不会被当作命令。
4. 总结阶段通过 SSE 读取模型输出；取消时关闭流并阻止后续工具或状态回写。
5. Mock Provider 走确定性回退，自动测试不访问付费模型。

## 4. 必须扩展的模块

- 新增 `apps.assistant`：模型配置、会话、消息、工具、编排、SSE 与限流。
- 新增前端助手工作台与模型管理组件。
- 在驾驶舱保留当前筛选条件跳转助手。
- 在 Nginx API 代理关闭缓冲并增加流式读取超时。
- 配置 Redis Cache，用于跨 Gunicorn Worker 的单用户并发锁和 DRF 限流。

## 5. 兼容性与安全风险

| 风险 | 处理 |
| --- | --- |
| 部分模型不支持 function calling | 自动使用严格 Schema 的受控路由回退 |
| 部分兼容接口不返回流式 Token 用量 | 用量字段允许为空，不伪造 Token；仍记录模型和耗时 |
| 模型地址可能造成 SSRF | 保存及调用前校验协议、凭据、DNS 和 IP；内网 Ollama 必须显式白名单 |
| DNS 重绑定 | 每次实际调用前重新解析并校验；不跟随重定向且禁用系统代理 |
| 提示词注入 | 用户帖子仅作为工具数据；系统提示明确隔离，工具名和参数均由白名单与 Pydantic 校验 |
| SSE 断线或页面刷新 | 生成器关闭后写入 `CANCELLED`，不会恢复为 `RUNNING` |
| 重复提交 | 服务端唯一 `request_id`，完成请求可安全重放且不重复保存用户消息 |
| 多进程并发 | Redis 原子锁、会话行锁和数据库唯一请求 ID 三层约束 |
| 模型配置删除 | 会话外键置空，消息保留模型名称、Provider 和配置 ID 快照，不保留凭据 |

## 6. 审计结论

现有统计与治理体系可作为可靠数据底座，但原 Provider 不具备助手运行能力。新增独立助手边界是最小兼容方案：业务统计继续由 Django 服务层负责，模型只能总结经白名单工具返回的数据，不能直接访问 SQL、ORM 或写操作。

