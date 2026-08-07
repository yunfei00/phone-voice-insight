param(
    [switch]$UseSQLite,
    [switch]$MigrateOnly,
    [string]$PostgresHost = "localhost",
    [int]$PostgresPort = 5432,
    [string]$ListenAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Test-TcpPort([string]$HostName, [int]$TargetPort) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync($HostName, $TargetPort)
        if (-not $connection.Wait(1000)) {
            return $false
        }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if ($UseSQLite) {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.local"
    Write-Warning "Using SQLite local preview mode. PostgreSQL remains required for normal development and deployment."
} else {
    if (-not (Test-TcpPort $PostgresHost $PostgresPort)) {
        throw @"
PostgreSQL is not reachable at ${PostgresHost}:${PostgresPort}.
Start PostgreSQL first, for example:
  docker compose up -d postgres redis
Or run the infrastructure-free preview:
  .\scripts\backend.ps1 -UseSQLite
"@
    }
    $env:DJANGO_SETTINGS_MODULE = "config.settings.development"
    $env:POSTGRES_HOST = $PostgresHost
    $env:POSTGRES_PORT = "$PostgresPort"
}

$env:REDIS_HOST = "localhost"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"

Push-Location $backend
try {
    uv run python manage.py migrate --noinput
    Assert-LastExitCode "Database migration"

    if (-not $MigrateOnly) {
        uv run python manage.py runserver "${ListenAddress}:${Port}"
        Assert-LastExitCode "Django development server"
    }
} finally {
    Pop-Location
}
