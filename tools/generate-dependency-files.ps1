param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system",
    [string]$BaselinePath = (Join-Path $PSScriptRoot "..\assembly\baselines\default-requirements.baseline.json")
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

# Load baseline contract: name → spec (e.g. "asyncpg" → ">=0.29.0")
$baselinePackages = [ordered]@{}
$baselineFile = $null
if (Test-Path $BaselinePath) {
    $baselineFile = (Resolve-Path $BaselinePath).Path
    $baselineJson = Get-Content -Raw -Encoding UTF8 $BaselinePath | ConvertFrom-Json
    foreach ($pkg in $baselineJson.python.packages) {
        $baselinePackages[$pkg.name] = $pkg.spec
    }
}

# Pinned production versions — update here when bumping deps.
$PYTHON_VERSIONS = @{
    "fastapi"            = "0.115.0"
    "uvicorn[standard]"  = "0.30.6"
    "sqlalchemy"         = "2.0.36"
    "pydantic"           = "2.9.2"
    "pydantic-settings"  = "2.5.2"
    # Keep in FastAPI 0.115.x's supported Starlette range.
    "starlette"          = "0.38.6"
    "structlog"          = "24.4.0"
    "pandas"             = "2.2.3"
    "httpx"              = "0.27.2"
    "python-dotenv"      = "1.0.1"
    "python-multipart"   = "0.0.12"
    "asyncpg"            = "0.29.0"
    "openpyxl"           = "3.1.5"
}

$FRONTEND_VERSIONS = @{
    "react"                          = "18.3.1"
    "react-dom"                      = "18.3.1"
    "react-i18next"                  = "15.0.2"
    "i18next"                        = "23.15.2"
    "i18next-browser-languagedetector" = "8.0.0"
    "lucide-react"                   = "0.460.0"
    "@vitejs/plugin-react"           = "4.4.1"
    "vite"                           = "6.0.5"
    "typescript"                     = "5.7.2"
    "@types/react"                   = "18.3.12"
    "@types/react-dom"               = "18.3.1"
}

function Get-PythonVersion([string]$PackageName) {
    if ($PYTHON_VERSIONS.ContainsKey($PackageName)) { return $PYTHON_VERSIONS[$PackageName] }
    return "latest"
}

function Get-FrontendVersion([string]$PackageName) {
    if ($FRONTEND_VERSIONS.ContainsKey($PackageName)) { return $FRONTEND_VERSIONS[$PackageName] }
    return "latest"
}

function Get-TopLevelPythonImports([string]$BackendPath) {
    $imports = New-Object System.Collections.Generic.HashSet[string]
    if (-not (Test-Path $BackendPath)) {
        return $imports
    }

    Get-ChildItem -LiteralPath $BackendPath -Recurse -File -Filter *.py | ForEach-Object {
        $content = [string](Get-Content -Raw -Encoding UTF8 $_.FullName)
        foreach ($match in [regex]::Matches($content, "(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_\.]*)")) {
            $topLevel = $match.Groups[1].Value.Split(".")[0]
            [void]$imports.Add($topLevel)
        }
    }
    return $imports
}

function Get-FrontendPackageImports([string]$FrontendPath) {
    $imports = New-Object System.Collections.Generic.HashSet[string]
    if (-not (Test-Path $FrontendPath)) {
        return $imports
    }

    Get-ChildItem -LiteralPath $FrontendPath -Recurse -File -Include *.ts,*.tsx,*.js,*.jsx | ForEach-Object {
        $content = [string](Get-Content -Raw -Encoding UTF8 $_.FullName)
        foreach ($match in [regex]::Matches($content, "from\s+['""]([^'""]+)['""]|import\s*\(\s*['""]([^'""]+)['""]\s*\)")) {
            $specifier = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
            if ($specifier.StartsWith(".") -or $specifier.StartsWith("/")) {
                continue
            }
            $packageName = $specifier
            if ($specifier.StartsWith("@")) {
                $parts = $specifier.Split("/")
                if ($parts.Length -ge 2) {
                    $packageName = "$($parts[0])/$($parts[1])"
                }
            } else {
                $packageName = $specifier.Split("/")[0]
            }
            [void]$imports.Add($packageName)
        }
    }
    return $imports
}

