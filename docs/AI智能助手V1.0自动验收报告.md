# AI 智能助手 V1.0 自动验收报告

## 1. 验收结论

- 验收日期：2026-10-29（Asia/Shanghai）
- 开发基线：`origin/main@38a0815`
- 功能实现提交：`e6826d9`、`5d97077`、`a24504a`、`b38f905`
- 开发分支：`feat/ai-assistant-v1`
- Pull Request：<https://github.com/yunfei00/phone-voice-insight/pull/15>
- GitHub CI：后端、前端均通过（`b38f905`）
- 结论：代码、自动化测试、隔离 Docker 部署和真实浏览器验收均通过，可以合并 `main`。

> `main` 合并提交由 GitHub 在 PR 合并时生成，最终 SHA 记录在本次任务的交付回复中。

## 2. 实现功能

1. 每个用户可维护多个助手模型配置，并可继续使用原有个人默认模型。
2. API Key 复用现有加密能力，只返回末四位，不向前端返回明文。
3. 会话、消息、模型快照、证据、工具轨迹、Token 和耗时均持久化。
4. 实现六个只读业务工具：产品概览、问题统计、产品对比、反馈检索、问题证据、反馈趋势。
5. 原生工具调用与受控兼容回退并存，不支持 function calling 的模型仍可使用。
6. SSE 流式输出、请求幂等、断开处理、停止生成、单用户并发限制和频率限制已实现。
7. 新增深色科技风格助手工作台，支持历史会话、模型切换、产品/来源/时间筛选、快捷问题和证据展开。
8. 驾驶舱增加“向 AI 提问”入口，并携带当前筛选条件。
9. Nginx 和 Compose 增加 SSE 长连接所需的禁用缓冲及超时配置。

## 3. 安全与数据口径

- 所有模型、会话和消息 API 均要求认证，并按当前用户隔离。
- 外部模型地址执行协议、主机、DNS 和 IP 校验；私有地址仅允许管理员显式加入白名单。
- 模型不能执行 SQL、访问任意 ORM，或触发采集、删除、修改和管理操作。
- 业务工具只读取最终有效 AI 语料，并限制参数 Schema、结果数量、时间范围和工具轮数。
- 用户帖子被视为不可信数据，不作为系统指令执行。
- Markdown 使用安全文本节点渲染，不使用 `v-html`。
- 本次验收仅使用 Mock/Fake Provider 和隔离固定数据，没有调用付费模型，也没有读取或输出真实 API Key。

## 4. 自动化测试结果

### 4.1 后端

执行命令：

```text
uv run ruff format --check . ../collectors ../ai ../tools
uv run ruff check . ../collectors ../ai ../tools
uv run mypy . ../collectors ../ai ../tools
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check_structured_analysis_contract
uv run pytest --basetemp ../.pytest-ai-assistant-final
```

结果：

- Ruff Format：PASS，226 个文件。
- Ruff Check：PASS。
- Mypy：PASS，226 个源文件。
- Migration Check：PASS，无待生成迁移。
- Structured Analysis Contract：PASS，版本 `1.0.0`。
- Pytest：PASS，`344 passed, 2 skipped`。
- 两项跳过均为仓库已有的显式真实站点测试开关，不属于功能失败。

本地 Migration Check 因未启动本机 PostgreSQL 输出连接历史检查警告，但命令完成并确认无模型变更；隔离 Docker PostgreSQL 中已实际完成全部迁移。

### 4.2 前端

执行命令：

```text
npm run lint
npm run typecheck
npm run test
npm run build
```

结果：

- ESLint + Prettier：PASS。
- Vue TypeScript：PASS。
- Vitest：PASS，`10` 个测试文件、`31` 项测试。
- Production Build：PASS，转换 `2327` 个模块。

合计：`375` 项自动化测试通过，`2` 项真实站点测试按设计跳过。

## 5. Docker 验收

验收在服务器 `106.52.122.214` 上使用独立项目名、独立网络、独立 PostgreSQL/Redis Volume 和本机环回端口完成，不接触生产数据库：

```text
项目名：pvi-ai-assistant
入口：127.0.0.1:18090
代码：b38f905
```

结果：

- Compose 配置校验：PASS。
- Backend 镜像构建：PASS。
- Frontend 镜像构建：PASS。
- PostgreSQL：healthy。
- Redis：healthy。
- Backend：healthy。
- Frontend：healthy。
- Celery Worker：healthy。
- Celery Beat：healthy。
- `assistant.0001_initial` 迁移：PASS。
- 登录、创建会话、连续提问、工具查询、SSE 回答、证据保存、历史消息读取：PASS。
- 隔离验收数据：1 条最终有效结构化语料，消息历史 6 条，证据引用 1 条。

验收完成后已删除隔离容器、网络和隔离 Volume，并移除服务器测试工作树。生产六个容器始终保持 healthy，生产数据和配置未修改。

## 6. 浏览器与响应式验收

使用实际构建后的前端和后端完成浏览器验收：

- 桌面端 `1440 × 900`：会话侧栏、筛选栏、消息区、模型管理和证据卡片均正常。
- 移动端 `390 × 844`：无横向爆屏，筛选、消息、快捷问题和证据可正常滚动查看。
- 真实浏览器首次发现并修复了 `Accept: text/event-stream` 被 DRF 拒绝为 406 的问题。
- 修复提交 `b38f905` 增加 `EventStreamRenderer` 和精确回归测试；修复后真实快捷提问、流式回答和历史保存均通过。

## 7. GitHub CI

- PR：<https://github.com/yunfei00/phone-voice-insight/pull/15>
- Backend Job：PASS。
- Frontend Job：PASS。
- CI 未采用跳过测试、降低断言或修改为永远成功的方式。

## 8. 已知限制与后续建议

1. 部分 OpenAI-compatible 流式服务不返回 usage，相关消息的 Token 字段可能为 `null`，但不影响回答和证据保存。
2. 停止生成会关闭本系统后续工具和流式读取；模型提供方已经接收的提示词仍可能产生少量已计费 Token。
3. 当前 Gunicorn 使用同步 Worker；已限制单用户并发，未来大规模并发 SSE 可评估 ASGI 部署。
4. Vite 对既有图表及主包输出大于 500 kB 的非阻断警告，助手页面本身已按路由懒加载；后续可继续拆分公共依赖。
5. 本次按安全要求未调用真实付费模型。真实用户保存配置后，可在“模型管理”中执行最小连接测试。

## 9. 最终判定

AI 智能助手 V1.0 的权限隔离、多模型配置、真实业务工具、流式会话、证据追溯、取消与幂等、前端工作台和 Docker 部署均已验证通过。当前不存在阻塞合并的 P0/P1 缺陷。
