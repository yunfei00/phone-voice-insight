# Phase 5 人工评估

## 原则

人工评估只衡量结构化结果是否忠实于当前原文和必要上下文，不评价手机是否值得购买，也不把模型输出自身当作 Gold Label。尚未人工检查的数据必须显示 `NOT EVALUATED`。

每条 `AnalysisResult` 最多保存一条 `AnalysisEvaluation`，字段为：

```text
aspect_correct
sentiment_correct
issue_correct
scenario_correct
evidence_correct
hallucination
reviewer_notes
evaluated_at
```

## 检查方法

审核页面必须同时展示 Review ID、当前原文、父帖/主题上下文、记录类型、发布时间，以及每个 Aspect 的情感、问题分类、问题摘要、场景、当前证据、上下文证据和 confidence。

逐项判断：

1. `aspect_correct`：所有输出维度均有原文依据，且没有漏掉明确的第二个维度。
2. `sentiment_correct`：每个维度的方向正确；不同维度不能因为整条文本有正有负而统一标为 MIXED。
3. `issue_correct`：问题分类简短稳定，摘要忠于原文且没有臆测原因。
4. `scenario_correct`：场景来自当前文本或可追溯上下文；未出现时保持为空。
5. `evidence_correct`：当前证据逐字属于当前原文；上下文依赖时，证据逐字属于所引用父记录/主题且记录 ID 正确。
6. `hallucination`：模型增加了原文和上下文均未表达的事实、原因、版本、场景、严重程度或产品结论时标为 true。

“我也是”类回复可以借助父帖判断 Aspect，但必须满足：当前证据仍是“我也是”，`context_dependent=true`，上下文证据和 Review ID 完整，不能把父帖内容伪装成当前回复自己的表达。

## 执行门槛

第一轮真实 20 条必须全部人工检查，目标为：

```text
Schema 有效率 = 100%
Evidence 合法率 = 100%
数据库持久化成功率 = 100%
Aspect 正确率 >= 90%
Sentiment 正确率 >= 90%
Evidence 正确率 = 100%
严重幻觉 = 0
```

明显不达标时停止调用并新增 `review_analysis_v3`，不得覆盖 v2。通过后才可执行 100 条；第二轮从真实结果中按固定种子随机抽查 50 条，记录上述六个判断。只有第二轮仍达标，才允许处理剩余语料。

## 汇报

准确率分母必须是实际完成人工评估的记录数。分别汇报 Aspect、Sentiment、Issue、Scenario、Evidence 正确率和 hallucination count，不得把空评估、自动校验通过或模型 confidence 当作人工正确率。provider 未返回 token 时显示 `N/A`，不得估算。

固定 20 条 PoC 的 review ID 保存到 `docs/evaluation/phase5-poc-sample-v1.json`，不复制用户正文。真实运行完成后，可执行：

```bash
python manage.py export_analysis_review --batch-id <batch_id>
```

生成 `docs/evaluation/phase5-poc-review-v1.md` 的待审核内容。报告只允许正文、必要上下文和 AI 结果，不读取昵称或 `raw_data`。所有复核项默认保持未勾选，状态为 `NOT_EVALUATED`。管理页面使用 HTML 转义后再逐字高亮当前证据和上下文证据；若证据不在对应文本中，页面显示“证据校验失败”。
