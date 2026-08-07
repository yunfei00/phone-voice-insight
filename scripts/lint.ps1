$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $root "backend")
try {
    uv run ruff check . ../collectors ../ai
    if ($LASTEXITCODE -ne 0) { throw "Ruff check failed with exit code $LASTEXITCODE" }
    uv run ruff format --check . ../collectors ../ai
    if ($LASTEXITCODE -ne 0) { throw "Ruff format check failed with exit code $LASTEXITCODE" }
    uv run mypy .
    if ($LASTEXITCODE -ne 0) { throw "mypy failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root "frontend")
try {
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed with exit code $LASTEXITCODE" }
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
