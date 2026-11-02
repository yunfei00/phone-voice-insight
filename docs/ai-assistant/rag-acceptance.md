# AI 数据查询与 RAG V1.0 自动验收报告

## 1. 验收信息

- 日期：2026-10-31
- 基线：`main@88cabce2e5c3b271111871bd106b1390c2656c31`
- 分支：`feature/ai-data-rag-v1`
- Pull Request：`https://github.com/yunfei00/phone-voice-insight/pull/20`
- 隔离 Docker 项目：`pvi-rag-validation`
- 生产环境：未更新

## 2. 功能结论

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 六个受控只读工具 | PASS | Pydantic + LangChain StructuredTool，参数/数量受限 |
| 帖子与回复查询 | PASS | THREAD 主记录、回复内容可召回、详情返回回复树 |
| 统计和趋势 | PASS | 复用 `apps.reports.services` 最终有效 AI 语料口径 |
| 产品比较 | PASS | 返回分子、分母、时间范围和可信度数据 |
| 混合检索 | PASS | 关键词、中文二元召回、pgvector 余弦、去重重排 |
| 增量与删除同步 | PASS | post-save 提交索引、OneToOne CASCADE、周期对账 |
| 失败降级 | PASS | Embedding 异常记录 FAILED，查询降级关键词 |
| 历史断点续跑 | PASS | `RagIndexRun.checkpoint_review_id` + 分批 Celery |
| 助手执行状态 | PASS | 理解、查询/检索、生成三个实际阶段 |
| 可追溯证据 | PASS | 帖子 ID、标题、摘要、URL、匹配依据 |
| Prompt Injection 防护 | PASS | 帖子内容明确标记为不可信，只能走白名单工具 |

## 3. 自动测试

### 后端

- Ruff format：PASS（235 个文件）。
- Ruff check：PASS。
- mypy：PASS（235 个源文件）。
- migration check：PASS。
- structured contract：PASS。
- pytest：385 PASS、2 SKIPPED；其中新增 RAG 模块 36 PASS。
- 两个 SKIPPED 是需要显式开启的 Honor/JD 真实站点测试，不伪造通过。

Windows 默认临时目录权限导致首次全量 pytest 在最后一个用例 setup 报错；改用工作区独立 `--basetemp` 后同一代码全量通过。该错误不是业务测试失败。

### 前端

- ESLint + Prettier：PASS。
- TypeScript：PASS。
- Vitest：37 PASS。
- Production Build：PASS。

第一次 `npm ci` 后并行执行时，一个既有侧栏测试超过 5 秒；原命令立即复跑 37/37 PASS，未修改断言或超时阈值。

## 4. 固定检索评测

数据集：`docs/ai-assistant/rag-evaluation-v1.json`，10 个固定中文手机问题场景。

| 指标 | 结果 |
| --- | ---: |
| Recall@5 | 1.00 |
| 引用准确率 | 1.00 |
| 回答正确率（目标帖子命中） | 1.00 |
| P50 | 4.39 ms |
| P95 | 5.12 ms |

该延迟来自本地 SQLite 固定小数据集，只用于回归比较，不能等同生产大数据 PostgreSQL 延迟。PostgreSQL 验收实际验证了 pgvector 扩展、HNSW 索引和迁移，未伪造大规模性能结果。

## 5. Docker 验收

服务器独立环境实际执行：

- Compose build：PASS。
- PostgreSQL 17.11 + pgvector 0.8.7：PASS。
- `rag_doc_embedding_hnsw`：存在。
- assistant 0001～0004 migrations：全部 applied。
- Backend：healthy。
- PostgreSQL：healthy。
- Redis：healthy。
- Celery Worker：healthy。
- Celery Beat：healthy。
- Frontend：healthy，HTTP 200。
- Backend health API：HTTP 200，database/redis 均 ok。
- RAG 索引 API 未认证访问：HTTP 401，权限边界正确。
- 六容器整体重启后：全部恢复 healthy，索引运行记录和 vector 0.8.7 扩展仍存在。

开发 Compose 的前端健康检查最初使用 `localhost`，Alpine 将其解析为未监听的 `::1`；已改为 `127.0.0.1` 并复验 healthy。

## 6. 安全检查

- 未提交 API Key、密码、`.env`、本地数据库或测试 Volume。
- Embedding URL 使用现有 DNS/IP SSRF 防护。
- 模型无 SQL、ORM、写操作和管理操作能力。
- 测试使用 fake Embedding，不调用付费模型。
- 隔离验收没有读取、修改或删除生产业务数据。

## 7. GitHub CI

- Backend：PASS（41 秒）。
- Frontend：PASS（1 分 14 秒）。
- CI Run：`https://github.com/yunfei00/phone-voice-insight/actions/runs/41157649986`
- PR 保持 OPEN，未合并 `main`。

## 8. 已知限制

1. 默认 Embedding Provider 为 `disabled`；正式配置前只有关键词检索，这是安全降级而不是故障。
2. 未使用真实外部 Embedding 服务，避免在没有凭据和预算授权时产生费用。
3. 固定评测集为 10 个中文场景，尚未代表全部口语、方言和跨语言表达。
4. 尚未在生产真实数据规模测量 PostgreSQL P50/P95；部署前应先在生产副本执行容量评测。
5. V1 使用固定 1024 维；更换不同维度模型需要新 migration 或独立索引版本。

## 9. 结论

代码、自动测试和隔离 Docker 验收达到创建 PR 的条件。正式生产部署与真实外部 Embedding 服务验证仍需在 PR 审核后按部署文档执行；本分支不会自动合并 `main`。

