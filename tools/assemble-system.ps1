param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\mvp-resolved-plan.json",
    [string]$SourceSystemDirectory = "generated\mvp-import-flow\form-analysis-server",
    [string]$OutputDirectory = "dist\generated-system",
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function New-CleanDirectory([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force $Path | Out-Null
}

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path $Source)) {
        throw "Source not found: $Source"
    }
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Test-RelativePath([string]$Root, [string]$RelativePath) {
    return Test-Path (Join-Path $Root $RelativePath)
}

$plan = Read-JsonUtf8 (Join-Path $ProjectRoot $ResolvedPlanPath)
$sourcePath = Join-Path $ProjectRoot $SourceSystemDirectory
$outputPath = Join-Path $ProjectRoot $OutputDirectory

New-CleanDirectory $outputPath
Copy-Tree (Join-Path $sourcePath "backend") (Join-Path $outputPath "backend")
Copy-Tree (Join-Path $sourcePath "frontend") (Join-Path $outputPath "frontend")

# Keep generated backend compatible with Python 3.10 deployments.
Get-ChildItem -LiteralPath (Join-Path $outputPath "backend") -Recurse -File -Filter *.py | ForEach-Object {
    $content = [string](Get-Content -Raw -Encoding UTF8 $_.FullName)
    $updated = $content.Replace("from datetime import UTC, datetime", "from datetime import datetime, timezone").Replace("datetime.now(UTC)", "datetime.now(timezone.utc)")
    $updated = $updated.Replace("from enum import StrEnum", "from enum import Enum")
    $updated = [regex]::Replace($updated, "class ([A-Za-z_][A-Za-z0-9_]*)\(StrEnum\):", 'class $1(str, Enum):')
    $updated = [regex]::Replace(
        $updated,
        '(?m)^    mode = \(getattr\(settings, "auth_mode", "off"\) or "off"\)\.strip\(\)\.lower\(\)\r?\n    if mode != "api_key":',
        "    if request.method.upper() == `"OPTIONS`":`n        return await call_next(request)`n`n    mode = (getattr(settings, `"auth_mode`", `"off`") or `"off`").strip().lower()`n    if mode != `"api_key`":"
    )
    if (-not (Test-Path (Join-Path $outputPath "backend\app\models\core\audit_event.py"))) {
        $updated = [regex]::Replace($updated, "(?m)^from app\.models import \(\r?\n\s+AuditEvent,\r?\n\)\r?\n", "")
    }
    if ($updated -ne $content) {
        [System.IO.File]::WriteAllText($_.FullName, $updated, (New-Object System.Text.UTF8Encoding $false))
    }
}

$auditServicePath = Join-Path $outputPath "backend\app\services\audit_events.py"
if (-not (Test-Path $auditServicePath)) {
    @'
"""Best-effort audit event writer.

Generated packages may reference audit hooks even when persistent audit models are
not selected. Keep those hooks non-blocking in that configuration.
"""

from typing import Any


async def write_audit_event_best_effort(**_: Any) -> None:
    return None
'@ | Set-Content -Encoding UTF8 $auditServicePath
}

$rowEditModelPath = Join-Path $outputPath "backend\app\models\audit.py"
if (-not (Test-Path $rowEditModelPath)) {
    @'
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RowEdit(Base):
    __tablename__ = "row_edits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    table_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reason_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
'@ | Set-Content -Encoding UTF8 $rowEditModelPath
}

$configPath = Join-Path $outputPath "backend\app\config"
New-Item -ItemType Directory -Force $configPath | Out-Null
if (-not (Test-Path (Join-Path $configPath "__init__.py"))) {
    [System.IO.File]::WriteAllText((Join-Path $configPath "__init__.py"), "", (New-Object System.Text.UTF8Encoding $false))
}
if (-not (Test-Path (Join-Path $configPath "constants.py"))) {
    @'
import os

VALID_MATERIALS: list[str] = [
    item.strip()
    for item in os.environ.get("VALID_MATERIALS_CSV", "").split(",")
    if item.strip()
]
VALID_SLITTING_MACHINES: list[int] = [
    int(item.strip())
    for item in os.environ.get("VALID_SLITTING_MACHINES_CSV", "").split(",")
    if item.strip()
]


def get_material_list() -> list[str]:
    return VALID_MATERIALS


def get_slitting_machine_list() -> list[int]:
    return VALID_SLITTING_MACHINES
'@ | Set-Content -Encoding UTF8 (Join-Path $configPath "constants.py")
}

$recordModelPath = Join-Path $outputPath "backend\app\models\record.py"
if (-not (Test-Path $recordModelPath)) {
    @'
import uuid
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Enum as SAEnum, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.p2_item import P2Item
    from app.models.p3_item import P3Item


class DataType(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Record(Base):
    __tablename__ = "records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_no: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_type: Mapped[DataType] = mapped_column(SAEnum(DataType, name="datatype_enum"), nullable=False)
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    additional_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    machine_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mold_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    production_lot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    p2_items: Mapped[list["P2Item"]] = relationship("P2Item", back_populates="record", cascade="all, delete-orphan")
    p3_items: Mapped[list["P3Item"]] = relationship("P3Item", back_populates="record", cascade="all, delete-orphan")
'@ | Set-Content -Encoding UTF8 $recordModelPath
}

$p2ItemModelPath = Join-Path $outputPath "backend\app\models\p2_item.py"
if (-not (Test-Path $p2ItemModelPath)) {
    @'
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.record import Record


class P2Item(Base):
    __tablename__ = "p2_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    winder_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness1: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness2: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness3: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness4: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness5: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness6: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness7: Mapped[float | None] = mapped_column(Float, nullable=True)
    appearance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rough_edge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slitting_result: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="p2_items")
'@ | Set-Content -Encoding UTF8 $p2ItemModelPath
}

$p3ItemModelPath = Join-Path $outputPath "backend\app\models\p3_item.py"
if (-not (Test-Path $p3ItemModelPath)) {
    @'
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.record import Record


class P3Item(Base):
    __tablename__ = "p3_items"
    __table_args__ = (UniqueConstraint("record_id", "product_id", name="uq_p3_item_record_product"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    production_lot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    machine_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mold_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bottom_tape_lot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="p3_items")
'@ | Set-Content -Encoding UTF8 $p3ItemModelPath
}

$schemasPath = Join-Path $outputPath "backend\app\schemas"
if (-not (Test-Path $schemasPath)) {
    New-Item -ItemType Directory -Force $schemasPath | Out-Null
}

function Add-SchemaFileIfMissing([string]$Name, [string]$Content) {
    $path = Join-Path $schemasPath $Name
    if (-not (Test-Path $path)) {
        [System.IO.File]::WriteAllText($path, $Content, (New-Object System.Text.UTF8Encoding $false))
    }
}

Add-SchemaFileIfMissing "__init__.py" ""
Add-SchemaFileIfMissing "upload.py" @'
import uuid
from pydantic import BaseModel


class UploadErrorResponse(BaseModel):
    row_index: int
    field: str
    error_code: str
    message: str


class FileUploadResponse(BaseModel):
    process_id: uuid.UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    sample_errors: list[UploadErrorResponse]


class UpdateUploadContentRequest(BaseModel):
    csv_text: str
    reason_id: str | None = None
    reason_text: str | None = None
'@
Add-SchemaFileIfMissing "validate.py" @'
import uuid
from datetime import datetime
from pydantic import BaseModel


class ErrorItem(BaseModel):
    row_index: int
    field: str
    error_code: str
    message: str


class ErrorNotFoundResponse(BaseModel):
    detail: str
    process_id: str
    error_code: str


class ValidateResult(BaseModel):
    job_id: uuid.UUID
    process_id: uuid.UUID
    filename: str
    status: str
    created_at: datetime
    statistics: dict
    errors: list[ErrorItem]
    pagination: dict
'@
Add-SchemaFileIfMissing "import_data.py" @'
import uuid
from pydantic import BaseModel


class ImportRequest(BaseModel):
    process_id: uuid.UUID


class ImportResponse(BaseModel):
    imported_rows: int
    skipped_rows: int
    elapsed_ms: int
    message: str
    process_id: uuid.UUID


class ImportErrorResponse(BaseModel):
    detail: str
    process_id: str
    error_code: str
'@
Add-SchemaFileIfMissing "audit.py" @'
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class RowEditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    table_code: str
    record_id: uuid.UUID
    reason_id: str | None = None
    reason_text: str | None = None
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    created_by: str | None = None
    created_at: datetime
'@
Add-SchemaFileIfMissing "import_job.py" @'
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class ImportFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_hash: str
    file_size: int
    row_count: int
    created_at: datetime


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    table_id: uuid.UUID
    batch_id: str
    status: str
    progress: int
    total_files: int
    total_rows: int
    error_count: int
    error_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    actor_label_snapshot: str | None = None
    last_status_changed_at: datetime | None = None
    last_status_actor_kind: str | None = None
    last_status_actor_label_snapshot: str | None = None
    files: list[ImportFileRead] = []


class ImportJobErrorRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_index: int
    is_valid: bool
    parsed_json: dict[str, Any]
    errors_json: list[dict[str, Any]] | None = None
'@
Add-SchemaFileIfMissing "pdf_conversion.py" @'
import uuid
from enum import Enum
from typing import Any
from pydantic import BaseModel

from app.schemas.upload import UploadErrorResponse


class PdfConversionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PdfConvertTriggerRequest(BaseModel):
    winder_number: int | None = None


class PdfConvertTriggerResponse(BaseModel):
    job_id: uuid.UUID
    status: PdfConversionStatus


class PdfConvertStatusResponse(BaseModel):
    status: PdfConversionStatus
    job_id: uuid.UUID | None = None
    progress: int = 0
    external_job_id: str | None = None
    output_path: str | None = None
    output_paths: list[str] | None = None
    error_summary: dict[str, Any] | None = None


class PdfConvertIngestedUpload(BaseModel):
    filename: str
    process_id: uuid.UUID
    import_job_id: uuid.UUID | None = None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    sample_errors: list[UploadErrorResponse]
    csv_text: str | None = None


class PdfConvertIngestResponse(BaseModel):
    uploads: list[PdfConvertIngestedUpload]


class PdfConvertOutputFile(BaseModel):
    filename: str
    csv_text: str | None = None


class PdfConvertOutputsResponse(BaseModel):
    outputs: list[PdfConvertOutputFile]
'@

$assemblyIrPackagePath = "assembly\assembly-ir.json"
$assemblyIrPath = Join-Path $OutputDirectory $assemblyIrPackagePath
& (Join-Path $ProjectRoot "tools\generate-assembly-ir.ps1") `
    -ProjectRoot $ProjectRoot `
    -ResolvedPlanPath $ResolvedPlanPath `
    -OutputPath $assemblyIrPath

& (Join-Path $ProjectRoot "tools\generate-backend-registry.ps1") `
    -ProjectRoot $ProjectRoot `
    -ResolvedPlanPath $ResolvedPlanPath `
    -IRPath $assemblyIrPath `
    -OutputDirectory (Join-Path $OutputDirectory "assembly\backend-registry")

& (Join-Path $ProjectRoot "tools\generate-frontend-registry.ps1") `
    -ProjectRoot $ProjectRoot `
    -IRPath $assemblyIrPath `
    -OutputDirectory (Join-Path $OutputDirectory "assembly\frontend-registry")

& (Join-Path $ProjectRoot "tools\generate-dependency-files.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory `
    -BaselinePath (Join-Path $ProjectRoot "assembly\baselines\default-requirements.baseline.json")

# Build frontend production bundle (result: frontend/dist/)
# Must run after generate-dependency-files.ps1 which creates package.json + tsconfig
$frontendDir = Join-Path $outputPath "frontend"
if (Test-Path (Join-Path $frontendDir "package.json")) {
    Write-Host "Building frontend (npm install + npm run build)..."
    Push-Location $frontendDir
    try {
        & npm install --silent
        if ($LASTEXITCODE -ne 0) { throw "npm install failed in $frontendDir" }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed in $frontendDir" }
    } finally {
        Pop-Location
    }
    $nodeModulesPath = Join-Path $frontendDir "node_modules"
    if (Test-Path $nodeModulesPath) {
        Remove-Item -LiteralPath $nodeModulesPath -Recurse -Force
    }
    Write-Host "Frontend built -> $frontendDir\dist\"
}

& (Join-Path $ProjectRoot "tools\generate-model-init.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory

$scriptsPath = Join-Path $outputPath "scripts"
New-Item -ItemType Directory -Force $scriptsPath | Out-Null

$kitsOutputPath = Join-Path $outputPath "kits"
New-Item -ItemType Directory -Force $kitsOutputPath | Out-Null
foreach ($kitId in @($plan.resolvedKitOrder)) {
    $kitSourcePath = Join-Path $ProjectRoot "kits\$kitId"
    $kitDestinationPath = Join-Path $kitsOutputPath $kitId
    Copy-Tree $kitSourcePath $kitDestinationPath
}

$assemblyIrFullPath = Join-Path $ProjectRoot $assemblyIrPath
$assemblyIr = Read-JsonUtf8 $assemblyIrFullPath
$kitInstallPlanPath = Join-Path $outputPath "kitInstallPlan.json"
@($assemblyIr.kitInstallPlan) | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $kitInstallPlanPath

@'
param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$planPath = Join-Path $Root "kitInstallPlan.json"
if (-not (Test-Path $planPath)) {
    throw "Kit install plan not found: $planPath"
}

$plan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
foreach ($entry in @($plan | Sort-Object order)) {
    $scriptPath = Join-Path $Root "kits\$($entry.kit)\install.ps1"
    if (-not (Test-Path $scriptPath)) {
        throw "Kit install script not found: $scriptPath"
    }

    Write-Host "Running kit install: $($entry.kit)"
    & powershell -ExecutionPolicy Bypass -File $scriptPath -Root $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Kit install failed for $($entry.kit) with exit code $LASTEXITCODE."
    }
}

Write-Host "Kit install plan completed."
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "run-kit-installs.ps1")

& (Join-Path $ProjectRoot "tools\generate-db-bootstrap.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory `
    -BaselinePath (Join-Path $ProjectRoot "assembly\baselines\default-db-schema.baseline.json")

$dependencyManifest = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    backend = [ordered]@{
        appEntry = "backend\app\main.py"
        requirementsTxt = Test-RelativePath $outputPath "backend\requirements.txt"
        pyprojectToml = Test-RelativePath $outputPath "backend\pyproject.toml"
        alembicIni = Test-RelativePath $outputPath "backend\alembic.ini"
        migrationDirectory = Test-RelativePath $outputPath "backend\alembic"
        installCommand = "python -m pip install -r backend\requirements.txt"
        startCommand = "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    }
    frontend = [ordered]@{
        sourceDirectory = "frontend"
        packageJson = Test-RelativePath $outputPath "frontend\package.json"
        installCommand = "npm install"
        startCommand = "npm run dev"
    }
    notes = @(
        "Dependency files are inferred from generated backend/frontend imports when source manifests are missing.",
        "If backend requirements.txt or pyproject.toml is missing, install.ps1 stops with an actionable error.",
        "If frontend package.json is missing, frontend install/start is skipped unless -WithFrontend is requested."
    )
}
$dependencyManifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $outputPath "dependency-manifest.json")

@'
param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Test-RelativePath([string]$Base, [string]$RelativePath) {
    return Test-Path (Join-Path $Base $RelativePath)
}

$checks = [ordered]@{
    backendApp = Test-RelativePath $Root "backend\app\main.py"
    backendRequirements = Test-RelativePath $Root "backend\requirements.txt"
    backendPyproject = Test-RelativePath $Root "backend\pyproject.toml"
    backendAlembic = Test-RelativePath $Root "backend\alembic.ini"
    frontendPackage = Test-RelativePath $Root "frontend\package.json"
    envExample = Test-RelativePath $Root ".env.example"
    dependencyManifest = Test-RelativePath $Root "dependency-manifest.json"
}

$summary = [ordered]@{
    root = $Root
    checks = $checks
    backendDependencyManifestPresent = ($checks.backendRequirements -or $checks.backendPyproject)
    frontendDependencyManifestPresent = $checks.frontendPackage
}

$summary | ConvertTo-Json -Depth 10

if (-not $checks.backendApp) {
    throw "Backend entry is missing: backend\app\main.py"
}

if ($Strict -and -not ($checks.backendRequirements -or $checks.backendPyproject)) {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml to the extracted source or dependency planner."
}

if ($Strict -and -not $checks.frontendPackage) {
    throw "Frontend dependency manifest is missing. Add frontend\package.json to enable frontend install/start."
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "check-prerequisites.ps1")

$askAuth = (($plan.resolvedKitOrder -contains "tenant-auth-kit") -or ($plan.featureFlags.AUTH_MODE -eq "api_key")).ToString().ToLowerInvariant()
$askPdf = ([bool](($plan.selectedExternalServices | Where-Object { $_.config -eq "PDF_SERVER_URL" }) -or ($plan.selectedSubfeatures."upload-validation-kit" -contains "pdf-to-csv-binding"))).ToString().ToLowerInvariant()
$askValidation = ($plan.resolvedKitOrder -contains "upload-validation-kit").ToString().ToLowerInvariant()

$configureEnvScript = @'
param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$AskAuth = [System.Convert]::ToBoolean("__ASK_AUTH__")
$AskPdf = [System.Convert]::ToBoolean("__ASK_PDF__")
$AskValidation = [System.Convert]::ToBoolean("__ASK_VALIDATION__")

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
'@

$configureEnvScript = $configureEnvScript.Replace("__ASK_AUTH__", $askAuth).Replace("__ASK_PDF__", $askPdf).Replace("__ASK_VALIDATION__", $askValidation)

[System.IO.File]::WriteAllText(
    (Join-Path $scriptsPath "configure-env.ps1"),
    $configureEnvScript,
    (New-Object System.Text.UTF8Encoding $false)
)

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$requirements = Join-Path $Root "backend\requirements.txt"
$pyproject = Join-Path $Root "backend\pyproject.toml"
$frontendPackage = Join-Path $Root "frontend\package.json"

if (Test-Path $requirements) {
    Write-Host "Installing backend dependencies from backend\requirements.txt"
    & $Python -m pip install -r $requirements
} elseif (Test-Path $pyproject) {
    Write-Host "Installing backend project from backend\pyproject.toml"
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m pip install .
    } finally {
        Pop-Location
    }
} else {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml before running install."
}

if (-not $SkipFrontend) {
    if (Test-Path $frontendPackage) {
        Write-Host "Installing frontend dependencies from frontend\package.json"
        Push-Location (Join-Path $Root "frontend")
        try {
            & $Npm install
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "frontend\package.json is missing; skipping frontend install."
    }
}

Write-Host "Install step completed."
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "install.ps1")

@'
param(
    [string]$Python = "python",
    [int]$BackendPort = 8000,
    [int]$TimeoutSeconds = 15,
    [switch]$ImportApp,
    [switch]$StartBackend
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$BackendRoot = Join-Path $Root "backend"

function Invoke-CheckedNative([scriptblock]$Command, [string]$FailureMessage) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root -Strict | Out-Host

$requiredPaths = @(
    "backend\app\main.py",
    "backend\app\models\__init__.py",
    "backend\requirements.txt",
    "frontend\package.json",
    "scripts\start.ps1"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $Root $relativePath))) {
        throw "Missing smoke-start path: $relativePath"
    }
}

