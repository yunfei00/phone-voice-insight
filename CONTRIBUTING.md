# 贡献指南

1. 从最新 `main` 创建 `codex/` 或团队约定前缀的功能分支。
2. 不提交 `.env`、秘密、Cookie、Token、数据库、抓取原始敏感样本、缓存或构建产物。
3. 修改模型时提交迁移；修改 API/Schema 时同步测试和文档。
4. 采集相关变更必须写明平台规则、限速、错误处理和数据最小化；任何验证码/权限绕过代码都不会接受。
5. AI 变更必须版本化 Prompt/模型并验证证据来自原文。

提交前运行：

```powershell
.\scripts\lint.ps1
.\scripts\test.ps1
cd frontend
npm run build
```

Pull Request 应说明范围、验证命令、迁移/环境变量变化、风险和回滚方式。
