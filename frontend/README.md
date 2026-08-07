# PVI 前端

Vue 3 + TypeScript + Vite 后台应用。页面数据统一通过 `VITE_API_BASE_URL` 访问后端，默认使用相对路径 `/api/v1`。

```powershell
npm ci
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
```

Phase 1 只提供真实 API 驱动的基础页面；没有后端数据时显示 0 或空状态，不生成模拟业务结果。
