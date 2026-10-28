# 手机用户声音平台 V1.0 三阶段一体化验收报告

## 1. 交付基线

- 开发基线：`eeed2d9`（PR #4 已由此前流程合入 `main`）
- 功能实现提交：`2a0f9fb`
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
- 本地环境没有可验证的用户生产凭据，因此本次真实 AI 调用为 **0 条**，Token 用量 **0**，未虚构真实模型验收结果。
- Mock Provider/替身覆盖了自动接受、自动排除、不确定、技术错误、短回复上下文、日预算和接受项入分析队列。

## 5. 自动化测试结果

### 后端

- `uv run ruff check .`：PASS
- `uv run mypy . ../collectors ../ai ../tools`：PASS，208 个源文件无类型错误
- `uv run python manage.py makemigrations --check --dry-run`：PASS，无模型差异
- `uv run pytest --basetemp=<workspace-temp>`：**297 passed, 2 skipped, 0 failed**
- 两项跳过均为默认关闭的真实外网测试（荣耀、京东），不影响 Mock/解析器/业务闭环测试。

### 前端

- `npm run lint`：PASS
- `npm run typecheck`：PASS
- `npm run test -- --run`：**15 passed, 0 failed**
- `npm run build`：PASS

### Docker

- 当前 Windows 执行环境未安装 Docker CLI，因此容器级集成测试标记为 **未验证**，不能写为 PASS。
- Compose 文件未被破坏；应在目标服务器按第 8 节执行容器验收。

### GitHub CI

- 工作流：`CI`，运行编号 `40687379866`
- backend：PASS（Ruff、Mypy、迁移检查、结构化分析契约、完整测试）
- frontend：PASS（npm ci、lint、typecheck、test、build）
- 结论：GitHub CI 全绿。

## 6. 主要修改文件

- 采集：`backend/apps/collection/models.py`、`tasks.py`、`views.py`、`services/orchestration.py`、`services/collection_runner.py`、`services/honor_full.py`
- 治理：`backend/apps/reviews/models.py`、`ai_views.py`、`views.py`、`tasks.py`、`services/ai_governance.py`、`services/automatic_pipeline.py`
- 分析：`backend/apps/analysis/structured_views.py`、`management/commands/live_ai_acceptance.py`
- 调度与配置：`backend/config/celery.py`、`backend/config/settings/base.py`、`.env.example`
- 前端：`CollectionTasksView.vue`、`DataQualityView.vue`、`StructuredAnalysisView.vue`、API 与类型定义
- 测试：采集治理、AI 治理、自动流水线、前端采集和结构化分析组件测试

## 7. 已知风险与未完成外部验收

- 本机没有 Docker，容器健康状态未验证。
- 本机没有生产数据库和生产用户 AI 凭据，真实 AI 小样本调用未执行。
- 荣耀真实站点测试默认关闭，未进行大规模真实抓取；所有网络限制与合规节流规则保持不变。
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

代码级三阶段功能、本地自动化门禁和 GitHub CI 已通过；真实 AI、Docker 与目标服务器部署属于当前环境缺失依赖，均如实标记为未验证。代码已具备部署升级条件，但在目标服务器容器健康检查完成前不宣称生产部署验收通过。
