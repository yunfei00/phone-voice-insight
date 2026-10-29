# 截图证据

状态：PASS

2026-10-29 使用 Playwright 登录 `pvi-v010-acceptance` 隔离 Docker 环境生成，页面数据来自独立 PostgreSQL，不是设计稿或静态 Mock。隔离页面通过 SSH 回环隧道访问，未暴露公网；截图后隧道已关闭。

| 文件 | 页面 | 验收重点 |
| --- | --- | --- |
| `01-dashboard.png` | 智能驾驶舱 | 深色主题、真实空数据状态、筛选和投屏入口 |
| `02-data-quality.png` | 数据质量 | 测试产品、1 条反馈、全量治理任务 SUCCESS 1/1 |
| `03-structured-analysis.png` | AI 结构化分析 | taxonomy、筛选、空结果和任务区域 |

三张 PNG 均已人工目视检查，无登录密码、API Key 或生产用户数据。
