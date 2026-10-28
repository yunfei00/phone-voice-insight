# API 说明

所有接口沿用现有认证和权限机制。

- `GET /api/v1/taxonomies/`：标签树。
- `GET /api/v1/structured-runs/`：运行记录，可按状态、Provider、模型、内容、批次和当前版本过滤。
- `GET /api/v1/structured-analyses/`：结果分页；支持搜索及 product、source、aspect_code、topic_code、sentiment、review_required。
- `POST /api/v1/structured-analyses/{id}/review/`：提交完整校正结果和原因；服务端重新校验并保存前后版本。
- `GET /api/v1/structured-analyses/quality/`：成功率、Schema 合法率、待复核数及人工评测状态。
- `GET /api/v1/structured-analyses/aggregates/`：评论数、观点数、域/主题/情感/严重度、需求、竞品及可解释异常候选。
- `GET|POST /api/v1/structured-batches/`：分页查看或创建批任务。支持内容 ID、时间、机型、来源、上限、dry-run、并发/RPM、Token/预算和重试限制。
- `POST /api/v1/structured-batches/{id}/pause|cancel/`：阻止后续内容启动。

异常规则 V1：最近 7 天至少 5 条，且达到之前 28 天周均两倍。返回值明确声明论坛反馈占比不是设备故障率。

