# 本地开发快捷脚本 — 在 PowerShell 中运行: .\scripts\dev.ps1

param(
    [ValidateSet("up", "down", "migrate", "test", "run", "check")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

switch ($Action) {
    "up" {
        if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
        docker compose up -d
        Write-Host "Waiting for services..." -ForegroundColor Cyan
        Start-Sleep -Seconds 15
        uv run python manage.py migrate
        Write-Host "Ready. Run: .\scripts\dev.ps1 -Action run" -ForegroundColor Green
    }
    "down" { docker compose down }
    "migrate" { uv run python manage.py migrate }
    "test" { uv run python manage.py test }
    "run" { uv run python manage.py runserver }
    "check" {
        uv run ruff check .
        uv run ruff format --check .
        uv run python manage.py test
    }
}
