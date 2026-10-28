# 手机用户声音平台 V1.0 三阶段一体化验收报告

## 1. 交付基线

- 开发基线：`eeed2d9`（PR #4 已由此前流程合入 `main`）
- 功能实现提交：`2a0f9fb`；生产部署应用提交：`a8ae8f2`
- 开发分支：`main`（遵循用户在本轮开始前“先合并全部分支到 main，再执行”的最新指令）
- 原始数据处理：未删除、未重建任何现有 `ReviewRecord`
- AI 密钥处理：未修改、未输出、未写入仓库或日志

## 2. 第一阶段：采集稳定性

### 修复内容

- 同一来源使用数据库租约串行执行；不同产品允许创建等待任务。
- 来源等待队列按任务创建时间和 ID 公平调度，当前任务完成、失败或停止后自动续接下一任务。
- 派发令牌和执行令牌分别防止丢失消息重复派发、重复 Celery 消息并发执行以及旧 Worker 覆盖新执行状态。
- 任务持久化心跳；巡检仅在心跳超时且来源租约已经失效时恢复，避免把正常长网络请求误判为失联。
- Worker 失联恢复保留 `last_checkpoint`，关闭旧运行记录后以新执行代次继续。
- PENDING 消息丢失超过安全窗口后由每分钟巡检重新派发，不消耗 Celery 重试次数。
- WAITING、RUNNING、STOPPING、CANCELLED、SUCCESS、FAILED 状态均提供中文展示和等待原因。
- FULL 继续采用“发现 → 详情与全部回复分页 → 重试 → 完整性验证”的持久化分块流程；10 页只是默认单块页数，不是全量上限。
- 采集有新增记录时异步触发自动治理/分析流水线；触发失败只记录日志，不反向破坏采集成功状态。

### 数据库变更

- `CollectionTask`：派发令牌、派发时间、执行令牌、心跳、等待原因。
- `CollectionRun`：执行令牌。
- `CollectionSourceLease`：租约拥有者令牌。
- 迁移：`collection/0009_collectionrun_execution_token_and_more.py`。

## 3. 第二阶段：数据治理 V1.0

### 修复内容

- 数据质量页新增统一“产品与处理范围”，同一产品/来源同时控制质量统计、规则治理、AI 自动判断、任务历史和治理结果。
- 治理结果、治理任务、AI 判断任务和 AI 判断结果均使用后端分页，默认每页 10 条；切换范围自动回到第一页。
- AI 决策改为 `ACCEPTED`、`REJECTED`、`UNCERTAIN`、`ERROR` 四态。
- 高精度策略：规则与 AI 一致且置信度不低于 0.85 才自动接受；冲突、低置信度或证据不足标记为不确定且不进入结构化分析。
- 官方内容自动排除普通用户体验统计；技术错误不会被当成无效反馈。
- 短回复可使用父帖内容作为证据来源，但不会编造证据。
- AI 技术错误最多重试 1～3 次（默认 2 次），每次尝试和 Token 用量均持久化。
- 管理员人工接口仍保留用于历史诊断，但不再是自动流程前置条件。

### 数据库变更

- `GovernanceTask.trigger_type`：区分手动与采集后自动。
- `GovernanceAIReview`：新四态与 `attempt_count`。
- `GovernanceAIBatch`：自动标记、来源范围、四态计数、输入输出 Token 汇总。
- 迁移：`reviews/0012`、`0013`、`0014`。

## 4. 第三阶段：AI 自动结构化分析

### 自动流水线

正常路径为：

`采集新增数据 → 规则治理 → AI 自动决策 → 仅 ACCEPTED 候选进入结构化分析 → Schema/证据校验 → 聚合展示`

- 复用用户现有 AI Provider、模型和加密凭据，不新增平行 Provider。
- 自动任务幂等检查产品级治理任务和 AI 批次，避免重复运行。
- 每日 Token 预算、批量大小、每分钟请求数、错误尝试次数均可配置。
- 自动流水线默认关闭，部署确认配置和预算后通过 `AI_AUTOMATION_ENABLED=true` 启用。
- 每 5 分钟巡检尚未治理的新记录；采集完成也会立即触发一次。
- 结构化分析页展示产品范围、分析量、成功量、观点数量、失败量、高频问题、证据和最近任务，列表及任务均分页。

### 真实 AI 验收保护

- 独立开关：`AI_LIVE_ACCEPTANCE_ENABLED=false`（默认）。
- 硬上限：`AI_LIVE_ACCEPTANCE_MAX_ITEMS<=10`。
- 显式命令：`python manage.py live_ai_acceptance --product-id <ID> --max-items 10`。
- 生产环境用户 AI 配置连通性已真实验证：OpenAI Compatible / `deepseek-flash`，HTTP 200；密钥未输出。
- 真实治理小样本 3 条：接受 1、不确定 2、错误 0；输入 Token 1894、输出 Token 186。
- 结构化分析共进行了 5 次受控调用（前两次为同一批有限重试，后三次均为单次重试），均收到 HTTP 200，但依次暴露并修复了容器 Prompt 路径、Schema/Taxonomy 注入、输出上限、证据偏移和业务域一致性问题。
- 最后一条实际响应输入 Token 3000、输出 Token 2376；失败原因已收敛为模型没有把 `aspect_code` 放入冗余的 `business_domains`。代码已加入仅基于返回标签的确定性一致性校正并有自动测试，但为控制付费调用，本轮未再次请求模型，因此不把结构化真实验收标记为通过。
- 生产 `AI_AUTOMATION_ENABLED` 继续保持 `false`，避免在结构化真实闭环尚未复验时自动消耗预算。