function Add-IfImported(
    [System.Collections.Generic.HashSet[string]]$Imports,
    [System.Collections.Generic.List[string]]$Requirements,
    [string]$ImportName,
    [string]$RequirementName
) {
    if ($Imports.Contains($ImportName) -and -not $Requirements.Contains($RequirementName)) {
        $Requirements.Add($RequirementName)
    }
}

$systemPath = Join-Path $ProjectRoot $SystemDirectory
$backendPath = Join-Path $systemPath "backend"
$frontendPath = Join-Path $systemPath "frontend"

if (-not (Test-Path $systemPath)) {
    throw "System directory not found: $systemPath"
}

$pythonImports = Get-TopLevelPythonImports $backendPath
$requirementNames = New-Object System.Collections.Generic.List[string]

Add-IfImported $pythonImports $requirementNames "fastapi" "fastapi"
Add-IfImported $pythonImports $requirementNames "uvicorn" "uvicorn[standard]"
Add-IfImported $pythonImports $requirementNames "sqlalchemy" "sqlalchemy"
Add-IfImported $pythonImports $requirementNames "pydantic" "pydantic"
Add-IfImported $pythonImports $requirementNames "pydantic_settings" "pydantic-settings"
Add-IfImported $pythonImports $requirementNames "starlette" "starlette"
Add-IfImported $pythonImports $requirementNames "structlog" "structlog"
Add-IfImported $pythonImports $requirementNames "pandas" "pandas"
Add-IfImported $pythonImports $requirementNames "httpx" "httpx"
Add-IfImported $pythonImports $requirementNames "dotenv" "python-dotenv"

$backendContent = ""
if (Test-Path $backendPath) {
    $backendContent = (Get-ChildItem -LiteralPath $backendPath -Recurse -File -Filter *.py | ForEach-Object {
        Get-Content -Raw -Encoding UTF8 $_.FullName
    }) -join "`n"
}

if ($backendContent.Contains("UploadFile") -and -not $requirementNames.Contains("python-multipart")) {
    $requirementNames.Add("python-multipart")
}
if ($backendContent.Contains("postgresql+asyncpg") -or $backendContent.Contains("create_async_engine")) {
    if (-not $requirementNames.Contains("asyncpg")) {
        $requirementNames.Add("asyncpg")
    }
}
if ($backendContent.Contains("read_excel") -or $backendContent.Contains("Excel")) {
    if (-not $requirementNames.Contains("openpyxl")) {
        $requirementNames.Add("openpyxl")
    }
}

# Build requirement lines: baseline packages first (in declared order), then any
# inferred extras not already covered by the baseline.
$addedNames = New-Object System.Collections.Generic.HashSet[string]
$requirementLines = New-Object System.Collections.Generic.List[string]

foreach ($kvp in $baselinePackages.GetEnumerator()) {
    $requirementLines.Add("$($kvp.Key)$($kvp.Value)")
    [void]$addedNames.Add($kvp.Key)
    [void]$addedNames.Add(($kvp.Key -replace '\[.*\]', ''))
}

foreach ($name in $requirementNames) {
    $baseName = $name -replace '\[.*\]', ''
    if (-not $addedNames.Contains($name) -and -not $addedNames.Contains($baseName)) {
        $ver = Get-PythonVersion $name
        $requirementLines.Add($(if ($ver -eq "latest") { $name } else { "$name==$ver" }))
        [void]$addedNames.Add($name)
    }
}

$requirementsPath = Join-Path $backendPath "requirements.txt"
[System.IO.File]::WriteAllText($requirementsPath, ($requirementLines -join "`n") + "`n", $utf8NoBom)

$frontendImports = Get-FrontendPackageImports $frontendPath
$dependencies = [ordered]@{}
foreach ($packageName in @("react", "react-dom", "react-i18next", "i18next", "i18next-browser-languagedetector", "lucide-react")) {
    if ($frontendImports.Contains($packageName)) {
        $dependencies[$packageName] = Get-FrontendVersion $packageName
    }
}
if (-not $dependencies.Contains("react")) {
    $dependencies["react"] = Get-FrontendVersion "react"
}
if (-not $dependencies.Contains("react-dom")) {
    $dependencies["react-dom"] = Get-FrontendVersion "react-dom"
}

$devDependencies = [ordered]@{
    "@vitejs/plugin-react" = Get-FrontendVersion "@vitejs/plugin-react"
    "vite"                 = Get-FrontendVersion "vite"
    "typescript"           = Get-FrontendVersion "typescript"
    "@types/react"         = Get-FrontendVersion "@types/react"
    "@types/react-dom"     = Get-FrontendVersion "@types/react-dom"
}

