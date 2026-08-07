# 荣耀俱乐部采集器

该采集器只读取荣耀俱乐部公开、无需登录的 HTML 页面。当前入口是话题 595（荣耀 Power2），支持话题列表、楼主、楼层回复、页面内嵌评论、角色、发布时间、图片数量与父子关系解析。

模块职责：

- `client.py`：URL/SSRF 校验、固定 User-Agent、单并发限速与阻断检测；
- `parser.py`：移动版/兼容桌面版 DOM 解析和内容清洗；
- `date_parser.py`：完整时间、省略年份时间和跨年处理；
- `role_mapper.py`：官方、版主、达人、普通等级映射；
- `normalizer.py`：统一记录、相关性判断和脱敏 raw_data；
- `collector.py`：组合 `BaseCollector` 契约。

默认请求间隔至少 3 秒，不持久化 Cookie，不下载图片，不保存昵称、头像、主页、IP、地址或联系方式。403、429、5xx、非 HTML、验证码、登录墙和异常跳转都是停止条件。禁止加入代理池、指纹伪装、验证码处理或私有接口逆向。

测试使用 `tests/fixtures` 中的脱敏最小 HTML。`RUN_HONOR_LIVE_TESTS=1` 可显式启用一次 1 话题 + 1 帖子的在线 smoke test；CI 不启用。
