param([string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path)

$ErrorActionPreference = 'Stop'

function Assert-Match([string]$Content, [string]$Pattern, [string]$Message) {
    if ($Content -notmatch $Pattern) { throw $Message }
}

$modal = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot 'kits\audit-edit-kit\src\frontend\src\components\EditRecordModal.tsx')
$reasons = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot 'kits\audit-edit-kit\src\frontend\src\pages\EditReasonsPage.tsx')
$forms = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot 'kits\generic-forms-kit\src\frontend\src\pages\FormsPage.tsx')
$app = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot 'kits\generic-forms-kit\src\frontend\src\App.tsx')

Assert-Match -Content $modal -Pattern 'body: JSON\.stringify\(\{ reason_id: reasonId, changes \}\)' -Message 'Record PATCH body contract changed.'
Assert-Match -Content $modal -Pattern 'Object\.is\(next, original\)' -Message 'Record changes must exclude unchanged fields.'
Assert-Match -Content $modal -Pattern 'body\.filter\(\(reason\) => reason\.is_active\)' -Message 'Record modal must list active reasons only.'
Assert-Match -Content $modal -Pattern 'type Scalar = string \| number \| boolean \| null' -Message 'Record changes must remain scalar-only.'
Assert-Match -Content $modal -Pattern 'const n = Number\(text\);' -Message 'Numeric input must be parsed once.'
Assert-Match -Content $modal -Pattern 'return Number\.isNaN\(n\) \? text : \(field\.type === "integer" \? Math\.trunc\(n\) : n\);' -Message 'Unparseable numeric input must remain a string for backend validation.'
Assert-Match -Content $reasons -Pattern 'const patch: \{ label\?: string; is_active\?: boolean \} = \{\}' -Message 'Reason PATCH must only allow label and is_active.'
Assert-Match -Content $reasons -Pattern 'body: JSON\.stringify\(patch\)' -Message 'Reason PATCH must send the restricted patch object.'
Assert-Match -Content $forms -Pattern 'setEditingRecord\(r\)' -Message 'Forms record edit button is not mounted.'
Assert-Match -Content $app -Pattern 'canShowManager \? \(' -Message 'Edit reasons tab must use the manager gate.'
Assert-Match -Content $app -Pattern 'tab === "editReasons"' -Message 'Edit reasons page is not registered.'

node -e "const value=(type,text)=>{const n=Number(text);return Number.isNaN(n)?text:(type==='integer'?Math.trunc(n):n)};if(value('integer','42x')!=='42x'||value('integer','42')!==42||value('decimal','12.5')!==12.5)process.exit(1)"
if ($LASTEXITCODE -ne 0) { throw 'Numeric scalar conversion behavior changed.' }

Write-Host 'OK edit-record frontend contracts'
