# 京东公开评价 PoC 采集器

本目录实现京东商品入口校验、单并发限速客户端、JSON/JSONP 安全解析、评论标准化、SKU 属性映射和脱敏数据契约。

2026-08-08 探测时，`item.jd.com/100310496358.html` 的普通 HTTP 请求返回动态页面外壳，但正常浏览器随后被重定向到京东登录页。因此：

- 未确认商品标题、品牌和“荣耀京东自营旗舰店”三项身份信号；
- 未确认当前评论 host/path、参数、分页起始值和字段名；
- `VERIFIED_COMMENT_ENDPOINT` 与 `VERIFIED_COMMENT_FIELD_MAP` 故意为空；
- 真实请求会以 `ENDPOINT_NOT_VERIFIED` 或 `ACCESS_BLOCKED` 失败，不会回退到历史接口；
- 不读取登录 Cookie，不处理验证码，不轮换身份或代理。

fixtures 是脱敏的解析契约样本，不宣称来自本次真实响应。只有重新完成正常页面现场验证后，才可在 `constants.py` 中加入已验证 endpoint、host 和字段映射，并启用迁移创建的 JD SourceTarget。
