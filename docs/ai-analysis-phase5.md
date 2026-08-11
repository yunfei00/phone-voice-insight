# Phase 5：AI 结构化分析

## 状态与范围

Phase 5 当前为 **IN PROGRESS**。代码链路、管理命令、API、管理页面和离线测试已经实现；生产环境尚未配置真实 AI，因此真实 20 条 PoC、人工复核、100 条扩量和 278 条全量分析均不得开始。Fake Provider 只用于 pytest、CI 和本地联调，不能替代真实 PoC。

本阶段只把 Phase 4 治理后的荣耀 Power2 用户语料转换为可追溯的结构化结果，不做产品评分、问题排行、聚类、趋势、RAG、问答或产品结论。

唯一允许的输入是当前 `CORPUS_VERSION` 的 `AnalysisCorpusItem`，并同时满足：

```text
eligible = true
quality.eligible_for_ai = true
product = HONOR_POWER2
source = HONOR_CLUB
```

`OFFICIAL_REPLY`、低信息、页面噪声、宣传内容、产品不匹配及最终人工 override 后不合格的记录不会进入模型。

## 处理链路

```text
AnalysisCorpusItem
  -> ReviewAnalysisInput（当前文本与上下文分离）
  -> provider-neutral AIProvider
  -> 去除可选 Markdown fence
  -> json.loads
  -> ReviewAnalysisOutput.model_validate
  -> 业务校验
  -> 原文/上下文逐字证据校验
  -> AnalysisResult + AspectResult
  -> AnalysisEvaluation（人工）
```

证据必须是连续、逐字存在的原文。当前记录的 `evidence_text` 只能来自当前 `ReviewRecord.content`；上下文依赖结果还必须给出上下文记录 ID 和逐字 `context_evidence_text`。第一次证据失败会把受控反馈交给模型重试一次，第二次失败以 `EVIDENCE_VALIDATION_FAILED` 结束，不保存看似合理的幻觉结果。

相同 provider、model、prompt 和 `input_hash` 已有成功结果时直接跳过。输入指纹为：

```text
SHA256(corpus_version + normalized_text + context_text + prompt_version)
```

## Provider 配置

默认 provider 为 `openai_compatible`，支持任意兼容 Chat Completions 的服务：

```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=
AI_API_KEY=
AI_MODEL=
AI_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=2
AI_CONCURRENCY=2
AI_TEMPERATURE=0
AI_MAX_OUTPUT_TOKENS=1500
```

缺少 base URL、key 或 model 时显式返回 `AI_NOT_CONFIGURED`。日志、错误消息、数据库 `raw_result` 和前端接口均不得包含 API key、Authorization 或完整 HTTP headers。若 provider 返回 token usage 则原样保存；否则保留为 `NULL`，不估算。

自动重试只允许 timeout、HTTP 429 和 5xx，最多 2 次并指数退避。认证、配置、Schema 和业务校验失败不做 provider 重试。Celery 入口按 10 条切分处理；第一版实际执行串行处理，因此不会超过并发上限 2。

## Prompt 与输出

生产默认使用不可变的 `review_analysis_v2`。v1 保留用于历史追溯；需要修正规则时新增 v3，不覆盖 v2。输出只允许固定 15 个一级 Aspect，详见 [AI 分类体系](ai-taxonomy.md)。一条反馈可以产生多个 Aspect；`MIXED` 只表示同一 Aspect 同时有明确正反评价。

## 命令

真实调用前先执行不含用户数据、也不读取评论表的最小连通性检查：

```bash
python manage.py check_ai
```

成功时只输出 provider、model 和 `connectivity=OK`；失败时只输出受控错误类型、HTTP status 和可选 provider request ID。该命令不会输出 API key、Authorization 或完整 headers。

先预览全部合格语料，dry-run 不读取 provider、不调用网络，也不写入分析结果：

```bash
python manage.py analyze_reviews \
  --product HONOR_POWER2 \
  --source HONOR_CLUB \
  --prompt-version review_analysis_v2 \
  --dry-run
```

固定种子 `20260808` 会覆盖 THREAD/REPLY、短/长文本、有/无上下文、正/负面及多 Aspect，再以稳定哈希补齐，避免简单取数据库前 N 条。

真实 20 条命令：

```bash
python manage.py analyze_reviews \
  --product HONOR_POWER2 \
  --source HONOR_CLUB \
  --prompt-version review_analysis_v2 \
  --limit 20
```

也支持 `--record-id`、逗号分隔的 `--record-ids`、`--retry-failed`、`--force` 和 `--seed`。`--force` 仍不会放宽治理资格或证据规则。固定 PoC 必须保存 review ID 后通过 `--record-ids` 重放，不能依赖数据库前 20 条。

真实 CLI 单次最多运行 20 条。超过 20 条必须显式增加 `--allow-large-run`；API 对 100/278 条任务要求 `allow_large_run=true`，前端必须再次弹窗确认。dry-run 不调用 AI，不受该费用闸门限制。

## 严格执行闸门

必须按以下顺序执行，前一步没有真实通过时禁止进入下一步：

1. 全部 278 条 dry-run，核对输入与上下文。
2. 用真实 provider 分析固定样本 20 条。
3. 人工复核 20 条；Schema、证据和持久化均为 100%，Aspect/Sentiment 不低于 90%，严重幻觉为 0。
4. 扩大到 100 条。
5. 人工随机复核 50 条并保存 `AnalysisEvaluation`。
6. 达标后分析剩余语料，最终覆盖 278 条。

真实 AI 未配置时应停在第 1 步之后，报告 `AI_NOT_CONFIGURED`，不得切换到 Fake、不得把模型输出自动当作人工 Gold Label。

## 管理界面与 API

AI 分析页展示合格、已分析、成功、失败和待分析数量，以及 Schema/Evidence 质量和人工评估状态；支持创建 20/100/278 条任务、查看最近批次、结果筛选、原文/上下文证据对照及简化人工评估。配置接口仅返回 provider、model、prompt、configured 和 concurrency，不返回密钥。

主要接口：

```text
GET  /api/v1/analysis-results/
GET  /api/v1/analysis-results/summary/
POST /api/v1/analysis-results/{id}/evaluate/
GET  /api/v1/analysis-batches/
POST /api/v1/analysis-batches/
GET  /api/v1/analysis-batches/configuration/
```
