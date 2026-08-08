# 更新日志

格式参考 Keep a Changelog，版本遵循语义化版本。

## [Unreleased]

### Added

- Phase 4 荣耀数据治理：`ReviewQuality`、版本化 `ReviewQualityRun`、`AnalysisCorpusItem`、确定性规则 Pipeline、上下文构建、人工覆盖、Celery 任务、管理命令和数据质量 API/页面。
- 荣耀 FULL/INCREMENTAL 采集统计与连续 20 个已知帖子边界；首阶段安全配置为 5 页/100 帖，硬上限 10 页/200 帖。
- Phase 4 真实扩容与质量报告：10 页实际覆盖 97 个主题、487 条记录，固定 100 条样本在最终 v7 规则下复核通过；真实增量任务在连续 20 个已知主题处停止。
- 京东 Phase 3.1 可视浏览器辅助探测工具：独立 Chrome profile、XHR/fetch 元数据索引、候选结构检测、最多 3 条递归脱敏样本，以及默认关闭的 live 开关。
- 京东接口发现报告；本次隔离会话分类为 `C JD_REVIEW_ACCESS_BLOCKED`，未启用 SourceTarget，也未采集真实评价。
- 京东 PoC 失败关闭框架：商品身份门禁、严格 SSRF 校验、固定身份 4 秒限速、登录/重定向阻断、JSON/JSONP 安全解析。
- JD 评价/追评标准化、评分与 SKU 属性契约、`SourceProductVariant` 映射、逐页 checkpoint、去重和隐私 allowlist。
- `jd_poc` 受限命令、默认关闭的 JD live smoke test、脱敏合成 fixtures，以及 API/前端 rating/product_variant 筛选与展示。
- 荣耀俱乐部公开 HTML 采集器，支持 Power2 话题、帖子、楼层回复、内嵌评论、角色与时间解析。
- Honor Club HTTP 安全校验、单并发 3 秒限速、阻断页面检测、产品相关性过滤和脱敏持久化。
- 采集器注册表、运行服务、ReviewRecord 持久化、稳定内容哈希、去重和逐帖 checkpoint。
- Celery 真实采集任务、采集执行 API、管理命令及前端执行/轮询与反馈详情筛选。
- 脱敏 HTML fixtures、解析/角色/时间/父子关系/去重测试，以及默认禁用的在线 smoke test。

### Changed

- 京东 Phase 3 因外部访问限制调整为 `POSTPONED`；保留已有 collector、探测工具和离线测试，第一版产品改为只依赖荣耀俱乐部数据。
- 荣耀俱乐部完成 2 页/20 帖门禁与重复运行去重；客户端兼容同源、同帖的 `mobile=2` 重定向并逐跳验证。
- `NormalizedReview` 新增 `rating`、`variant_external_id`、`variant_attributes`，通用持久化层写入 rating/product_variant。
- 扩展 `NormalizedReview` 与作者角色，新增 `MODERATOR`、`EXPERT`。
- Docker 后端镜像包含共享 collectors/ai 包；补充 Phase 2 PoC 文档和开发说明。
- 后端镜像构建支持通过 `UV_DEFAULT_INDEX_URL` 选择 Python 包索引，改善受限网络下的可重复部署。

### Known issues

- 2026-08-08 京东独立可视 Chrome 探测仍受登录/访问限制，369 条脱敏响应索引中有 70 条 HTTP 403，未确认评价接口。JD SourceTarget 默认停用，未采集真实京东评价。

## [0.1.0] - 2026-07-30

### Added

- Phase 1 Monorepo、Django REST 后端、Vue 管理端。
- PostgreSQL、Redis、Celery Worker/Beat 和 Docker Compose。
- 产品、来源、采集、反馈、分析、报告模型与初始化迁移。
- 分页筛选 API、健康检查、Admin、OpenAPI、Swagger/ReDoc。
- 采集器与 AI 契约、测试、CI、脚本和中文文档。
