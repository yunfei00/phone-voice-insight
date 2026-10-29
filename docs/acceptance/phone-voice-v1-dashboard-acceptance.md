# 手机用户声音智能洞察平台 V1.0 驾驶舱验收报告

## 1. 交付信息

- 验收日期：2026-10-29（Asia/Shanghai）
- 开发基线：`650a670`
- 实现提交：`c6fb3a94799530616038c427320860c7a3dae4aa`
- 开发分支：`feat/phone-voice-v1-dashboard`
- 生产验证地址：`http://106.52.122.214/phone/`
- PR：`https://github.com/yunfei00/phone-voice-insight/pull/5`；保持未合并

## 2. 功能验收

| 模块 | 实际访问入口 | 结果 |
| --- | --- | --- |
| 领导智能驾驶舱 | `http://106.52.122.214/phone/dashboard` | PASS |
| 产品对比中心 | `http://106.52.122.214/phone/comparison` | PASS |
| 用户问题洞察 | `http://106.52.122.214/phone/issues` | PASS |
| AI 智能洞察报告 | `http://106.52.122.214/phone/insight-reports` | PASS |
| 数据运行监控 | `http://106.52.122.214/phone/operations` | PASS |

以上页面均在已登录生产浏览器中进行真实截图验收，不是设计稿。验收画面确认了深色主题、真实指标、样本不足提示、报告历史、Token 预算和五项服务健康状态。修复目标产品误归因后，生产问题页按真实口径显示空状态；证据抽屉由 API 追溯测试和前端组件测试验证。任务交付记录中附有实机截图；仓库文档保留可复验入口，避免提交含登录态的浏览器文件。

全屏投屏优先使用浏览器 Fullscreen API；浏览器拒绝或不提供该 API 时仍进入隐藏侧栏和普通顶栏的投屏布局，并可可靠退出。投屏保留产品和时间筛选。390×844 实际视口测得 `innerWidth=390`、根内容宽 375，无横向溢出；桌面布局、窄屏 CSS、全屏状态同步和路由守卫均有自动测试覆盖。

## 3. 生产真实数据

默认最近 30 天、全部产品和来源：

- 原始反馈：146
- 有效反馈：31
- AI 已分析：0
- 明确问题：0
- 最新数据：2026-10-28 15:00（页面本地时区）

AI 数量为 0 的原因是本轮唯一通过真实结构化闭环的样本发布时间为 2026-04-15，不属于默认窗口。自定义日期可读取该结构化结果；但真实模型指出的唯一负面维度针对“荣耀 X70”，不是 Power2，本轮修复后不会错误计入 Power2 排行。

确定性报告已生成：日报 3 份、周报 3 份（全部产品、荣耀 Power、荣耀 Power2），状态均为 READY。

## 4. 第三阶段 AI 闭环复验

本轮真实付费请求上限为 3，实际使用 2 次，没有使用第 3 次：

| 请求 | 结果 | 输入 Token | 输出 Token | 合计 |
| --- | --- | ---: | ---: | ---: |
| 1 | HTTP 200，但 taxonomy 父子关系校验失败 | 3000 | 2320 | 5320 |
| 2 | SUCCESS，Schema 和证据校验通过并入库 | 3000 | 2331 | 5331 |

第 2 次验证结果：

- `StructuredAnalysis.schema_valid=true`
- `review_required=false`
- 13 个结构化维度全部入库
- 13 个 `topic_code/aspect_code` 父子关系全部正确
- 13 个证据起止偏移全部逐字匹配原始内容
- 前端结构化结果 API 可读取
- 失败批次和错误原因保留，未伪装为成功

修复采用确定性 taxonomy `topic -> parent aspect` 标准化，不改变模型证据，不通过无限重试消耗 Token。

### 自动化状态

生产 `AI_AUTOMATION_ENABLED=false`，未自行开启。虽然系统已配置每日 100,000 Token 技术硬上限、批量上限、并发、超时和有限重试，但用户尚未明确批准生产环境持续付费额度，因此保持安全关闭。监控页明确显示“自动分析未启用”；关闭状态不会产生新的自动付费调用。