$packageJson = [ordered]@{
    private = $true
    type = "module"
    scripts = [ordered]@{
        dev = "vite"
        build = "vite build"
        preview = "vite preview"
    }
    dependencies = $dependencies
    devDependencies = $devDependencies
}

$packageJsonPath = Join-Path $frontendPath "package.json"
[System.IO.File]::WriteAllText($packageJsonPath, ($packageJson | ConvertTo-Json -Depth 20), $utf8NoBom)

# Generate vite.config.ts if missing
$viteConfigPath = Join-Path $frontendPath "vite.config.ts"
if (-not (Test-Path $viteConfigPath)) {
    $c = "import { defineConfig } from 'vite'`nimport react from '@vitejs/plugin-react'`n`nexport default defineConfig({`n  plugins: [react()],`n  server: {`n    proxy: {`n      '/api': process.env.VITE_PROXY_TARGET || 'http://localhost:8000',`n    },`n  },`n  build: {`n    outDir: 'dist',`n  },`n})`n"
    [System.IO.File]::WriteAllText($viteConfigPath, $c, $utf8NoBom)
}

# Generate tsconfig.json if missing
$tsconfigPath = Join-Path $frontendPath "tsconfig.json"
if (-not (Test-Path $tsconfigPath)) {
    $c = "{`n  `"files`": [],`n  `"references`": [`n    { `"path`": `"./tsconfig.app.json`" },`n    { `"path`": `"./tsconfig.node.json`" }`n  ]`n}`n"
    [System.IO.File]::WriteAllText($tsconfigPath, $c, $utf8NoBom)
}

$tsconfigAppPath = Join-Path $frontendPath "tsconfig.app.json"
if (-not (Test-Path $tsconfigAppPath)) {
    $tsconfigAppObj = [ordered]@{
        compilerOptions = [ordered]@{
            tsBuildInfoFile = "./node_modules/.tmp/tsconfig.app.tsbuildinfo"
            target = "ES2020"; useDefineForClassFields = $true
            lib = @("ES2020","DOM","DOM.Iterable"); module = "ESNext"
            skipLibCheck = $true; moduleResolution = "bundler"
            allowImportingTsExtensions = $true; isolatedModules = $true
            moduleDetection = "force"; noEmit = $true; jsx = "react-jsx"
            strict = $true; noFallthroughCasesInSwitch = $true
        }
        include = @("src")
    }
    [System.IO.File]::WriteAllText($tsconfigAppPath, ($tsconfigAppObj | ConvertTo-Json -Depth 10), $utf8NoBom)
}

$tsconfigNodePath = Join-Path $frontendPath "tsconfig.node.json"
if (-not (Test-Path $tsconfigNodePath)) {
    $tsconfigNodeObj = [ordered]@{
        compilerOptions = [ordered]@{
            tsBuildInfoFile = "./node_modules/.tmp/tsconfig.node.tsbuildinfo"
            target = "ES2022"; lib = @("ES2023"); module = "ESNext"
            skipLibCheck = $true; moduleResolution = "bundler"
            allowImportingTsExtensions = $true; isolatedModules = $true
            moduleDetection = "force"; noEmit = $true; strict = $true
            noFallthroughCasesInSwitch = $true
        }
        include = @("vite.config.ts")
    }
    [System.IO.File]::WriteAllText($tsconfigNodePath, ($tsconfigNodeObj | ConvertTo-Json -Depth 10), $utf8NoBom)
}

# Generate index.html if missing
$indexHtmlPath = Join-Path $frontendPath "index.html"
if (-not (Test-Path $indexHtmlPath)) {
    $c = "<!doctype html>`n<html lang=`"en`">`n  <head>`n    <meta charset=`"UTF-8`" />`n    <meta name=`"viewport`" content=`"width=device-width, initial-scale=1.0`" />`n    <title>Form System</title>`n  </head>`n  <body>`n    <div id=`"root`"></div>`n    <script type=`"module`" src=`"/src/main.tsx`"></script>`n  </body>`n</html>`n"
    [System.IO.File]::WriteAllText($indexHtmlPath, $c, $utf8NoBom)
}

