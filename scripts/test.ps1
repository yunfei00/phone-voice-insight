$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $root "backend")
try {
    uv run pytest
    if ($LASTEXITCODE -ne 0) {
        throw "Backend tests failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root "frontend")
try {
    npm run test
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend tests failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
