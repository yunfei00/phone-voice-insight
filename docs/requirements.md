# 需求说明

## 项目背景

公开评价和社区讨论分散在不同平台，字段、结构、层级与语义并不一致。PVI 希望把荣耀 Power2 的真实公开反馈统一保存，并为后续清洗、结构化分析、聚类、趋势和报告提供可信底座。

## 用户目标

- 研究人员能够确认数据来自哪个平台、入口、产品和时间。
- 运营人员能够查看采集任务状态及失败原因，而不是把未执行任务当作成功。
- 产品人员能够按来源、记录类型、官方身份和时间筛选反馈。
- 后续分析能够引用原始证据，并追溯模型和 Prompt 版本。

## Phase 1 范围

- Monorepo、Django、Vue、PostgreSQL、Redis、Celery/Beat、Docker Compose。
- 产品、来源、采集任务、反馈、分析和报告的基础模型。
- 分页 API、过滤、健康检查、OpenAPI、Admin。
- 采集器抽象接口、来源骨架、AI Schema、Prompt 和示例。
- 自动化测试、lint、类型检查、构建、CI、脚本与文档。

## 核心用户场景

1. 管理员在 Admin 维护产品、来源和合规采集入口。
2. 用户在前端选择产品、来源与入口创建采集任务。
3. 用户看到任务状态；Phase 1 执行时得到明确的“collector not implemented”失败。
4. 用户分页浏览和筛选已导入的统一反馈。
5. 用户检查后端、数据库和 Redis 健康状态。
6. 开发者通过 Schema 和契约实现下一阶段采集或 AI 能力。

## 功能需求

- 初始化荣耀、荣耀 Power2、指定别名/版本、京东和荣耀俱乐部。
- 同一来源下非空 `external_id + record_type` 数据库级唯一。
- 列表接口统一使用 `count/next/previous/results` 分页结构。
- 反馈支持来源、产品、类型、官方身份、时间和关键词筛选。
- 任务状态至少包含 PENDING、RUNNING、PAUSED、SUCCESS、FAILED、CANCELLED。
- 前端所有统计来自 API；空数据为 0，不硬编码业务数字。
- 健康检查不返回密码、连接串或内部主机信息。

## 非功能需求

- Python/TypeScript 严格类型、格式化、lint 和自动化测试。
- 开发配置支持热更新；数据服务可持久化并有 healthcheck。
- 依赖有锁文件，CI 不需要真实密钥或外部网站。
- API、采集、分析和展示分层，失败可见且可追踪。
- 中文文档为主，编码 UTF-8，时间统一使用带时区 ISO 8601。

## 明确不做

真实京东/荣耀俱乐部采集、验证码或反爬绕过、AI 调用、Embedding/聚类、RAG、评分算法、复杂商业 UI、用户权限/付费、Kubernetes。

## 验收标准

- 后端迁移、初始化数据、测试、Ruff 和 mypy 通过。
- 前端 lint、typecheck、Vitest 与 build 通过。
- 默认 Compose 定义六个主要服务并通过静态解析；在有 Docker 的环境可构建启动。
- 前端/API/Admin/Swagger/ReDoc 路由完整。
- 采集任务未实现时持久化 FAILED 和错误信息，不产生反馈。
- 仓库不含 `.env`、数据库、缓存、构建目录或真实秘密。
