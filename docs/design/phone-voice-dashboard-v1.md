# 手机用户声音智能洞察驾驶舱 V1.0 设计说明

## 1. 产品定位

`PHONE VOICE INTELLIGENCE · V1.0` 面向领导、业务分析人员和平台管理员。默认首页在 10 秒内给出真实数据覆盖、有效反馈、AI 分析覆盖和明确问题概况；所有问题均可追溯到结构化证据及原始记录。

当前项目阶段统一配置为 `Phase 6 · 智能洞察驾驶舱`，配置文件为 `frontend/src/config/project.ts`。

## 2. 页面架构

| 页面 | 路由 | 主要能力 |
| --- | --- | --- |
| 领导智能驾驶舱 | `/phone/dashboard` | 六项指标、趋势、类别排行、产品概况、重点观察、五分钟刷新、投屏模式 |
| 产品对比中心 | `/phone/comparison` | 任意两款产品、同口径对比、数量/占比切换、样本可信度提示 |
| 用户问题洞察 | `/phone/issues` | 后端分页、筛选排序、问题证据抽屉、原帖追溯 |
| AI 智能洞察报告 | `/phone/insight-reports` | 每日/最近七日报告、产品筛选、历史报告、复制摘要 |
| 数据运行监控 | `/phone/operations` | 采集、治理、AI、预算、数据库、Redis、Worker、Beat 分层状态 |

原有帖子视图、原始反馈、数据治理、AI 配置等页面均保留。

## 3. 统一设计系统

主题变量集中在 `frontend/src/assets/main.css`：

- 主背景 `#071524`
- 次级背景 `#0A192A`
- 卡片背景 `#12283F`
- 卡片边框 `#29435C`
- 科技蓝 `#35B9F0`
- 青绿色 `#42D6C6`
- 预警橙 `#F1AD61`
- 异常红 `#E36F79`
- 主文字 `#EDF5FF`
- 次级文字 `#96ADC6`

图表基于 ECharts 按需模块；组件提供加载、空数据、错误容器、自适应 resize 和销毁处理，并遵循 `prefers-reduced-motion`。投屏模式优先使用浏览器 Fullscreen API；不支持或拒绝时回退为页面级投屏布局，仍可进入和退出，隐藏侧栏与普通顶栏，不要求 F11。

## 4. 统计口径

### 4.1 时间

默认最近 30 天。主时间使用 `published_at`；缺失时回退 `collected_at`，回退数量在总览 API 中明确返回。URL 保存 `product_id/source_id/start_date/end_date`，自定义日期刷新后仍正确显示为“自定义”。

### 4.2 有效反馈

`ReviewQuality.eligible_for_ai=true` 且 `is_official_content=false`，按 `ReviewRecord` 去重。

### 4.3 AI 已分析

同时满足：

1. 治理结果为 `ACCEPTED`；
2. 当前 `AnalysisRun` 为 `SUCCEEDED/REVIEW_REQUIRED`；
3. `StructuredAnalysis.schema_valid=true`；
4. 结构化结果不要求人工复核；
5. 非官方内容。

`REJECTED/UNCERTAIN/ERROR/未分析` 不进入明确问题统计。

### 4.4 明确问题

仅统计 `OpinionAspect.sentiment=NEGATIVE`，同一反馈同一聚合维度去重。若模型明确给出 `target_product`，只有其标准化名称与内容所属产品一致时才归入该产品；比较文本中针对其他产品的负面证据不会误归因。

### 4.5 负面占比与可信度

负面占比 = 明确负面独立反馈数 / 已完成分析的有效独立反馈数。默认比较最小样本为 30，可通过环境变量调整。该比例不是设备真实故障率。

### 4.6 重点观察

默认当前周期至少 5 条独立明确问题反馈，且比上一等长周期增长至少 50%。上一周期为零时显示“新出现”，不会显示无穷大增长；仍必须满足最小样本量。

## 5. 后端 API

统一前缀 `/api/v1/dashboard/`：

- `GET overview/`
- `GET trends/`
- `GET categories/`
- `GET products/`
- `GET comparison/`
- `GET issues/`
- `GET issues/{product_id}:{topic_code}/`
- `GET reports/`
- `GET reports/{id}/`
- `GET operations/`

通用参数为 `product_id/source_id/start_date/end_date`；问题接口额外支持 `category/topic/severity/search/ordering/page/page_size`；对比接口使用 `left_product_id/right_product_id`。

产品概况采用按产品批量聚合，查询数量不随产品数量线性增长。问题列表只返回聚合行，证据在详情接口按需读取。现有约一万条数据规模的生产实测 P95 均低于 1 秒。

## 6. 自动报告

`AggregateReport` 支持全产品或单产品、日报和周报、数据截止时间及生成状态。Celery Beat 每日 01:10 生成日报、每周一 01:20 生成周报。生成过程为数据库聚合加确定性模板，不调用付费模型；同一产品、类型和时间范围通过数据库约束幂等更新。

## 7. 权限与安全

- 驾驶舱只读接口要求登录。
- 运行监控：管理员返回完整采集/治理/AI 细节，其他角色只返回脱敏摘要。
- 采集任务、结构化批次、AI 配置与连通性检查限制为分析员或管理员；低层采集控制限制为管理员。
- API 不返回密钥、密文或敏感环境变量。
- 前端隐藏菜单不是权限边界，后端权限为最终边界。

## 8. AI 自动化

采集→治理→AI 决策→结构化分析的任务链保留幂等、每日 Token 上限、批量上限、并发、有限重试和超时控制。Dashboard 请求与报告生成均不会触发付费 AI。

生产当前保持 `AI_AUTOMATION_ENABLED=false`。这是付费调用安全门禁，不代表结构化能力不可用；手工有界真实验收已通过。

## 9. 已知限制

- 当前只有 1 条通过真实结构化闭环的样本，且发布时间为 2026-04-15；默认最近 30 天不显示 AI 问题数据，这是数据覆盖事实而非页面故障。
- ECharts 和 Element Plus 生产 chunk 仍有大于 500KB 的构建警告，功能与性能验收不受影响，后续可继续细分 vendor chunk。
- V1.0 不提供 PDF/PPT 导出、综合质量评分、故障率声明、向量库或知识图谱。
