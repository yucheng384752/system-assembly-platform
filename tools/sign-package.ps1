param(
    [string]$RecipePath     = '',
    [string]$PackageZipPath = '',
    [string]$PrivateKeyPath = (Join-Path $PSScriptRoot "keys\signing-private-key.pem"),
    [string]$OutputDir      = '',
    [string]$MachineId      = '',   # /etc/machine-id from target machine (optional; omit for any-machine license)
    [string]$LicenseeName   = '',   # Override recipe.licensee.name
    [string]$LicenseeEmail  = '',   # Override recipe.licensee.email
    [int]$ExpiresAfterDays  = 0     # Override recipe.licensee.expiresAfterDays (0 = use recipe value)
)

$ErrorActionPreference = 'Stop'

# Resolve recipe ---------------------------------------------------------------
if (-not $RecipePath) {
    $assemblyDir = Join-Path $PSScriptRoot '..\assembly'
    $RecipePath = Get-ChildItem $assemblyDir -Filter '*.recipe.json' |
        Where-Object { $_.Name -notmatch '^(form-analysis-original|mvp-import-flow)' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $RecipePath -or -not (Test-Path $RecipePath)) {
    throw "Recipe not found. Pass -RecipePath or export a recipe to assembly/."
}
if (-not (Test-Path $PrivateKeyPath)) {
    throw "Private key not found: $PrivateKeyPath`nRun tools\generate-license-keys.ps1 first."
}

if (-not $OutputDir) { $OutputDir = Split-Path $RecipePath -Parent }

# Use Node.js for RSA-PSS signing (avoids .NET Framework crypto limitations)
$nodeScript = @'
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const [recipePath, privateKeyPath, outputDir, packageZipPath, machineId,
       licNameOverride, licEmailOverride, licDaysOverride] = process.argv.slice(2);

const rawBuf = fs.readFileSync(recipePath);
const rawText = (rawBuf[0] === 0xEF && rawBuf[1] === 0xBB && rawBuf[2] === 0xBF)
    ? rawBuf.slice(3).toString("utf8") : rawBuf.toString("utf8");
const recipe = JSON.parse(rawText);
const privateKey = fs.readFileSync(privateKeyPath, "utf8");

const recipeLicensee = recipe.licensee || {};
const now = new Date();
const daysRaw = (licDaysOverride && licDaysOverride !== "__none__") ? licDaysOverride : recipeLicensee.expiresAfterDays;
const days = (daysRaw && Number(daysRaw) > 0) ? Number(daysRaw) : 365;
const expiresAt = new Date(now.getTime() + days * 86400000).toISOString().replace(/\.\d+Z$/, "Z");

// Machine fingerprint: accept either a pre-computed SHA-256 hash (64 hex chars)
// or the raw /etc/machine-id string (will be hashed here).
let machineFingerprint = null;
if (machineId && machineId !== "__none__") {
    const trimmed = machineId.trim().toLowerCase();
    if (/^[0-9a-f]{64}$/.test(trimmed)) {
        // Already a SHA-256 fingerprint — use as-is
        machineFingerprint = trimmed;
    } else {
        machineFingerprint = crypto.createHash("sha256").update(trimmed).digest("hex");
    }
}

function sign(payload) {
    const canonical = JSON.stringify(payload);
    const sig = crypto.sign("sha256", Buffer.from(canonical, "utf8"), {
        key: privateKey,
        padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
        saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST,
    });
    return { payload: canonical, signature: sig.toString("base64"), algorithm: "RSA-PSS-SHA256" };
}

// License object
const licPayload = {
    schemaVersion: "1.0",
    issuedAt: now.toISOString().replace(/\.\d+Z$/, "Z"),
    expiresAt,
    licensee: {
        name:  licNameOverride  || recipeLicensee.name  || "",
        email: licEmailOverride || recipeLicensee.email || "",
    },
    recipe: recipe.name,
    enabledKits: recipe.enabledKits ?? [],
};
if (machineFingerprint) {
    licPayload.machineFingerprint = machineFingerprint;
}
const licObj = sign(licPayload);
fs.writeFileSync(path.join(outputDir, "license.lic"), JSON.stringify(licObj, null, 2), "utf8");
console.log("OK license.lic");
console.log("LICENSEE:" + JSON.stringify(licPayload.licensee));
console.log("EXPIRES:" + expiresAt);
if (machineFingerprint) console.log("FINGERPRINT:" + machineFingerprint);

// Package zip signature (optional)
if (packageZipPath && fs.existsSync(packageZipPath)) {
    const zipBytes = fs.readFileSync(packageZipPath);
    const sha256 = crypto.createHash("sha256").update(zipBytes).digest("hex");
    const zipPayload = {
        schemaVersion: "1.0",
        issuedAt: now.toISOString().replace(/\.\d+Z$/, "Z"),
        zipFile: path.basename(packageZipPath),
        sha256,
        recipe: recipe.name,
    };
    const zipSig = sign(zipPayload);
    const sigPath = packageZipPath.replace(/\.zip$/i, ".sig.json");
    fs.writeFileSync(sigPath, JSON.stringify(zipSig, null, 2), "utf8");
    console.log("OK " + path.basename(sigPath));
}
'@

$tmpScript = [System.IO.Path]::GetTempFileName() + '.cjs'
$tmpOut    = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tmpScript, $nodeScript, [System.Text.Encoding]::UTF8)
try {
    $zipArg      = if ($PackageZipPath) { $PackageZipPath } else { '__none__' }
    $midArg      = if ($MachineId)      { $MachineId }      else { '__none__' }
    $nameArg     = if ($LicenseeName)   { $LicenseeName }   else { '__none__' }
    $emailArg    = if ($LicenseeEmail)  { $LicenseeEmail }  else { '__none__' }
    $daysArg     = if ($ExpiresAfterDays -gt 0) { "$ExpiresAfterDays" } else { '__none__' }
    $argStr = """$tmpScript"" ""$RecipePath"" ""$PrivateKeyPath"" ""$OutputDir"" ""$zipArg"" ""$midArg"" ""$nameArg"" ""$emailArg"" ""$daysArg"""
    $proc = Start-Process -FilePath 'node' -ArgumentList $argStr `
        -Wait -PassThru -NoNewWindow -RedirectStandardOutput $tmpOut -RedirectStandardError "$tmpOut.err"
    $stdout = Get-Content $tmpOut -Raw -ErrorAction SilentlyContinue
    $stderr = Get-Content "$tmpOut.err" -Raw -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) {
        throw "node signing failed (exit $($proc.ExitCode)):`n$stdout`n$stderr"
    }
    foreach ($line in ($stdout -split "`n")) {
        $line = $line.Trim()
        if ($line -match '^OK ') { Write-Host $line }
        elseif ($line -match '^LICENSEE:') {
            $data = ($line -replace '^LICENSEE:') | ConvertFrom-Json
            Write-Host "Licensee : $($data.name) <$($data.email)>"
        }
        elseif ($line -match '^FINGERPRINT:') {
            Write-Host "Machine  : $($line -replace '^FINGERPRINT:')"
        }
        elseif ($line -match '^EXPIRES:') {
            Write-Host "Expires  : $($line -replace '^EXPIRES:')"
        }
    }
} finally {
    Remove-Item $tmpScript -ErrorAction SilentlyContinue
    Remove-Item $tmpOut -ErrorAction SilentlyContinue
    Remove-Item "$tmpOut.err" -ErrorAction SilentlyContinue
}
