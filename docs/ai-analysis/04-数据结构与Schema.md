# 数据结构与 Schema

## 数据库

- `AnalysisRun`：一次执行及其状态、模型版本、输入/配置指纹、Token、成本、耗时与安全错误。
- `StructuredAnalysis`：评论级情感、语言、内容类型、相关性、摘要、型号提及和复核状态。
- `OpinionAspect`：多观点、标签、情感、意图、严重度、场景、产品关系、证据及置信度。
- `AnalysisReviewRecord`：人工修改前后 JSON、复核人、原因和时间。

迁移 `0005`、`0006` 只新增表和字段，不删除或改写旧分析及原始反馈。

## Schema

`schemas/structured_analysis_v1.schema.json` 使用 Draft 2020-12、`additionalProperties=false` 和受控枚举。Pydantic 提供强类型校验；业务校验器负责标签父子关系、证据切片、目标产品声明和摘要 PII。无关内容允许空观点数组；`null`、`UNKNOWN` 和空数组语义独立。

