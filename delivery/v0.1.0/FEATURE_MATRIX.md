# Phone Voice Insight V0.1.0 功能矩阵

> 验收时间：2026-10-29（Asia/Shanghai）
>
> 基线：`origin/main@4a70143`
>
> 发布分支：`release/v0.1.0-acceptance`

状态定义：PASS 为实际执行通过；FAIL 为执行失败；BLOCKED 为环境或外部依赖阻塞；NOT_IMPLEMENTED 为代码不存在；NOT_APPLICABLE 为本版本不适用。

| 模块 | 功能 | 状态 | 验证依据 |
| --- | --- | --- | --- |
| 系统基础 | 登录、退出、会话恢复、过期处理 | PASS | `test_accounts.py`、前端路由测试 |
| 系统基础 | 角色权限及未授权访问保护 | PASS | accounts/reports/reviews API 权限测试 |
| 系统基础 | 前后端接口、异常结构、健康检查 | PASS | 隔离 Docker HTTP `/phone/api/v1/health/` |
| 系统基础 | 深色主题、刷新、路由跳转 | PASS | 前端组件与路由测试、既有生产页面验收 |
| 产品管理 | 列表、新增、编辑、详情 | PASS | `test_products.py`、ProductsView |
| 产品管理 | 删除及关联保护 | PASS | PROTECT/CASCADE 关系与产品 API 测试 |
| 产品管理 | Power/Power 2 匹配、幂等初始化、防重复 | PASS | 产品初始化与采集器测试 |
| 来源采集 | 来源、入口配置与安全验证 | PASS | source target 验证及 SSRF 测试 |
| 来源采集 | 荣耀公开页面采集、分页、去重、回复树 | PASS | collection/full verification/thread tree 测试 |
| 来源采集 | 调度、租约、重试、恢复与状态 | PASS | collection governance/closeout 测试 |
| 来源采集 | 荣耀在线小样本复验 | BLOCKED | 本轮未再次请求外站，避免反爬和重复请求；历史生产数据保留 |
| 来源采集 | 京东真实采集 | NOT_APPLICABLE | 登录墙导致 Phase 3 正式延期，不伪造成功 |
| 原始数据 | 列表、筛选、分页、详情、来源链接 | PASS | `test_reviews.py`、ReviewsView |
| 原始数据 | 帖子、普通回复、官方回复、楼中楼 | PASS | `test_thread_trees.py` |
| 原始数据 | 发布时间、地域缺失值与元数据补全 | PASS | `test_review_metadata.py` |
| 数据质量 | 规则预览、单批治理、后台治理 | PASS | `test_review_governance.py` |
| 数据质量 | 一键治理全部、`source_id=null` | PASS | API 回归测试 + 隔离 Docker/Celery 实际执行 |
| 数据质量 | 进度、部分失败、失败记录重试、幂等 | PASS | 新增 GovernanceTask 异常/重试测试 |
| 数据质量 | AI 复核状态与人工确认 | PASS | governance AI API/task 测试（Mock） |
| 结构化分析 | 配置、连接测试、任务、解析与持久化 | PASS | analysis/structured analysis 测试 |
| 结构化分析 | 情感、分类、体验维度、证据偏移 | PASS | Schema、taxonomy、evidence contract 测试 |
| 结构化分析 | SUCCESS 与结果展示一致 | PASS | StructuredAnalysisView 组件测试、生产库只读核对 |
| 结构化分析 | 本轮真实付费模型调用 | BLOCKED | 无法从 Provider 响应可靠换算人民币 2 元；按指令仅执行 Mock |
| 驾驶舱 | 总览、筛选、趋势、问题排行、真实口径 | PASS | `test_dashboard_v1.py`、dashboard-v1 前端测试 |
| 驾驶舱 | 对比、问题详情、证据追溯、空状态 | PASS | 后端/前端 Dashboard V1 测试 |
| 报告 | 日报、周报、历史列表、详情 | PASS | 确定性报告服务及幂等测试 |
| 报告 | PDF/PPT/文件下载 | NOT_IMPLEMENTED | V0.1.0 未实现，列入后续版本 |
| 监控 | 采集、治理、AI、预算与系统健康 | PASS | operations API 和前端测试 |
| 部署 | Compose 配置、构建、迁移、六服务健康 | PASS | `pvi-v010-acceptance` 隔离项目实测 |
| 部署 | Celery 入队执行、重启后持久化 | PASS | 隔离 Redis/PostgreSQL/Worker 实测 |
| 浏览器证据 | 本轮真实页面截图 | PASS | Playwright 经 SSH 回环隧道访问隔离环境，3 张截图已目视检查 |

## 交付判断

P0/P1 代码缺陷均已修复；核心业务、CI、隔离 Docker 和真实页面截图为 PASS。外站在线复验和真实付费模型调用属于可明确隔离的外部阻塞，不影响已有功能正确性，但报告中不将其标记为 PASS。
