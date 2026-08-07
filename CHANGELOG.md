# 更新日志

格式参考 Keep a Changelog，版本遵循语义化版本。

## [Unreleased]

### Added

- 荣耀俱乐部公开 HTML 采集器，支持 Power2 话题、帖子、楼层回复、内嵌评论、角色与时间解析。
- Honor Club HTTP 安全校验、单并发 3 秒限速、阻断页面检测、产品相关性过滤和脱敏持久化。
- 采集器注册表、运行服务、ReviewRecord 持久化、稳定内容哈希、去重和逐帖 checkpoint。
- Celery 真实采集任务、采集执行 API、管理命令及前端执行/轮询与反馈详情筛选。
- 脱敏 HTML fixtures、解析/角色/时间/父子关系/去重测试，以及默认禁用的在线 smoke test。

### Changed

- 扩展 `NormalizedReview` 与作者角色，新增 `MODERATOR`、`EXPERT`。
- Docker 后端镜像包含共享 collectors/ai 包；补充 Phase 2 PoC 文档和开发说明。
- 后端镜像构建支持通过 `UV_DEFAULT_INDEX_URL` 选择 Python 包索引，改善受限网络下的可重复部署。

## [0.1.0] - 2026-07-30

### Added

- Phase 1 Monorepo、Django REST 后端、Vue 管理端。
- PostgreSQL、Redis、Celery Worker/Beat 和 Docker Compose。
- 产品、来源、采集、反馈、分析、报告模型与初始化迁移。
- 分页筛选 API、健康检查、Admin、OpenAPI、Swagger/ReDoc。
- 采集器与 AI 契约、测试、CI、脚本和中文文档。
