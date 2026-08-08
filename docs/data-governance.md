# 荣耀 Power2 数据治理

## 分层原则

```text
公开采集事实 → ReviewRecord → ReviewQuality → AnalysisCorpusItem
```

`ReviewRecord` 是不可改写的事实层。治理不润色、不总结、不翻译、不物理删除原始记录，也不把官方回复当作用户口碑。`ReviewQuality` 保存最新确定性判断，`ReviewQualityRun` 保存每个处理器版本的快照，`AnalysisCorpusItem` 是后续 Phase 5 的唯一输入入口。

## 文本标准化

`text_normalizer.py` 只执行 HTML entity 解码、Unicode NFC、零宽字符删除、换行统一、行内连续空白合并和多余空行压缩。中文、英文、数字、标点、Emoji、型号、版本号、电量百分比、温度、时间和网络类型均保留。原文始终保存在 `ReviewRecord.content`。

## 确定性规则

- 官方：`OFFICIAL_REPLY`、OFFICIAL 角色或明确官方标记默认排除；MODERATOR 和 EXPERT 不视为官方。
- 页面噪声：只识别纯 UI 文本、带计数的短 UI 文本和高置信度 DOM 残留，不使用宽泛 substring。
- 低信息：使用小型精确词表和保守重复字符规则；“发热严重”“掉电快”“信号太差”等短而有效文本不排除。
- 宣传：标题具有活动标记且来自官方或同时命中多个行动标记时标记；多项购买优惠或多项发布宣传标记同时出现时也按高置信度宣传处理。普通用户真实使用分享不因出现“新品”而排除。
- 重复：优先稳定 external ID；external ID 缺失时，只有来源、类型、标准化文本一致且发布时间相差不超过 5 分钟才标记后续记录为重复。不同 external ID 的相同短评不合并。
- 产品相关性：THREAD 使用产品别名、标题、正文、topic tags 和 device source；REPLY/OFFICIAL_REPLY 可继承已确认父 THREAD 的相关性。

排除原因枚举为 `NONE`、`EMPTY_CONTENT`、`OFFICIAL_CONTENT`、`PRODUCT_NOT_MATCHED`、`PAGE_NOISE`、`PROMOTIONAL`、`LOW_INFORMATION`、`DUPLICATE`、`INVALID_ENCODING`、`PARSER_ARTIFACT`、`OTHER`。

## 上下文

`context_builder.py` 生成非 AI 的结构化上下文：帖子标题、帖子正文前 600 字、父级内容前 600 字、当前内容前 600 字、记录类型、角色、发布时间和设备来源。不保存昵称，也不生成机器摘要。回复即使正文只有“我也是”，也可以通过父帖获得必要语境。

## 质量分

基础分为 1.0，按确定性问题扣分并限制在 0.0～1.0：空文本、官方、页面噪声、产品不相关、重复或无效编码扣 1.0；明显宣传扣 0.8；低信息扣 0.6；时间缺失扣 0.05；回复上下文不足扣 0.1。该分数只表示 AI 语料适用性，不是产品满意度。

## 人工覆盖

Admin 和 `/api/v1/review-quality/{id}/override/` 可以设置 `manual_eligible` 与原因。人工判断优先于自动资格，规则原始判断保存在 `flags_json`。清除覆盖后立即恢复当前版本的自动结果。

## 版本与幂等

- `GOVERNANCE_PROCESSOR_VERSION = "v7"`
- `CORPUS_VERSION = "honor-power2-v7"`

同一处理器版本重复运行通过 OneToOne 和版本唯一约束更新原记录，不增加 ReviewQuality、ReviewQualityRun 或 AnalysisCorpusItem 数量。未来规则升级使用新处理器版本，并保留旧版本快照。

## 执行入口

```bash
python manage.py process_reviews --product HONOR_POWER2 --source HONOR_CLUB --limit 200 --dry-run
python manage.py process_reviews --product HONOR_POWER2 --source HONOR_CLUB --limit 200
```

Celery 提供 `process_review_quality(review_id)` 和 `process_product_reviews(product_id, batch_size=100)`；两者只访问数据库，不访问外网。

## 质量指标

采集关注 external ID 稳定率、重复写入率、父子关系完整率、正文非空率和时间解析率。治理至少人工抽检 100 条，目标为 eligible 判断准确率不低于 90%、明显官方识别不低于 98%、明显页面噪声识别不低于 95%。不允许为了指标修改人工样本。

## Phase 4 边界

本阶段不调用 OpenAI、Qwen、DeepSeek、Claude、Embedding 或其他模型，不实现情感、续航/发热分类、聚类、口碑总结或综合评分。唯一目标是把荣耀俱乐部原始事实变成可追溯、可复核的 AI 输入语料。