# Generate vite-env.d.ts for import.meta.env support
$viteEnvPath = Join-Path $frontendPath "src\vite-env.d.ts"
if (-not (Test-Path $viteEnvPath)) {
    [System.IO.File]::WriteAllText($viteEnvPath, '/// <reference types="vite/client" />', (New-Object System.Text.UTF8Encoding $false))
}

# Helper: write a stub file only if it doesn't already exist (BOM-less UTF-8)
function Write-StubIfMissing([string]$Path, [string]$Content) {
    if (-not (Test-Path $Path)) {
        $dir = Split-Path -Parent $Path
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        [System.IO.File]::WriteAllText($Path, $Content, $script:utf8NoBom)
    }
}

$srcPath = Join-Path $frontendPath "src"

# CSS stubs (empty files)
foreach ($cssRel in @('index.css', 'styles\app.css', 'styles\figma.css',
                       'styles\admin-page.css', 'styles\manager-page.css',
                       'styles\register-page.css', 'styles\upload-page.css')) {
    Write-StubIfMissing (Join-Path $srcPath $cssRel) ''
}

# src/types/api.ts
Write-StubIfMissing (Join-Path $srcPath 'types\api.ts') @'
export interface FilePreview {
  id: string
  name: string
  size: number
  type: string
  status: string
}
export interface FileValidationError {
  row?: number
  column?: string
  message: string
}
export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'
'@

# src/components/common/ToastContext.tsx
Write-StubIfMissing (Join-Path $srcPath 'components\common\ToastContext.tsx') @'
import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
interface Toast { id: number; message: string; type?: string }
interface ToastCtx { addToast: (msg: string, type?: string) => void }
const ToastContext = createContext<ToastCtx>({ addToast: () => {} })
export function ToastProvider({ children }: { children: ReactNode }) {
  const [, setToasts] = useState<Toast[]>([])
  const addToast = useCallback((message: string, type?: string) => {
    setToasts(t => [...t, { id: Date.now(), message, type }])
  }, [])
  return <ToastContext.Provider value={{ addToast }}>{children}</ToastContext.Provider>
}
export function useToast() { return useContext(ToastContext) }
'@

# src/components/common/ToastContainer.tsx
Write-StubIfMissing (Join-Path $srcPath 'components\common\ToastContainer.tsx') @'
export function ToastContainer() { return null }
'@

# src/components/common/Modal.tsx
Write-StubIfMissing (Join-Path $srcPath 'components\common\Modal.tsx') @'
import type { ReactNode } from "react"
interface ModalProps { open?: boolean; onClose?: () => void; children?: ReactNode; title?: string }
export function Modal({ open, children, onClose }: ModalProps) {
  if (!open) return null
  return (
    <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,.4)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000 }}>
      <div style={{ background:"#fff",borderRadius:8,padding:24,minWidth:320,maxWidth:"90vw" }}>
        {children}
        {onClose && <button onClick={onClose} style={{ marginTop:16 }}>Close</button>}
      </div>
    </div>
  )
}
export default Modal
'@

# src/components/common/ProgressBar.tsx
Write-StubIfMissing (Join-Path $srcPath 'components\common\ProgressBar.tsx') @'
interface ProgressBarProps { value?: number; max?: number; className?: string }
export function ProgressBar({ value = 0, max = 100, className }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className={className} style={{ background:"#e5e7eb",borderRadius:4,height:8 }}>
      <div style={{ width:`${pct}%`,height:"100%",background:"#3b82f6",borderRadius:4,transition:"width .2s" }} />
    </div>
  )
}
export default ProgressBar
'@

# src/components/SimpleLogViewer.tsx
Write-StubIfMissing (Join-Path $srcPath 'components\SimpleLogViewer.tsx') @'
export default function SimpleLogViewer() {
  return <div style={{ padding:16, fontFamily:"monospace" }}>Log viewer not available.</div>
}
'@

# src/pages/QueryPage.tsx
Write-StubIfMissing (Join-Path $srcPath 'pages\QueryPage.tsx') @'
export function QueryPage() {
  return <div style={{ padding:24 }}>Query Page</div>
}
'@

# src/pages/AnalyticsPage.tsx
Write-StubIfMissing (Join-Path $srcPath 'pages\AnalyticsPage.tsx') @'
export function AnalyticsPage() {
  return <div style={{ padding:24 }}>Analytics Page</div>
}
'@