$pythonFiles = Get-ChildItem -LiteralPath (Join-Path $BackendRoot "app") -Recurse -Filter *.py | ForEach-Object { $_.FullName }
if ($pythonFiles.Count -eq 0) {
    throw "No backend Python files found for compile smoke."
}
Invoke-CheckedNative { & $Python -m py_compile @pythonFiles } "Backend Python compile smoke failed."

$startScript = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "scripts\start.ps1")
if ($startScript -notmatch "uvicorn app\.main:app") {
    throw "scripts\start.ps1 does not start uvicorn app.main:app."
}

$result = [ordered]@{
    root = $Root
    pythonFilesCompiled = $pythonFiles.Count
    importAppRequested = [bool]$ImportApp
    startBackendRequested = [bool]$StartBackend
}

if ($ImportApp -or $StartBackend) {
    $envPath = Join-Path $Root ".env"
    $envExamplePath = Join-Path $Root ".env.example"
    if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
        Copy-Item -LiteralPath $envExamplePath -Destination $envPath
        Write-Host "Created .env from .env.example"
    }
}

if ($ImportApp) {
    Push-Location $BackendRoot
    try {
        Invoke-CheckedNative { & $Python -c "import app.main; print(app.main.app.title)" } "Generated FastAPI app import smoke failed."
    } finally {
        Pop-Location
    }
}

