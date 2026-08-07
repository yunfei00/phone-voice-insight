$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

foreach ($command in @("uv", "node", "npm")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $command"
    }
}

$envFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination $envFile
    Write-Host "Created .env from .env.example. Replace sample secrets before shared use."
}

Push-Location (Join-Path $root "backend")
try {
    uv sync
    Assert-LastExitCode "Backend dependency installation"
} finally {
    Pop-Location
}

Push-Location (Join-Path $root "frontend")
try {
    npm ci
    Assert-LastExitCode "Frontend dependency installation"
} finally {
    Pop-Location
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Push-Location $root
    try {
        docker compose up -d postgres redis
        Assert-LastExitCode "PostgreSQL/Redis startup"
        docker compose run --rm backend python manage.py migrate --noinput
        Assert-LastExitCode "Database migration"
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "Docker was not found. Dependencies are installed; prepare PostgreSQL/Redis before migrating."
}

Write-Host "PVI development setup completed."
