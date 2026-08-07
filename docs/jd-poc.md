# 京东评价采集 PoC

## 1. 目标与边界

- 产品候选：荣耀 Power2
- 京东商品 ID：`100310496358`
- 期望店铺：荣耀京东自营旗舰店
- 商品页：`https://item.jd.com/100310496358.html`
- 数据语义：采集时公开可见评价样本，不代表全部订单、全部用户或全部历史评价
- 第一阶段硬限制：最多 3 页、每页最多 10 条、最多 30 条主评价、单并发、请求间隔至少 4 秒

不登录、不读取或发送登录 Cookie、不处理验证码、不模拟滑块、不使用 Token/代理/多账号/指纹伪装，不逆向签名或私有 API。403、429、登录墙、验证码、异常跳转或连续服务错误均立即停止。

## 2. 2026-08-08 当前页面探测

两次低频、固定 User-Agent、无 Cookie 的普通 HTTPS 请求用于确认响应和动态配置，结果一致：

- HTTP 200；无 Location；`Content-Type: text/html; charset=utf-8`；约 35 KB；
- canonical 与移动端 meta 指向商品 ID `100310496358`；
- HTML 是动态渲染外壳，标题为京东通用标题；未出现 Power2、HONOR、目标店铺或评论 endpoint；
- HTML 引用了 `api.m.jd.com` 与公开静态组件，但没有足以确认商品、店铺、评论 host/path 或参数的内联配置；
- 响应中未出现验证码或访问受限文案。

随后只进行一次正常浏览器导航。页面被重定向到 `passport.jd.com/new/login.aspx?...`，可见标题为“京东-欢迎登录”。此时命中登录墙停止条件，关闭页面并停止全部京东真实访问。

因此本次不能确认该 ID 当前仍展示为荣耀 Power2，也不能确认店铺仍为荣耀京东自营旗舰店。候选历史接口 `club.jd.com` / `sclub.jd.com/comment/productPageComments.action` 未被请求，也没有被写入代码。

## 3. 当前评论加载方式与接口结构

本次未获得真实评论请求或响应，以下项目均为“未验证”，不能猜测：

- 评论 host、path 与 HTTP method；
- 必需/可选参数、分页起始值、pageSize、排序和分类参数；
- JSON 或 JSONP 实际格式；
- 评论 ID、评分、SKU、时间、追评和媒体的真实字段名；
- 默认排序或最新排序语义；
- 是否允许匿名、是否需要 Cookie。

`collectors/jd/constants.py` 中的 `VERIFIED_COMMENT_ENDPOINT`、`VERIFIED_COMMENT_HOSTS` 和 `VERIFIED_COMMENT_FIELD_MAP` 故意为空。真实执行会失败关闭，不会降级使用历史接口。

## 4. 已实现代码契约

已实现以下可离线验证的安全框架：

- 仅允许 `https://item.jd.com/{纯数字}.html`，拒绝 IP、localhost、userinfo、非 HTTPS、外部域名、自定义端口、query/fragment 和商品 ID 不一致；
- 固定 User-Agent、15 秒超时、单并发、至少 4 秒间隔，不保存 Cookie，禁止跟随重定向；
- 严格 JSON/JSONP 解析，只验证 callback 包装并调用 `json.loads`，不使用 `eval/exec`；
- endpoint 或字段映射未验证时抛出 `ENDPOINT_NOT_VERIFIED` / `RESPONSE_SCHEMA_NOT_VERIFIED`；
- `NormalizedReview` 支持 rating、来源 SKU ID 与版本属性；
- `SourceProductVariant` 用 `source + external_id` 唯一约束保存来源 SKU 映射；
- 持久化优先按来源 SKU 映射，其次只在 memory+storage+color 三项完整且唯一时匹配 ProductVariant，否则保留 NULL；
- 主评使用 `jd_review:{comment_id}`；单一且无独立 ID 的追评可使用 `jd_append:{comment_id}`；多追评缺少稳定 ID 时停止；
- 评分只接受真实数值且要求 0～5，越界或无法解析时留空并记录 warning；
- HTML 标签、控制字符和多余空白被清理，Emoji、标点、换行语义、数字和英文保留；
- 图片/视频不下载、不保存 URL，只保存存在性与数量。

脱敏 fixtures 使用显式注入的字段映射测试上述契约，但它们是合成的解析样本，不宣称来自本次京东真实响应。

## 5. SKU 与 ProductVariant

Phase 1 已有两个颜色为空的通用版本：12GB+256GB、12GB+512GB。本次页面未能现场确认旭日橙、幻夜黑、雪原白及其六种容量组合，所以没有创建六个颜色版本，也没有创建任何 JD `SourceProductVariant` 映射。

迁移幂等创建名为“荣耀Power2京东自营”的 SourceTarget，配置 4 秒间隔、3 页、每页 10 条，但 `is_active=false`。只有后续重新验证商品、店铺、评论 endpoint、字段结构和实际 SKU 组合后才能启用。

## 6. 分页、checkpoint 与去重

JD strategy 已支持逐页处理和每页更新 checkpoint：

```json
{
  "page": 1,
  "page_size": 10,
  "last_comment_id": "verified-comment-id",
  "sort_mode": "CURRENT_PAGE_DEFAULT"
}
```

动态排序导致跨页重复时，依靠 `source + external_id + record_type` 跳过，重复不算失败。若明确到达末页可正常结束；应有数据却突然返回空时抛出 `POSSIBLE_BLOCK_OR_FORMAT_CHANGE`。

## 7. 隐私最小化

京东 raw_data 仅允许评论/SKU 标识、颜色/规格/参考名称、点赞/回复数量、媒体数量、原始时间、是否有可分析文本和解析 warning。不保存昵称、用户 ID、GUID、头像、主页、地区、设备唯一标识、订单、手机号、地址、Cookie、Token 或 IP，也不把完整原始 response 直接写入数据库。

## 8. 命令与在线 smoke test

入口复验并人工启用 SourceTarget 后，受限命令为：

```powershell
python manage.py jd_poc --target-id <id> --pages 1 --limit 10 --dry-run
python manage.py jd_poc --target-id <id> --pages 1 --limit 10
```

命令强制 `pages<=3`、`limit<=30`。`RUN_JD_LIVE_TESTS=1` 默认关闭；即使显式开启，在 endpoint/字段映射为空时也会 skip。CI 不访问京东。

## 9. PoC 实际结果

真实采集序列未执行，原因是正常浏览器访问出现登录墙。真实统计为：商品页普通 HTTP 请求 2 次、正常浏览器导航 1 次（合计 3 次商品页访问尝试）、评论页请求 0、扫描评论 0、新增 REVIEW 0、新增 APPEND_REVIEW 0、映射版本 0、跳过 0、失败写入任务 0。没有数据库真实评价可供随机 10 条抽查。

离线 fixture/集成测试不能计入真实 PoC 数字。后续复测必须从“一页 dry-run → 一页写入 → 相同任务去重 → 三页/30 条”重新开始，完成后立即停止扩大。

## 10. 已知问题

- 当前网络/会话下正常页面要求登录，商品与店铺身份未通过门禁；
- 当前评论 endpoint、参数、分页、排序和字段结构完全未验证；
- 未创建现场 SKU 映射，variant_mapping_rate 无真实分母；
- 未执行真实写入、重复运行、3 页扩展与随机抽查；
- 数据质量率无法在 0 条真实记录上定义，报告为 N/A，而不是 0%。