if ($StartBackend) {
    Push-Location $BackendRoot
    try {
        $process = Start-Process $Python -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", [string]$BackendPort
        ) -WindowStyle Hidden -PassThru

        try {
            $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
            $healthy = $false
            while ((Get-Date) -lt $deadline) {
                if ($process.HasExited) {
                    throw "Backend process exited early with code $($process.ExitCode)."
                }
                try {
                    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/healthz" -TimeoutSec 2
                    if ($response.status -eq "healthy") {
                        $healthy = $true
                        break
                    }
                } catch {
                    Start-Sleep -Milliseconds 500
                }
            }
            if (-not $healthy) {
                throw "Backend health endpoint did not become healthy within $TimeoutSeconds seconds."
            }
            $result.backendHealth = "healthy"
        } finally {
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
            }
        }
    } finally {
        Pop-Location
    }
}

$result | ConvertTo-Json -Depth 10
Write-Host "OK smoke-start"
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "smoke-start.ps1")

@'
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

$alembicIni = Join-Path $Root "backend\alembic.ini"
if (Test-Path $alembicIni) {
    Write-Host "Running Alembic migrations."
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m alembic upgrade head
    } finally {
        Pop-Location
    }
} else {
    $bootstrapModule = Join-Path $Root "backend\app\core\generated_db_bootstrap.py"
    if (Test-Path $bootstrapModule) {
        Write-Host "Alembic is missing; running generated SQLAlchemy bootstrap."
        Push-Location (Join-Path $Root "backend")
        try {
            & $Python -m app.core.generated_db_bootstrap
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "backend\alembic.ini and generated_db_bootstrap.py are missing; no migration command was run."
    }
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "migrate.ps1")

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $RuntimePath | Out-Null
New-Item -ItemType Directory -Force $LogPath | Out-Null

function Test-RunningPid([string]$PidPath) {
    if (-not (Test-Path $PidPath)) {
        return $false
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $PidPath).Trim()
    if ([string]::IsNullOrWhiteSpace($rawPid)) {
        return $false
    }

    try {
        $process = Get-Process -Id ([int]$rawPid) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

if ($Background) {
    $backendPidPath = Join-Path $RuntimePath "backend.pid"
    if (Test-RunningPid $backendPidPath) {
        throw "Backend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
    }

    $backendOut = Join-Path $LogPath "backend.out.log"
    $backendErr = Join-Path $LogPath "backend.err.log"
    $backendProcess = Start-Process $Python -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--host", $HostAddress,
        "--port", [string]$BackendPort
    ) -WorkingDirectory (Join-Path $Root "backend") `
      -WindowStyle Hidden `
      -RedirectStandardOutput $backendOut `
      -RedirectStandardError $backendErr `
      -PassThru
    [string]$backendProcess.Id | Set-Content -Encoding UTF8 $backendPidPath

    $frontendPid = $null
    if ($WithFrontend) {
        $frontendPackage = Join-Path $Root "frontend\package.json"
        if (-not (Test-Path $frontendPackage)) {
            throw "Cannot start frontend because frontend\package.json is missing."
        }

        $frontendPidPath = Join-Path $RuntimePath "frontend.pid"
        if (Test-RunningPid $frontendPidPath) {
            throw "Frontend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
        }

        $frontendOut = Join-Path $LogPath "frontend.out.log"
        $frontendErr = Join-Path $LogPath "frontend.err.log"
        $frontendProcess = Start-Process $Npm -ArgumentList @("run", "dev") `
          -WorkingDirectory (Join-Path $Root "frontend") `
          -WindowStyle Hidden `
          -RedirectStandardOutput $frontendOut `
          -RedirectStandardError $frontendErr `
          -PassThru
        [string]$frontendProcess.Id | Set-Content -Encoding UTF8 $frontendPidPath
        $frontendPid = $frontendProcess.Id
    }

    [ordered]@{
        backend = [ordered]@{
            pid = $backendProcess.Id
            url = "http://$HostAddress`:$BackendPort"
            stdout = "logs\backend.out.log"
            stderr = "logs\backend.err.log"
        }
        frontend = [ordered]@{
            requested = [bool]$WithFrontend
            pid = $frontendPid
            stdout = if ($WithFrontend) { "logs\frontend.out.log" } else { $null }
            stderr = if ($WithFrontend) { "logs\frontend.err.log" } else { $null }
        }
    } | ConvertTo-Json -Depth 10

    Write-Host "Background processes started. Use scripts\status.ps1 to inspect them."
    return
}

if ($WithFrontend) {
    $frontendPackage = Join-Path $Root "frontend\package.json"
    if (-not (Test-Path $frontendPackage)) {
        throw "Cannot start frontend because frontend\package.json is missing."
    }

    Write-Host "Starting frontend dev server in a new PowerShell process."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$Root\frontend'; $Npm run dev"
    ) -WindowStyle Hidden | Out-Null
}