# src/components/admin stubs
Write-StubIfMissing (Join-Path $srcPath 'components\admin\StationManager.tsx') @'
export function StationManager() { return <div>Station Manager</div> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\admin\ValidationRuleManager.tsx') @'
export function ValidationRuleManager() { return <div>Validation Rule Manager</div> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\admin\AnalyticsMappingManager.tsx') @'
export function AnalyticsMappingManager() { return <div>Analytics Mapping Manager</div> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\admin\StationLinkManager.tsx') @'
export function StationLinkManager() { return <div>Station Link Manager</div> }
'@

# src/components/ui stubs
Write-StubIfMissing (Join-Path $srcPath 'components\ui\table.tsx') @'
import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react"
export function Table({ children }: { children?: ReactNode }) { return <table style={{ width:"100%",borderCollapse:"collapse" }}>{children}</table> }
export function TableHeader({ children }: { children?: ReactNode }) { return <thead>{children}</thead> }
export function TableBody({ children }: { children?: ReactNode }) { return <tbody>{children}</tbody> }
export function TableRow({ children }: { children?: ReactNode }) { return <tr>{children}</tr> }
export function TableHead({ children, ...p }: ThHTMLAttributes<HTMLTableCellElement>) { return <th style={{ padding:"8px",borderBottom:"1px solid #e5e7eb",textAlign:"left" }} {...p}>{children}</th> }
export function TableCell({ children, ...p }: TdHTMLAttributes<HTMLTableCellElement>) { return <td style={{ padding:"8px",borderBottom:"1px solid #e5e7eb" }} {...p}>{children}</td> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\ui\input.tsx') @'
import type { InputHTMLAttributes } from "react"
export function Input(p: InputHTMLAttributes<HTMLInputElement>) { return <input style={{ border:"1px solid #d1d5db",borderRadius:4,padding:"4px 8px",width:"100%" }} {...p} /> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\ui\button.tsx') @'
import type { ButtonHTMLAttributes } from "react"
export function Button({ className, ...p }: ButtonHTMLAttributes<HTMLButtonElement>) { return <button style={{ padding:"6px 12px",borderRadius:4,cursor:"pointer" }} className={className} {...p} /> }
'@
Write-StubIfMissing (Join-Path $srcPath 'components\ui\progress.tsx') @'
export function Progress({ value = 0, className }: { value?: number; className?: string }) {
  return <div className={className} style={{ background:"#e5e7eb",borderRadius:4,height:8 }}><div style={{ width:`${Math.min(100,value)}%`,height:"100%",background:"#3b82f6",borderRadius:4 }} /></div>
}
'@
Write-StubIfMissing (Join-Path $srcPath 'components\ui\alert-dialog.tsx') @'
import type { ReactNode } from "react"
export function AlertDialog({ children, open }: { children?: ReactNode; open?: boolean }) { if (!open) return null; return <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,.4)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000 }}>{children}</div> }
export function AlertDialogContent({ children }: { children?: ReactNode }) { return <div style={{ background:"#fff",borderRadius:8,padding:24,minWidth:320 }}>{children}</div> }
export function AlertDialogHeader({ children }: { children?: ReactNode }) { return <div style={{ marginBottom:12 }}>{children}</div> }
export function AlertDialogFooter({ children }: { children?: ReactNode }) { return <div style={{ display:"flex",gap:8,justifyContent:"flex-end",marginTop:16 }}>{children}</div> }
export function AlertDialogTitle({ children }: { children?: ReactNode }) { return <h3 style={{ margin:0 }}>{children}</h3> }
export function AlertDialogDescription({ children }: { children?: ReactNode }) { return <p>{children}</p> }
export function AlertDialogAction({ children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...p}>{children}</button> }
export function AlertDialogCancel({ children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...p}>{children}</button> }
'@

$plan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    systemDirectory = $SystemDirectory
    backend = [ordered]@{
        source = "baseline-first+import-inference"
        baselineFile = $baselineFile
        imports = @($pythonImports | Sort-Object)
        requirementsPath = "backend\requirements.txt"
        requirements = @($requirementLines)
    }
    frontend = [ordered]@{
        source = "inferred-from-frontend-imports"
        imports = @($frontendImports | Sort-Object)
        packageJsonPath = "frontend\package.json"
        dependencies = $dependencies
        devDependencies = $devDependencies
    }
}

[System.IO.File]::WriteAllText((Join-Path $systemPath "dependency-plan.json"), ($plan | ConvertTo-Json -Depth 20), $utf8NoBom)

Write-Host "Dependency files generated in $SystemDirectory"
