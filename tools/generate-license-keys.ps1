param(
    [string]$KeysDir = (Join-Path $PSScriptRoot "keys")
)

$ErrorActionPreference = 'Stop'

$privatePem = Join-Path $KeysDir 'signing-private-key.pem'
$publicPem  = Join-Path $KeysDir 'signing-public-key.pem'

if (Test-Path $privatePem) {
    Write-Host "WARNING: Private key already exists at $privatePem"
    $answer = Read-Host "Overwrite? (y/N)"
    if ($answer -notmatch '^[Yy]') { Write-Host "Aborted."; exit 0 }
}

# Use Node.js built-in crypto (available Node 15+) for RSA key generation
$nodeScript = @'
const { generateKeyPairSync } = require("crypto");
const fs = require("fs");
const path = require("path");
const keysDir = process.argv[2];
fs.mkdirSync(keysDir, { recursive: true });
const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    publicKeyEncoding:  { type: "spki",   format: "pem" },
    privateKeyEncoding: { type: "pkcs8",  format: "pem" },
});
fs.writeFileSync(path.join(keysDir, "signing-private-key.pem"), privateKey, "utf8");
fs.writeFileSync(path.join(keysDir, "signing-public-key.pem"),  publicKey,  "utf8");
console.log("OK");
'@

$tmpScript = [System.IO.Path]::GetTempFileName() + '.cjs'
[System.IO.File]::WriteAllText($tmpScript, $nodeScript, [System.Text.Encoding]::UTF8)
try {
    $out = & node $tmpScript $KeysDir 2>&1
    if ($LASTEXITCODE -ne 0) { throw "node failed: $out" }
    Write-Host "OK  Private key : $privatePem  (KEEP SECRET — gitignored)"
    Write-Host "OK  Public key  : $publicPem   (embed in generated systems)"
    Write-Host ""
    Write-Host "Next step: run tools\sign-package.ps1 to sign a package."
} finally {
    Remove-Item $tmpScript -ErrorAction SilentlyContinue
}