Write-Host "Starting backend on http://$HostAddress`:$BackendPort"
Push-Location (Join-Path $Root "backend")
try {
    & $Python -m uvicorn app.main:app --host $HostAddress --port $BackendPort
} finally {
    Pop-Location
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "start.ps1")

@'
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"

function Get-ServiceStatus([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $pidValue = $null
    $running = $false

    if (Test-Path $pidPath) {
        $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
        if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
            $pidValue = [int]$rawPid
            try {
                Get-Process -Id $pidValue -ErrorAction Stop | Out-Null
                $running = $true
            } catch {
                $running = $false
            }
        }
    }

    return [ordered]@{
        pid = $pidValue
        running = $running
        pidFile = "runtime\$Name.pid"
        stdout = "logs\$Name.out.log"
        stderr = "logs\$Name.err.log"
        stdoutExists = Test-Path (Join-Path $LogPath "$Name.out.log")
        stderrExists = Test-Path (Join-Path $LogPath "$Name.err.log")
    }
}

[ordered]@{
    root = $Root
    backend = Get-ServiceStatus "backend"
    frontend = Get-ServiceStatus "frontend"
} | ConvertTo-Json -Depth 10
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "status.ps1")

@'
param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"

function Stop-ServiceByPidFile([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $result = [ordered]@{
        name = $Name
        pid = $null
        stopped = $false
        wasRunning = $false
    }

    if (-not (Test-Path $pidPath)) {
        return $result
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
    if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
        $result.pid = [int]$rawPid
        try {
            $process = Get-Process -Id $result.pid -ErrorAction Stop
            $result.wasRunning = $true
            Stop-Process -Id $process.Id -Force
            $result.stopped = $true
        } catch {
            $result.wasRunning = $false
        }
    }

    Remove-Item -LiteralPath $pidPath -Force
    return $result
}

$results = New-Object System.Collections.Generic.List[object]
if (-not $FrontendOnly) {
    $results.Add((Stop-ServiceByPidFile "backend"))
}
if (-not $BackendOnly) {
    $results.Add((Stop-ServiceByPidFile "frontend"))
}

[ordered]@{
    root = $Root
    results = $results.ToArray()
} | ConvertTo-Json -Depth 10
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "stop.ps1")

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop.ps1") | Out-Host
& (Join-Path $PSScriptRoot "start.ps1") `
    -Python $Python `
    -Npm $Npm `
    -HostAddress $HostAddress `
    -BackendPort $BackendPort `
    -WithFrontend:$WithFrontend `
    -Background
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "restart.ps1")

