# 荣耀俱乐部采集 PoC

## 1. Power2 话题入口

- 来源：`HONOR_CLUB`
- 产品：荣耀 Power2
- 话题：`https://club.honor.com/cn/threadtopic-595-1.html`
- 外部标识：`topic:595`
- SourceTarget 名称：荣耀Power2官方话题

数据迁移 `0003_seed_honor_power2_target` 幂等创建入口，默认配置为 1 个话题页、最多 10 个帖子、单次请求间隔 3 秒。

## 2. 页面结构

当前匿名请求返回公开移动版 HTML。话题页以 `#threadlist .gm-hlink` 表示帖子入口，可读取 thread id、标题、话题/版块标签和页面已有的计数。帖子页以 `.hbtTbox h1`、`.wapFirstThread`、`.hbt-pl[id^=pid]` 分别表示标题、楼主正文和楼层；`.viewContPl` 是楼层正文。

页面中的嵌套评论占位可能为空。采集器只解析公开 HTML 已内联的 `.comment-item`、`.nested-comment` 或 `data-comment-id` 内容，不逆向页面私有接口。

## 3. 数据字段

统一记录保存稳定 external id、父 external id、类型、标题、清洗正文、发布时间、角色、官方标记、来源 URL、内容哈希和脱敏 raw_data。raw_data 可包含角色原文、设备来源、话题标签、计数、原始时间、图片数量和父级解析方式；不包含昵称、头像、主页、Cookie、Token、IP 或精确位置。

图片只记录 `has_image` / `image_count`，不下载。引用块会从正文移除，避免把被回复者昵称持久化。

## 4. thread/reply 关系

- 楼主：`THREAD` / `thread:{thread_id}` / 无父记录；
- 普通楼层：`REPLY` / `honor_post:{pid}` / 父记录为主题；
- 官方楼层：`OFFICIAL_REPLY` / `honor_post:{pid}` / 父记录为主题；
- 内嵌评论：优先 `honor_comment:{comment_id}` / 父记录为楼层。

缺少稳定 pid/comment id 时使用 thread、楼层、原始时间和正文生成稳定哈希。无法可靠确定内嵌评论父楼层时回退到主题，并在 raw_data 标记 `parent_resolution=thread_fallback`。

## 5. 角色识别

- 荣耀俱乐部团队、荣耀答答团：`OFFICIAL`，`is_official=true`；
- 版主、实习版主：`MODERATOR`；
- 玩机达人、摄影达人及其他明确达人：`EXPERT`；
- LV1～LV10：`USER`；
- 其他：`UNKNOWN`。

版主和达人不是官方。角色原文保存在 `raw_data.author_role_text`。

## 6. checkpoint

每完成一个帖子立即同时更新 CollectionTask 与 CollectionRun：

```json
{
  "topic_page": 1,
  "thread_index": 10,
  "last_thread_id": "30327694"
}
```

网络请求不放在长事务中；只有单条持久化与短暂状态写入使用数据库事务。失败任务保留最后完成的帖子位置以供恢复。

## 7. 去重

第一层使用数据库唯一约束 `source + external_id + record_type`。第二层使用稳定 SHA256：有 external id 时组合 source code、external id 和规范化正文；无 external id 时组合 source code、record type、发布时间和规范化正文。重复项增加 skipped_count，不增加 failure_count。

## 8. 限速

客户端并发为 1，超时 15 秒，两次请求间隔至少 3 秒，使用固定且说明用途的 User-Agent，不轮换指纹。首轮硬限制 1 页/10 帖；runner 即使收到更大配置也限制 PoC 为最多 2 页/20 帖，扩大前必须人工确认。

## 9. 合规边界

只允许 `https://club.honor.com/cn/threadtopic-*.html` 和 `https://club.honor.com/cn/thread-*.html`。拒绝 IP、localhost、外部域名、非 HTTPS、凭据、端口、查询参数和片段。403、429、5xx、非 HTML、异常跳转、验证码或登录墙会立即终止。

不绕过登录/验证码，不伪造 Cookie，不使用代理池、设备指纹或多账号，不逆向私有接口，不下载图片，不做全站抓取。

## 10. PoC 测试方式

```powershell
cd backend
$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
uv run python manage.py honor_club_poc --target-id 1 --limit 1 --dry-run
uv run python manage.py honor_club_poc --target-id 1 --limit 10
```

重复第二条命令验证去重。默认 pytest 只读取脱敏 fixtures；设置 `RUN_HONOR_LIVE_TESTS=1` 才启用最多两次请求的在线 smoke test。

2026-08-08 已完成 2 页/20 帖扩展门禁。第一次完整成功运行扫描 20 帖，新增 42、跳过 67、失败 0；本轮新增类型为 THREAD 8、REPLY 33、OFFICIAL_REPLY 1，checkpoint 为 `topic_page=2 / thread_index=8 / last_thread_id=30318317`。当时本地库累计 109 条：THREAD 20、REPLY 80、OFFICIAL_REPLY 9。

用相同范围清空任务 checkpoint 后重复运行：扫描 20 帖，新增 0、跳过 109、失败 0，checkpoint 与首轮一致，证明数据库唯一约束和稳定 external id 去重生效。两次完整运行均未出现验证码、登录墙或访问风控。

扩展门禁的首次尝试在一个旧帖遇到站内 `mobile=2` 正常移动端重定向，并暴露 `/cn/cn/thread-...` 路径。客户端随后改为逐跳校验，只允许同一荣耀 host、同一 canonical thread 和精确 `mobile=2`，且在发起请求前拒绝外部跳转；修复后完整门禁通过。该兼容问题属于页面行为变化，不应记为风控。

## 11. 已知限制

- 移动页面可能只给图片型主题，正文为空时回退为标题并保留图片数量。
- `昨天`、`前天`、`N 小时前` 等相对时间不基于本机时钟猜测，`published_at` 留空并保留原文。
- 本轮真实 10 帖 HTML 的嵌套评论容器为空，因此真实样本未产生楼层下评论；父子解析由脱敏 fixture 覆盖。
- 页面 DOM 改版会触发解析数量变化，需要更新 fixture 和选择器后再运行。
- 2 页/20 帖门禁已经通过；京东真实评论仍因登录墙与接口未验证而没有采集到数据，AI 分析未实现。
