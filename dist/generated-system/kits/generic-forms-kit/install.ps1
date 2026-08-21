param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
)
$ErrorActionPreference = "Stop"
Write-Host "generic-forms-kit: schema-driven form types and generic record storage enabled."
Write-Host "  Backend: /api/forms (CRUD), /api/forms/{code}/schema, /api/forms/{code}/records, /api/forms/{code}/upload"
Write-Host "  Frontend: 通用表格 tab for managing form schemas and viewing records."