@"
DB_HOST=localhost
DB_PORT=5432
DB_NAME=form_system
DB_USERNAME=form_system
DB_PASSWORD=
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/form_system
# Local dev without PostgreSQL - use SQLite instead:
# DATABASE_URL=sqlite+aiosqlite:///./form_db.sqlite
SECRET_KEY=
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
AUTH_MODE=api_key
ADMIN_API_KEYS=
BOOTSTRAP_MANAGER_ENABLED=false
BOOTSTRAP_MANAGER_TENANT_CODE=
BOOTSTRAP_MANAGER_USERNAME=
BOOTSTRAP_MANAGER_PASSWORD=
BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD=true
MULTI_TENANT_ENABLED=true
AUDIT_EVENTS_ENABLED=false
USE_GENERIC_SCHEMA=false
PDF_SERVER_URL=
PDF_SERVER_TIMEOUT_SECONDS=1800
PDF_SERVER_MAX_CONCURRENT=3
PDF_SERVER_TABLE=
VALID_MATERIALS_CSV=
VALID_SLITTING_MACHINES_CSV=
ENTITLEMENT_MODE=local
ENVIRONMENT=production
"@ | Set-Content -Encoding UTF8 (Join-Path $outputPath ".env.example")

$manifest = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourceRecipe = $plan.recipe
    resolvedKitOrder = $plan.resolvedKitOrder
    database = $plan.database
    scripts = @(
        "scripts\check-prerequisites.ps1",
        "scripts\check-db.ps1",
        "scripts\configure-env.ps1",
        "scripts\install.ps1",
        "scripts\migrate.ps1",
        "scripts\smoke-start.ps1",
        "scripts\status.ps1",
        "scripts\stop.ps1",
        "scripts\restart.ps1",
        "scripts\start.ps1"
    )
    dependencyManifest = "dependency-manifest.json"
    dependencyPlan = "dependency-plan.json"
    dbBootstrapPlan = "db-bootstrap-plan.json"
    assemblyIr = $assemblyIrPackagePath
    status = "runnable-envelope"
}
$manifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $outputPath "package-manifest.json")

