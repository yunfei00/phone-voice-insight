# 京东浏览器辅助接口探测

该工具只解决“2026 年当前京东评价从哪里加载”。它不是正式 JDCollector，也不自动点击、登录、处理验证码或绕过风控。

## 安全边界

- 由 Playwright 以 `headless=False` 启动系统 Chrome；
- 只使用 `.local/jd-browser-profile/` 独立 profile，不读取或复制用户现有 Chrome profile；
- 只监听 `*.jd.com` / `*.jd.cn` 的 XHR/fetch；
- 不读取或保存 Cookie、Authorization、请求头、Set-Cookie、POST 数据或浏览器 Storage；
- URL 中未知或敏感 query 值写入报告前统一替换为 `<redacted>`；
- Stage A 只保存网络元数据、顶层 key 和数组长度；
- 人工确认候选后，Stage B 最多保存 3 条递归脱敏样本；
- 完整 response 永远只短暂存在内存，不落盘。

`.local/` 已由 Git 忽略。不要移动、上传或提交其中的 profile 与探测输出。

## 运行

在仓库根目录执行：

```powershell
$env:RUN_JD_BROWSER_LIVE_TEST = "1"
.\backend\.venv\Scripts\python.exe -m tools.jd_browser_probe.probe
```

浏览器打开后，由用户人工进入“商品评价”、切换“最新评价”并最多查看三页，之后回到探测终端按 Enter。程序会显示 Stage A 候选，请用户选择确认为评价的请求，再回答页面/登录/验证状态。

输出：

- `.local/jd-probe/network-index.json`
- `.local/jd-probe/stage-a-candidates.json`
- `.local/jd-probe/sanitized-sample.json`（仅确认候选后生成）
- `.local/jd-probe/discovery-report.json`
- `docs/jd-interface-discovery.md`

结果只会是：`A PUBLIC_ENDPOINT_FOUND`、`B BROWSER_SESSION_REQUIRED` 或 `C JD_REVIEW_ACCESS_BLOCKED`。