## 5. 自动化测试结果

### 后端

- `uv run ruff check .`：PASS
- `uv run mypy . ../collectors ../ai ../tools`：PASS，208 个源文件无类型错误
- `uv run python manage.py makemigrations --check --dry-run`：PASS，无模型差异
- `uv run pytest --basetemp=<workspace-temp>`：**301 passed, 2 skipped, 0 failed**
- 两项跳过均为默认关闭的真实外网测试（荣耀、京东），不影响 Mock/解析器/业务闭环测试。

### 前端

- `npm run lint`：PASS
- `npm run typecheck`：PASS
- `npm run test -- --run`：**15 passed, 0 failed**
- `npm run build`：PASS

### Docker 与生产健康检查

- 目标服务器：`106.52.122.214`，部署目录 `/opt/apps/phone-voice-insight`。
- PostgreSQL、Redis、backend、frontend、celery-worker、celery-beat 共 6 个容器全部 healthy。
- Celery inspect：1 个 worker 在线并返回 `pong`。
- 公网 `/phone/`：HTTP 200；`/phone/api/v1/health/`：HTTP 200，数据库与 Redis 均为 `ok`。
- 迁移一致性：`makemigrations --check --dry-run` 无差异。
- 升级前数据库备份：`/opt/apps/backups/phone-voice-insight/postgres-20261028-204214.sql.gz`；环境配置备份：`env-20261028-205346`。
- 升级后保留 9428 条原始记录、8 个采集任务、230 个采集运行；当前采集、治理、AI 治理、结构化分析活动任务均为 0。

### GitHub CI

- `dbd59b5` 及此前功能提交 CI 全绿。
- `58edb6d` 曾因 Ruff format 门禁失败，已按 CI 同一命令修复并提交 `a8ae8f2`；最终提交的 CI 状态以 GitHub Actions 最新运行结果为准。

## 6. 主要修改文件

- 采集：`backend/apps/collection/models.py`、`tasks.py`、`views.py`、`services/orchestration.py`、`services/collection_runner.py`、`services/honor_full.py`
- 治理：`backend/apps/reviews/models.py`、`ai_views.py`、`views.py`、`tasks.py`、`services/ai_governance.py`、`services/automatic_pipeline.py`
- 分析：`backend/apps/analysis/structured_views.py`、`management/commands/live_ai_acceptance.py`
- 调度与配置：`backend/config/celery.py`、`backend/config/settings/base.py`、`.env.example`
- 前端：`CollectionTasksView.vue`、`DataQualityView.vue`、`StructuredAnalysisView.vue`、API 与类型定义
- 测试：采集治理、AI 治理、自动流水线、前端采集和结构化分析组件测试

## 7. 已知风险与未完成外部验收

- 真实 AI 治理已通过，但结构化分析在最后一项一致性修复后尚未再次调用模型复验，因此自动流水线保持关闭。
- 历史两次结构化失败发生在失败 Token 记账修复之前，对应调用用量无法从本地记录精确恢复；后续失败已能保存 Token。
- 荣耀真实站点测试默认关闭，本轮部署未发起大规模采集；所有网络限制与合规节流规则保持不变。
- 前端生产构建仍有单个大于 500 kB 的公共依赖 chunk 警告，不影响构建成功，后续可单独做代码分包优化。

## 8. 部署升级步骤与回滚

### 升级

1. 备份 PostgreSQL，确认当前无关键采集任务正在写入。
2. 拉取本次提交并更新 `.env`；先保持 `AI_AUTOMATION_ENABLED=false`。
3. 执行 `docker compose build` 和 `docker compose run --rm backend python manage.py migrate`。
4. 启动服务并检查 PostgreSQL、Redis、backend、frontend、celery-worker、celery-beat 健康状态。
5. 验证采集等待队列、数据质量页和结构化分析页。
6. 确认至少一个管理员/分析员的个人 AI 配置可用且每日预算合理后，再设置 `AI_AUTOMATION_ENABLED=true` 并重启 backend、worker、beat。

### 回滚

1. 先设置 `AI_AUTOMATION_ENABLED=false` 并停止 worker/beat，避免产生新自动任务。
2. 回滚应用镜像到升级前提交。
3. 数据迁移只新增可空或有默认值字段；如必须回退迁移，应先备份并依次回退 `reviews 0014 → 0013 → 0012`、`collection 0009`。
4. 不删除 `ReviewRecord`、治理结果、分析结果或历史采集运行。

## 9. 最终结论

代码、数据库迁移、Docker 部署、生产健康检查和真实 AI 治理小样本均已验证；现网服务可用且原有数据完整保留。结构化分析的最后一致性修复已通过自动测试但尚未再次进行付费模型复验，因此 AI 自动流水线仍安全关闭，本报告不宣称端到端 AI 自动结构化验收通过。
