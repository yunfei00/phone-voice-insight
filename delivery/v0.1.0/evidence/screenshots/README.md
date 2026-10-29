# 截图证据状态

状态：BLOCKED

2026-10-29 本轮尝试连接已登录 Edge 页面时，Windows 计算机控制无法以足够置信度确认当前浏览器 URL，安全策略主动终止自动化。未绕过该限制，也未使用设计稿或旧图冒充本轮截图。

可复验生产入口：

- `http://106.52.122.214/phone/dashboard`
- `http://106.52.122.214/phone/products`
- `http://106.52.122.214/phone/data-quality`
- `http://106.52.122.214/phone/structured-analysis`
- `http://106.52.122.214/phone/operations`

隔离 Docker 页面仅绑定服务器回环地址 `127.0.0.1:18089`，未暴露公网。
