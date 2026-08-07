# 京东评价接口发现报告

- 生成时间：2026-08-08（Asia/Shanghai）
- 结果：`C JD_REVIEW_ACCESS_BLOCKED`
- 商品 ID：`100310496358`
- 方法：Playwright 启动独立可视 Chrome profile，由用户人工导航；程序只监听京东域名的 XHR/fetch。

## 浏览器访问

- 隔离 Chrome 的京东搜索页显示“访问频繁导致无法搜索”。
- 使用商品基础链接直达后仍要求登录，评价区域未在隔离会话中正常显示。
- 用户提供的日常 Chrome 截图可见荣耀 Power2 商品与评价，但本工具没有接管、读取或复制该浏览器的 profile、Cookie 或登录会话。
- 未自动登录，未处理验证码或滑块，未尝试规避风控。

## 网络结果

本次保留了 369 条京东 XHR/fetch 脱敏响应索引：HTTP 200 为 299 条，HTTP 403 为 70 条。403 全部来自以下通用入口：

| host | path | method | status | content-type | 数量 |
| --- | --- | --- | ---: | --- | ---: |
| `api.m.jd.com` | `/` | GET | 403 | 未提供 | 42 |
| `api.m.jd.com` | `/api` | GET | 403 | 未提供 | 25 |
| `api.m.jd.com` | `/` | POST | 403 | 未提供 | 2 |
| `api.m.jd.com` | `/api` | POST | 403 | 未提供 | 1 |

没有人工确认到评价接口。host/path、分页参数、排序语义和响应字段均不得据此猜测或写入正式 JD collector。

运行时发现部分成功响应使用 `text/json` 或 `text/plain`。探测器已补充这两类内容类型的严格 JSON/JSONP 解析支持，但由于隔离会话仍受登录/访问限制，没有再次发起在线探测，因此不把它们宣称为评价响应。

## 响应结构

没有通过 Stage A 的已确认评价候选，所以评论 ID、正文、评分、时间、SKU、追评结构和分页字段全部为“未验证”。Stage B 未启动，脱敏样本数为 0。

## 隐私

- 未读取或保存 Cookie、Authorization、请求头、Set-Cookie、POST 数据或浏览器 Storage。
- 未读取用户现有 Chrome profile；登录状态仅存在于本次独立 profile，随后已停止探测进程。
- 未保存完整响应，也未生成 `sanitized-sample.json`。
- `.local/jd-probe/` 与 `.local/jd-browser-profile/` 均由 Git 忽略，不提交到仓库。

## 结论与替代方案

本次分类为 `C JD_REVIEW_ACCESS_BLOCKED`。Phase 3 状态为 `POSTPONED`，不是系统缺陷，也不表示 Phase 3 已完成。京东 SourceTarget 保持停用；产品第一版改为只依赖荣耀俱乐部数据。

允许的后续路线只有：

1. 使用京东提供且账号获授权的官方 API 或数据服务；
2. 由人工从正常可见页面导出最小化、脱敏后的评价字段，再通过受控导入流程处理；
3. 使用组织内部已有授权、来源可追溯的数据集。

不采用复制 Cookie/Token、复用日常 Chrome profile、逆向签名、绕过登录/验证码、代理池或高频重试。
