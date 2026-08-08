# 采集器契约

## 统一接口

`BaseCollector` 定义：

- `validate_target(CollectorTarget) -> ValidationResult`
- `fetch_page(CollectionRequest) -> RawPage`
- `parse_records(RawPage) -> list[RawRecord]`
- `normalize_record(RawRecord) -> NormalizedReview`

输入输出以及 `CollectionCheckpoint`、`CollectorError` 位于 `collectors/base/contracts.py`。未实现或未现场验证的能力必须显式抛出 `CollectorError`，不能返回空成功或虚假记录。

## 分页与增量

分页游标、页码和来源元数据只放在 checkpoint；每页成功持久化后再推进 checkpoint。荣耀 INCREMENTAL 固定从主题第 1 页开始，对已知帖子仍读取详情以发现新回复；连续 20 个已知 thread ID 后停止。第 1 页构成重叠窗口，不完全依赖发布时间。

## 重试与错误分类

错误至少区分配置错误、未实现、临时网络、限流、响应格式变化、权限/合规阻断和持久化失败。只有明确临时错误可退避重试；格式、权限和合规错误停止任务并等待人工处理。重试次数、间隔与最终失败必须记录。

## 限速

每个来源独立设置保守速率和最大并发；收到限流或服务异常立即停止或退避。不得以吞吐量为目标压测第三方网站。荣耀俱乐部 PoC 固定单并发，请求间隔不低于 3 秒。

## 合规边界

仅处理公开、允许访问且满足平台条款的数据。在实现前记录规则核查结果、联系/授权、保留周期和删除流程。

明确禁止：

- 破解验证码、绕过登录或访问权限；
- 偷取 Cookie、Token 或浏览器会话；
- 未授权账号共享；
- 用代理池、设备指纹伪装等方式规避平台限制；
- 高频、攻击式、破坏性访问；
- 在日志或仓库保存账号秘密。

## 荣耀俱乐部 Phase 2 实现

`HONOR_CLUB` 只允许 `https://club.honor.com/cn/threadtopic-*.html` 与 `https://club.honor.com/cn/thread-*.html`，拒绝凭据、端口、查询参数、片段、IP、localhost 和外部域名，避免把数据库目标配置变成 SSRF 入口。

客户端使用固定、诚实的 User-Agent，不保存 Cookie，15 秒超时，单并发且两次请求至少间隔 3 秒。遇到 403、429、5xx、非 HTML、异常跳转、验证码或登录墙时抛出 `CollectorError` 并停止，不尝试绕过。

稳定标识与关系：

- 主题：`thread:{thread_id}`，父记录为空；
- 楼层：`honor_post:{pid}`，父记录为主题；
- 内嵌评论：优先 `honor_comment:{comment_id}`，父记录为楼层；无法可靠定位时使用稳定哈希并显式记录父级回退；
- 官方回复使用 `OFFICIAL_REPLY`，版主和达人仍为普通 `REPLY`，且 `is_official=false`。

持久化使用 `source + external_id + record_type` 数据库唯一约束和稳定 SHA256 内容哈希。每完成一个帖子即更新任务与运行 checkpoint。完整细节见 [荣耀俱乐部 PoC](honor-club-poc.md)。

Phase 4 第一阶段配置最多 5 个主题页/100 个帖子；确认 HTTP 错误率低于 5%、无验证码或登录墙且解析正常后，才允许调整到最多 10 页/200 帖。单任务硬上限始终为 10 页/200 帖，继续保持单并发和至少 3 秒请求间隔。

2026-08-08 第一阶段和第二阶段均成功且失败数为 0，最终配置已调整为 10 页/200 帖。来源页面实际每页约 10 个主题，10 页扫描到 97 个符合条件的唯一主题；未为追求目标数字突破页数或限速。随后真实 INCREMENTAL 任务扫描 20 个连续已知主题后按边界停止，新增记录为 0。

## 京东 Phase 3 实现状态

京东 collector 已实现严格商品 URL 校验、固定身份与 4 秒限速、禁止重定向、JSON/JSONP 安全解析、评价/追评标准化、SKU 属性契约、逐页 checkpoint、去重和隐私 allowlist。`jd_poc` 强制最多 3 页/30 条主评价。

2026-08-08 正常浏览被重定向到登录页并触发访问频繁限制，因此商品/店铺/评论接口门禁未通过。Phase 3 状态为 `POSTPONED`；已验证 endpoint、host 与字段映射保持为空，SourceTarget 保持停用，真实调用失败关闭。这是外部数据访问限制，不是系统缺陷。详情见 [京东 PoC](jd-poc.md)。
