param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

function Get-RelativePath([string]$BasePath, [string]$FullPath) {
    $base = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $full = [System.IO.Path]::GetFullPath($FullPath)
    return $full.Substring($base.Length).Replace('\', '/')
}

$trackedPrivateKeys = @(
    & git -C $ProjectRoot ls-files |
        Where-Object { $_ -match '(^|/)(issuer|signing|.+)-private-key\.pem$' -or $_ -match '\.priv$' }
)
if ($trackedPrivateKeys.Count -gt 0) {
    throw "Tracked private key material found: $($trackedPrivateKeys -join ', ')"
}

$gitignorePath = Join-Path $ProjectRoot ".gitignore"
if (-not (Test-Path $gitignorePath)) {
    throw "Missing .gitignore"
}

$gitignore = Get-Content -Raw -Encoding UTF8 $gitignorePath
$requiredIgnorePatterns = @(
    "tools/issuer-private-key.pem",
    "data/issuer-private-key.pem"
)
foreach ($pattern in $requiredIgnorePatterns) {
    if (-not $gitignore.Contains($pattern)) {
        throw ".gitignore is missing private-key protection: $pattern"
    }
}

# Verify tools/keys sub-directory .gitignore protects signing-private-key.pem
$keysGitignorePath = Join-Path $ProjectRoot "tools\keys\.gitignore"
if (-not (Test-Path $keysGitignorePath)) {
    throw "Missing tools/keys/.gitignore (signing-private-key.pem protection)"
}
$keysGitignore = Get-Content -Raw -Encoding UTF8 $keysGitignorePath
if (-not $keysGitignore.Contains("signing-private-key.pem")) {
    throw "tools/keys/.gitignore is missing signing-private-key.pem protection"
}

$distRoots = @(
    "dist\package-stage",
    "dist\form-system-generated-package",
    "dist\generated-system",
    "dist\client-deploy-gui-selected-form-system"
)
foreach ($root in $distRoots) {
    $fullRoot = Join-Path $ProjectRoot $root
    if (-not (Test-Path $fullRoot)) {
        continue
    }

    $privatePemFiles = Get-ChildItem -LiteralPath $fullRoot -Recurse -File -Include *.pem -ErrorAction SilentlyContinue |
        Where-Object {
            $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $_.FullName -ErrorAction SilentlyContinue
            $content -match 'BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY'
        }
    if (@($privatePemFiles).Count -gt 0) {
        $relative = @($privatePemFiles | ForEach-Object { Get-RelativePath $ProjectRoot $_.FullName })
        throw "Private key material found in distributable output: $($relative -join ', ')"
    }
}

Write-Host "OK secret scan"