@'
# Generated System

This folder is generated by `tools/assemble-system.ps1`.

## First Run

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\configure-env.ps1
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\smoke-start.ps1
.\scripts\start.ps1 -Background
```

To also start the frontend dev server:

```powershell
.\scripts\start.ps1 -WithFrontend -Background
```

To inspect or stop background processes:

```powershell
.\scripts\status.ps1
.\scripts\stop.ps1
.\scripts\restart.ps1
```

## Runtime Contract

The package is a runnable envelope: selected source files, generated registries,
environment template, dependency manifest, and scripts are present.

Dependency files are generated from the selected backend and frontend imports.
Review `dependency-plan.json` before production deployment and pin exact
versions when the target runtime is decided.

Database bootstrap files are generated from `assembly\db-plan`. Run
`.\scripts\check-db.ps1` for structural validation, or
`.\scripts\check-db.ps1 -Connect` when a real database is available.

Run `.\scripts\smoke-start.ps1` before startup to compile the backend and
verify that start scripts are wired. After dependencies are installed, add
`-ImportApp`. With a real database available, add `-StartBackend` to verify
the `/healthz` endpoint.

Background processes write pid files to `runtime` and logs to `logs`.
'@ | Set-Content -Encoding UTF8 (Join-Path $outputPath "README.md")

if ($CreateZip) {
    $zipPath = "$outputPath.zip"
    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $outputPath "*") -DestinationPath $zipPath -Force
    Write-Host "Generated system zip written to $zipPath"
}

Write-Host "Generated system written to $outputPath"
