# AI 分析契约

## 输入

`ReviewAnalysisInput` 包含反馈 ID、产品型号、标题/正文、来源、记录类型、官方标记、可选评分和软件版本。输入在调用前应脱敏，官方回复和无效内容仍保留显式类型。

## 输出

`ReviewAnalysisOutput` 包含 `product_model`、`is_valid_content`、`content_type`、多项 `aspects`、软件版本、使用场景、摘要、总体置信度与 warnings。未知字段禁止，置信度限制在 0 到 1。

每个 `AspectAnalysisItem` 包含 aspect、sentiment、可选情感分、问题分类/摘要、原文证据和置信度。

## 15 个一级维度

BATTERY、CHARGING、HEATING、SIGNAL、PERFORMANCE、SYSTEM_FLUENCY、SYSTEM_BUG、DISPLAY、CAMERA、WEIGHT_AND_FEEL、BUILD_QUALITY、AUDIO_AND_CALL、DURABILITY、VALUE_FOR_MONEY、AFTER_SALES。

## 情感

POSITIVE、NEUTRAL、NEGATIVE、MIXED。`sentiment_score` 只作为模型结构字段，范围 -1 到 1；Phase 1 不定义汇总评分公式。

## 证据要求与幻觉控制

- 只能依据单条输入分析，不用产品常识补齐事实。
- `evidence_text` 必须直接、连续来自原始正文。
- 每个方面至少一段证据；无证据则不输出该方面。
- 信息不足时降低置信度并写 warning。
- Schema 校验失败、证据不在原文或型号冲突时结果不得入正式统计。

## Prompt 与模型版本

Prompt 文件名含版本（如 `review_analysis_v1.md`），修改语义必须升版本。每个结果保存 `model_name/model_version/prompt_version`，同版本可重复重放和对比；不能用“latest”替代持久化版本。

## 物流与官方回复

物流、包装、客服等内容标记为 `LOGISTICS_OR_SERVICE`，不得映射为手机硬件维度。官方回复标记为 `OFFICIAL_REPLY`，可用于问题处理分析，但不得计入用户口碑。

## 人工评估

后续建立分层抽样集，双人标注有效性、维度、情感和证据；监控维度准确率、证据一致率、幻觉率、官方/物流误判率及模型版本漂移。低置信和冲突结果进入人工复核。

## 示例

```json
{
  "product_model": "荣耀 Power2",
  "is_valid_content": true,
  "content_type": "USER_REVIEW",
  "aspects": [
    {
      "aspect": "BATTERY",
      "sentiment": "POSITIVE",
      "sentiment_score": 0.8,
      "issue_category": "",
      "issue_summary": "用户认可日常续航",
      "evidence_text": "续航能用一整天",
      "confidence": 0.9
    }
  ],
  "software_version": null,
  "usage_scenarios": ["日常使用"],
  "summary": "用户认可日常续航表现。",
  "confidence": 0.9,
  "warnings": []
}
```

完整机器可读示例位于 `ai/schemas/examples/review_analysis_output.json`。
