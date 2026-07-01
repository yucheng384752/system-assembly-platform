param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$AskAuth = [System.Convert]::ToBoolean("true")
$AskPdf = [System.Convert]::ToBoolean("false")
$AskValidation = [System.Convert]::ToBoolean("true")

function Read-EnvFile([string]$Path) {
    $values = [ordered]@{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content -Encoding UTF8 $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') {
            continue
        }
        $name, $value = $line -split '=', 2
        $values[$name.Trim()] = $value
    }
    return $values
}

function Save-EnvFile([string]$Path, [hashtable]$Values, [string[]]$Order) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($name in $Order) {
        if ($Values.Contains($name)) {
            $lines.Add("$name=$($Values[$name])")
        }
    }

    foreach ($name in $Values.Keys) {
        if ($Order -notcontains $name) {
            $lines.Add("$name=$($Values[$name])")
        }
    }

    [System.IO.File]::WriteAllLines($Path, $lines, (New-Object System.Text.UTF8Encoding $false))
}

function Convert-SecureStringToPlainText([securestring]$SecureValue) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Prompt-Value([hashtable]$Values, [string]$Name, [string]$Prompt, [string]$Default = "") {
    $current = if ($Values.Contains($Name)) { [string]$Values[$Name] } else { "" }
    $fallback = if ($current) { $current } else { $Default }
    $suffix = if ($fallback) { " [$fallback]" } else { "" }
    $answer = Read-Host "$Prompt$suffix"
    if ([string]::IsNullOrWhiteSpace($answer)) {
        $answer = $fallback
    }
    $Values[$Name] = $answer
    return $answer
}

function Prompt-Secret([hashtable]$Values, [string]$Name, [string]$Prompt, [switch]$AllowGenerate) {
    $current = if ($Values.Contains($Name)) { [string]$Values[$Name] } else { "" }
    $suffix = if ($current) { " [keep existing]" } else { "" }
    if ($AllowGenerate) {
        $choice = Read-Host "$Prompt$suffix (enter value, 'g' to generate)"
        if ($choice -eq "g") {
            $Values[$Name] = New-RandomSecret
            Write-Host "$Name generated."
            return
        }
        if (-not [string]::IsNullOrWhiteSpace($choice)) {
            $Values[$Name] = $choice
            return
        }
    }

    $secureValue = Read-Host "$Prompt$suffix" -AsSecureString
    $plainValue = Convert-SecureStringToPlainText $secureValue
    if ([string]::IsNullOrWhiteSpace($plainValue) -and $current) {
        $Values[$Name] = $current
    } else {
        $Values[$Name] = $plainValue
    }
}

$envPath = Join-Path $Root ".env"
$examplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $examplePath)) {
        throw ".env does not exist and .env.example was not found."
    }
    Copy-Item -LiteralPath $examplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

$values = Read-EnvFile $envPath

Write-Host "=== Database ==="
$dbHost = Prompt-Value $values "DB_HOST" "Database host" "localhost"
$dbPort = Prompt-Value $values "DB_PORT" "Database port" "5432"
$dbName = Prompt-Value $values "DB_NAME" "Database name" "form_system"
$dbUser = Prompt-Value $values "DB_USERNAME" "Database username" "form_system"
Prompt-Secret $values "DB_PASSWORD" "Database password"
if ([string]::IsNullOrWhiteSpace([string]$values["DATABASE_URL"])) {
    $values["DATABASE_URL"] = "postgresql+asyncpg://$($values["DB_USERNAME"]):$($values["DB_PASSWORD"])@$dbHost`:$dbPort/$dbName"
}
Prompt-Value $values "DATABASE_URL" "DATABASE_URL"

Write-Host ""
Write-Host "=== Application ==="
Prompt-Secret $values "SECRET_KEY" "SECRET_KEY" -AllowGenerate
Prompt-Value $values "CORS_ORIGINS" "CORS origins" "http://localhost:5173,http://localhost:3000"

if ($AskAuth) {
    Write-Host ""
    Write-Host "=== Authentication ==="
    Prompt-Value $values "AUTH_MODE" "Auth mode" "api_key"
    Prompt-Secret $values "ADMIN_API_KEYS" "Admin API keys" -AllowGenerate
    Prompt-Value $values "BOOTSTRAP_MANAGER_ENABLED" "Bootstrap manager enabled" "false"
    Prompt-Value $values "BOOTSTRAP_MANAGER_TENANT_CODE" "Bootstrap manager tenant code" "default"
    Prompt-Value $values "BOOTSTRAP_MANAGER_USERNAME" "Bootstrap manager username" "manager"
    Prompt-Secret $values "BOOTSTRAP_MANAGER_PASSWORD" "Bootstrap manager password"
    Prompt-Value $values "BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD" "Bootstrap manager must change password" "true"
}

if ($AskPdf) {
    Write-Host ""
    Write-Host "=== PDF Conversion ==="
    Prompt-Value $values "PDF_SERVER_URL" "PDF server URL"
    Prompt-Value $values "PDF_SERVER_TIMEOUT_SECONDS" "PDF server timeout seconds" "1800"
    Prompt-Value $values "PDF_SERVER_MAX_CONCURRENT" "PDF server max concurrent" "3"
    Prompt-Value $values "PDF_SERVER_TABLE" "PDF server table"
}

if ($AskValidation) {
    Write-Host ""
    Write-Host "=== Upload Validation ==="
    Prompt-Value $values "VALID_MATERIALS_CSV" "Valid materials CSV"
    Prompt-Value $values "VALID_SLITTING_MACHINES_CSV" "Valid slitting machines CSV"
}

$order = @(
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USERNAME",
    "DB_PASSWORD",
    "DATABASE_URL",
    "SECRET_KEY",
    "CORS_ORIGINS",
    "AUTH_MODE",
    "ADMIN_API_KEYS",
    "BOOTSTRAP_MANAGER_ENABLED",
    "BOOTSTRAP_MANAGER_TENANT_CODE",
    "BOOTSTRAP_MANAGER_USERNAME",
    "BOOTSTRAP_MANAGER_PASSWORD",
    "BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD",
    "PDF_SERVER_URL",
    "PDF_SERVER_TIMEOUT_SECONDS",
    "PDF_SERVER_MAX_CONCURRENT",
    "PDF_SERVER_TABLE",
    "VALID_MATERIALS_CSV",
    "VALID_SLITTING_MACHINES_CSV",
    "MULTI_TENANT_ENABLED",
    "AUDIT_EVENTS_ENABLED",
    "USE_GENERIC_SCHEMA",
    "ENTITLEMENT_MODE",
    "ENVIRONMENT"
)

Save-EnvFile $envPath $values $order
Write-Host "Environment configured: $envPath"