param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system",
    [string]$ResolvedPlanPath = "assembly\mvp-resolved-plan.json"
)

$ErrorActionPreference = "Stop"
$modelsRoot = Join-Path $ProjectRoot (Join-Path $SystemDirectory "backend\app\models")
if (-not (Test-Path $modelsRoot)) { throw "Models directory is missing: $modelsRoot" }
$planPath = Join-Path $ProjectRoot $ResolvedPlanPath
if (-not (Test-Path $planPath)) { throw "Resolved plan is missing: $planPath" }
$plan = Get-Content -Raw -Encoding UTF8 -LiteralPath $planPath | ConvertFrom-Json

$required = New-Object System.Collections.Generic.HashSet[string]
foreach ($name in @($plan.requiredModels)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$name)) { [void]$required.Add([string]$name) }
}

$exportsByModule = [ordered]@{}
$found = New-Object System.Collections.Generic.HashSet[string]
Get-ChildItem -LiteralPath $modelsRoot -Recurse -File -Filter "*.py" |
    Where-Object Name -ne "__init__.py" |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($modelsRoot.Length + 1)
        $extension = [System.IO.Path]::GetExtension($relative)
        $module = $relative.Substring(0, $relative.Length - $extension.Length).Replace("\", ".").Replace("/", ".")
        $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $_.FullName
        $names = @(
            [regex]::Matches($content, '(?m)^class\s+([A-Za-z_][A-Za-z0-9_]*)\b') |
                ForEach-Object { $_.Groups[1].Value } |
                Where-Object { $required.Contains($_) } |
                Select-Object -Unique
        )
        if ($names.Count) {
            $exportsByModule[$module] = $names
            foreach ($name in $names) { [void]$found.Add($name) }
        }
    }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('"""Generated model package exports for the selected recipe."""')
$lines.Add('')
foreach ($entry in $exportsByModule.GetEnumerator()) { $lines.Add("from .$($entry.Key) import $(@($entry.Value) -join ', ')") }
$lines.Add('')
$lines.Add('__all__ = [')
foreach ($name in @($found | Sort-Object)) { $lines.Add("    `"$name`",") }
$lines.Add(']')

$initPath = Join-Path $modelsRoot "__init__.py"
$lines -join [Environment]::NewLine | Set-Content -Encoding UTF8 -LiteralPath $initPath
$missing = @($required | Where-Object { -not $found.Contains($_) } | Sort-Object)
if ($missing.Count) { Write-Warning "Required model classes not found in assembled source: $($missing -join ', ')" }
Write-Host "Generated model exports at $initPath"