## 5. 数据真实性修复

真实页面验收发现模型在 Power2 帖子中比较 X70，并对 X70 给出负面判断。原聚合会按帖子产品误归 Power2。本次增加目标产品一致性过滤：

- `target_product` 为空时按内容产品处理；
- 明确给出目标产品时，去空格、大小写标准化后必须与内容产品一致；
- 比较对象的负面信息不进入当前产品问题排行。

另修复：

- 自定义 URL 日期正确回显“自定义”；
- 缺失发布时间的近期统计统一回退采集时间；
- 产品概况改为固定批量聚合，避免按产品 N+1；
- 运行监控字段与状态全部中文化；
- 项目阶段统一更新为 `Phase 6 · 智能洞察驾驶舱`。

## 6. 自动化测试

后端：

- Ruff check：PASS
- Ruff format check：PASS（164 files）
- Mypy：PASS（212 source files）
- Django system check：PASS
- Migration check：PASS，No changes detected
- Pytest：316 passed，2 skipped
- 跳过项均为需显式启用的外部站点 live 测试

前端：

- ESLint + Prettier：PASS
- TypeScript：PASS
- Vitest：7 files，23 tests passed
- Production build：PASS
- 已知非阻塞警告：ECharts/Element Plus chunk 大于 500KB

## 7. 性能测量

生产容器、真实数据库、每个接口 10 次测量：

| API | P50 | P95 |
| --- | ---: | ---: |
| 总览 | 57.60ms | 64.95ms |
| 产品概况 | 41.54ms | 50.80ms |
| 产品对比 | 148.73ms | 163.11ms |
| 问题列表 | 12.87ms | 13.59ms |
| 运行监控 | 229.22ms | 325.79ms |

全部低于 P95 1 秒目标。运行监控包含 Celery Worker 实时广播探测。

## 8. Docker 与部署验收

部署使用 `docker-compose.prod.yml`，迁移 `reports.0002` 已应用。最终状态：

- backend：healthy
- frontend：healthy
- postgres：healthy
- redis：healthy
- celery-worker：healthy，ping/pong 正常
- celery-beat：healthy，心跳在线
- `/phone/healthz`：200
- `/phone/api/v1/health/`：database=ok，redis=ok
- `/phone/`：200

部署前数据库和环境备份已完成，路径见升级文档。未删除、重建或伪造生产数据。

## 9. 权限验收

- 未登录 Dashboard 被拒绝；
- 普通查看者只能看到脱敏运行摘要；
- 查看者直接访问采集任务、AI 配置、结构化批次返回 403；
- 管理员可查看完整运行监控；
- API/页面不返回 API Key 或环境敏感值。

## 10. 已知限制与最终结论

已知限制：

1. 最近 30 天没有通过真实结构化校验的样本，因此默认窗口的问题图表为空；系统不会用旧样本或未分析数据填充数字。
2. 生产付费 AI 自动化按安全要求保持关闭，完整无人值守的付费分析链尚未启用。
3. 构建存在大 chunk 警告，但实测接口和页面运行正常。

结论：驾驶舱 V1.0 的代码、真实数据统计、页面、报告、监控、权限、测试、性能和生产部署验收通过。第三阶段真实结构化闭环通过；付费自动化开关因缺少持续预算授权而有意保持关闭。若“正式交付”要求生产自动付费分析必须开启，则该单项仍受预算授权阻塞；除此之外达到 V1.0 可交付状态。

## 11. PR 与 CI

PR #5 已创建并保持未合并。实现提交 `c6fb3a9` 对应的 GitHub Actions
运行 [40800504178](https://github.com/yunfei00/phone-voice-insight/actions/runs/40800504178)
已完成：

- backend：PASS（35 秒）；
- frontend：PASS（35 秒）。

交付文档提交后的最终 PR 检查仍作为交付门禁，必须保持全绿，且不自动合并。
