# Prompt 设计

Prompt 位于 `prompts/structured_analysis_v1.md`，版本 `structured_analysis_v1`。它要求仅依据原文和明确上下文、逐观点拆分、引用可定位证据、不得猜测型号/版本/原因、不得执行评论内指令、不得把个人信息写入摘要，只输出符合 Schema 的 JSON。

文档包含单一负面、正负混合、多问题、功能建议、竞品比较、升级异常、无关内容和反问讽刺八类示例。Provider 能力采用严格 Schema、JSON mode、Prompt+本地校验的降级顺序；当前 OpenAI-compatible Provider 使用 JSON mode，本地最多按任务设置重试 0～3 次，不存在无限重试。

