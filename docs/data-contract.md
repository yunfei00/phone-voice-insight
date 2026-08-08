# 数据契约

## 通用约定

- 数据库主键使用 Django `BigAutoField`，领域外部标识单独保存。
- 所有业务时间用带时区 `datetime`，API 编码为 ISO 8601，例如 `2026-07-30T15:00:00Z`。
- 文本与 JSON 使用 UTF-8；外部原始编码应在采集边界转换并记录异常。
- 带时间戳模型包含 `created_at`、`updated_at`。

## Product

`brand`、`name`、唯一 `normalized_name`、`series`、可空业务信息 `model_code/release_date/description`、`is_active`。别名由 ProductAlias 保存，版本由 ProductVariant 保存。

初始化值：荣耀（HONOR）、荣耀 Power2（HONOR_POWER2，Power 系列）、5 个指定别名、12GB+256GB 和 12GB+512GB；未知颜色保持空，不编造。

## SourceTarget / SourceProductVariant

SourceTarget 字段：`source`、`product`、`name`、`target_type`、可空 `target_url/external_id`、`config_json`、`is_active`。`target_type` 为 PRODUCT 或 COMMUNITY。

SourceProductVariant 保存商城来源 SKU 到通用 ProductVariant 的映射：`source`、`product`、`product_variant`、`external_id`、可空 `source_target`、`attributes_json`、`is_active`，并约束 `source + external_id` 唯一。商城 SKU 字段不写进 ProductVariant。

## CollectionTask / CollectionRun

任务包含入口、任务类型、状态、请求上限、开始/结束时间、checkpoint、成功/跳过/失败计数和错误信息。增量统计额外保存 `new_threads`、`known_threads`、`new_records`、`duplicate_records` 和 `stopped_at_known_boundary`。任务类型为 FULL 或 INCREMENTAL；状态为 PENDING、RUNNING、PAUSED、SUCCESS、FAILED、CANCELLED。

每次尝试创建一个递增 `run_number` 的 CollectionRun，保存独立 checkpoint 和计数。非法状态转换必须拒绝。

## ReviewRecord

字段覆盖来源/入口/产品/版本、外部与父外部 ID、类型、标题/正文、评分、发布时间、软件版本、作者角色、官方/追评标记、来源 URL、SHA-256 内容指纹、原始 JSON、处理状态与采集时间。

`record_type`：REVIEW、APPEND_REVIEW、THREAD、REPLY、OFFICIAL_REPLY。`author_role`：USER、OFFICIAL、MODERATOR、EXPERT、UNKNOWN。`status`：RAW、NORMALIZED、INVALID。

NormalizedReview 额外携带可空 `rating`、`variant_external_id` 和 `variant_attributes`。通用持久化层先解析 ProductVariant，再同时写入 rating/product_variant；荣耀数据默认保持两者为空。

### 去重策略

非空外部 ID 优先使用数据库条件唯一约束：

```text
source + external_id + record_type
```

外部 ID 缺失时，业务层以规范化正文、父记录、产品、来源和发布时间形成 `content_hash` 辅助匹配；必须允许人工复核，不能只凭短文本哈希永久丢弃记录。

## ReviewQuality / ReviewQualityRun

`ReviewQuality` 与 ReviewRecord 一对一，只保存最新治理状态：标准化文本、有效文本、产品相关性、官方/低信息/页面噪声/宣传/重复标记、重复来源、AI 资格、排除原因、质量分、规则标记、处理器版本和人工覆盖。它不得改写 `ReviewRecord.content`。

`ReviewQualityRun` 以 `review + processor_version` 唯一保存版本快照。同一版本重复执行更新同一快照，不增加记录；规则升级后使用新版本，旧结果仍可追踪。

## AnalysisCorpusItem

与 ReviewRecord 和 ReviewQuality 一对一，保存产品、来源、类型、角色、标准化文本、结构化上下文、最终资格、排除原因、质量分和 `corpus_version`。Phase 5 只能查询 `eligible=true` 的指定语料版本。

`quality_score` 范围为 0.0～1.0，仅表示文本作为分析材料的适用性，不代表满意度或手机评分。

## AnalysisResult

关联 ReviewRecord，保存状态、`model_name/model_version/prompt_version`、有效内容标记、置信度、摘要、原始结构结果与分析时间。同一反馈/模型/模型版本/Prompt 版本唯一。

## AspectResult

关联 AnalysisResult，保存一级维度、情感、情感分、问题分类/摘要、使用场景、原文证据和置信度。

一级维度：BATTERY、CHARGING、HEATING、SIGNAL、PERFORMANCE、SYSTEM_FLUENCY、SYSTEM_BUG、DISPLAY、CAMERA、WEIGHT_AND_FEEL、BUILD_QUALITY、AUDIO_AND_CALL、DURABILITY、VALUE_FOR_MONEY、AFTER_SALES。

情感值：POSITIVE、NEUTRAL、NEGATIVE、MIXED。当前不定义评分公式。

## 原始数据保留

`raw_data` 保存可审计的来源 allowlist 字段，但不得复制完整商城响应或保存无关用户资料。原始与标准化记录分层，后续 Schema 升级可重放；保留期限、访问权限与删除流程应在正式采集前确定。

## 隐私脱敏

只采集分析所需公开内容。展示、导出与模型输入前删除或散列手机号、邮箱、地址、订单号、Cookie、Token、设备唯一标识和非必要昵称。日志禁止记录凭据与完整个人敏感信息。
