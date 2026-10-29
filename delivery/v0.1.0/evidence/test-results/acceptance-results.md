# V0.1.0 验收执行证据摘要

执行时间：2026-10-29 13:00–13:20 +08:00

## 本地

- Ruff format/check：PASS（212 files）
- Mypy：PASS（212 source files）
- Django system check：PASS
- Migration check：PASS（No changes detected）
- Structured analysis contract：PASS（1.0.0）
- Pytest：326 passed，2 skipped，9.31 秒；覆盖率重跑 17.14 秒
- Frontend：8 files / 26 tests PASS
- ESLint、Prettier、TypeScript、Production Build：PASS
- npm audit：0 vulnerabilities

## GitHub

- Run：40821943255
- backend：PASS（29 秒）
- frontend：PASS（34 秒）

## 隔离 Docker

- Project：`pvi-v010-acceptance`
- Commit：`61333cb`
- 六容器：healthy
- HTTP health：database=ok、redis=ok
- Migration：全部应用
- Celery ping：1 node online / pong
- P0：HTTP 202，source_id=null，任务 SUCCESS，processed=1，failed=0
- 重启恢复：原始记录 1、治理记录 1、任务 SUCCESS

## 生产只读一致性核对

- ReviewRecord：9428
- ReviewQuality：464
- AnalysisCorpusItem：464
- SUCCEEDED AnalysisRun：1
- StructuredAnalysis：1
- SUCCEEDED 但无 StructuredAnalysis：0
