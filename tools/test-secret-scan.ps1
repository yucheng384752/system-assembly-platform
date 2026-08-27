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

# Hardcoded credential literals in the local VM deploy/debug scripts (e.g. PASS = "qqq123",
# ADMIN_API_KEYS='...') — these scripts talk to a live demo VM, so a hardcoded credential
# here is an active secret leak, not just a style issue. Env-var reads (_require_env(...))
# and f-string interpolation (the quoted value starting with "{") are the expected pattern
# and do not match. Scoped to tools/vm_*.py + _win_full_test.py (where this was found) rather
# than all of tools/, since other tools/test_*.py fixtures use intentional non-secret
# placeholder values that would otherwise false-positive here.
$credentialPattern = '(PASS(WORD)?|PGPASSWORD|ADMIN_API_KEYS?|ADMIN_KEY)\s*=\s*[''"](?!\{)[^''"]+[''"]'
$trackedToolScripts = @(
    & git -C $ProjectRoot ls-files 'tools/vm_*.py' 'tools/_win_full_test.py'
)
$hardcodedCredHits = @()
foreach ($relPath in $trackedToolScripts) {
    $fullPath = Join-Path $ProjectRoot $relPath
    if (-not (Test-Path $fullPath)) {
        continue
    }
    $lineNum = 0
    foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $fullPath) {
        $lineNum++
        $trimmed = $line.TrimStart()
        if ($trimmed.StartsWith("#")) {
            continue
        }
        if ($line -match $credentialPattern) {
            $hardcodedCredHits += "${relPath}:${lineNum}: $($line.Trim())"
        }
    }
}
if ($hardcodedCredHits.Count -gt 0) {
    throw "Hardcoded credential literal(s) found in VM deploy/debug scripts:`n$($hardcodedCredHits -join "`n")"
}

Write-Host "OK secret scan"
