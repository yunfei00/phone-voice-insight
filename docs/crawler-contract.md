# 采集器契约

## 统一接口

`BaseCollector` 定义：

- `validate_target(CollectorTarget) -> ValidationResult`
- `fetch_page(CollectionRequest) -> RawPage`
- `parse_records(RawPage) -> list[RawRecord]`
- `normalize_record(RawRecord) -> NormalizedReview`

输入输出以及 `CollectionCheckpoint`、`CollectorError` 位于 `collectors/base/contracts.py`。未实现方法必须抛出 `CollectorError(code="NOT_IMPLEMENTED")`，不能返回空成功或虚假记录。

## 分页与增量

分页游标、页码和来源元数据只放在 checkpoint；每页成功持久化后再推进 checkpoint。增量策略优先使用平台稳定外部 ID/发布时间，遇到已知边界可停止，但需保留重叠窗口以应对排序变化。

## 重试与错误分类

错误至少区分配置错误、未实现、临时网络、限流、响应格式变化、权限/合规阻断和持久化失败。只有明确临时错误可退避重试；格式、权限和合规错误停止任务并等待人工处理。重试次数、间隔与最终失败必须记录。

## 限速

每个来源独立设置保守速率、随机小幅抖动和最大并发；收到限流或服务异常立即退避。不得以吞吐量为目标压测第三方网站。

## 合规边界

仅处理公开、允许访问且满足平台条款的数据。在实现前记录规则核查结果、联系/授权、保留周期和删除流程。

明确禁止：

- 破解验证码、绕过登录或访问权限；
- 偷取 Cookie、Token 或浏览器会话；
- 未授权账号共享；
- 用代理池、设备指纹伪装等方式规避平台限制；
- 高频、攻击式、破坏性访问；
- 在日志或仓库保存账号秘密。

## 荣耀俱乐部 Phase 2 计划

先确认公开帖子/回复边界与页面/API 稳定性，选择单个经审核入口完成低频分页 PoC；实现帖子/回复父子关系、官方回复识别、checkpoint、原始响应样本脱敏和契约测试。PoC 达标后再评估规模化。

## 京东 Phase 3 计划

确认商品评价公开访问与使用规则，录入真实自营商品入口，完成低频评价/追评分页、SKU 映射、外部 ID 去重、checkpoint 和脱敏样本测试。任何验证码、签名或权限阻断都视为停止条件，不实现绕过。
