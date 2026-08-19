param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$modelsRoot = Join-Path $ProjectRoot (Join-Path $SystemDirectory "backend\app\models")
if (-not (Test-Path $modelsRoot)) {
    throw "Models directory is missing: $modelsRoot"
}

$exports = New-Object System.Collections.Generic.List[string]

function Add-Export([string]$Path, [string]$ImportLine, [string[]]$Names) {
    if (Test-Path (Join-Path $modelsRoot $Path)) {
        $script:lines.Add($ImportLine)
        foreach ($name in $Names) {
            if (-not $exports.Contains($name)) {
                $exports.Add($name)
            }
        }
    }
}

$script:lines = New-Object System.Collections.Generic.List[string]
$script:lines.Add('"""Generated model package exports for the selected recipe."""')
$script:lines.Add('')

Add-Export "core\audit_event.py" "from .core.audit_event import AuditEvent" @("AuditEvent")
Add-Export "core\tenant.py" "from .core.tenant import Tenant" @("Tenant")
Add-Export "core\tenant_user.py" "from .core.tenant_user import TenantUser" @("TenantUser")
Add-Export "core\tenant_api_key.py" "from .core.tenant_api_key import TenantApiKey" @("TenantApiKey")
Add-Export "core\schema_registry.py" "from .core.schema_registry import SchemaVersion, TableRegistry" @("SchemaVersion", "TableRegistry")
Add-Export "station.py" "from .station import Station, StationLink, StationSchema" @("Station", "StationLink", "StationSchema")
Add-Export "validation_rule.py" "from .validation_rule import ValidationRule" @("ValidationRule")
Add-Export "analytics_mapping.py" "from .analytics_mapping import AnalyticsMapping" @("AnalyticsMapping")
Add-Export "audit.py" "from .audit import RowEdit" @("RowEdit")
Add-Export "generic_record.py" "from .generic_record import GenericRecord, GenericRecordItem" @("GenericRecord", "GenericRecordItem")
Add-Export "record.py" "from .record import DataType, Record" @("DataType", "Record")
Add-Export "p1_record.py" "from .p1_record import P1Record" @("P1Record")
Add-Export "p2_item.py" "from .p2_item import P2Item" @("P2Item")
Add-Export "p2_record.py" "from .p2_record import P2Record" @("P2Record")
Add-Export "p2_item_v2.py" "from .p2_item_v2 import P2ItemV2" @("P2ItemV2")
Add-Export "p3_item.py" "from .p3_item import P3Item" @("P3Item")
Add-Export "p3_record.py" "from .p3_record import P3Record" @("P3Record")
Add-Export "p3_item_v2.py" "from .p3_item_v2 import P3ItemV2" @("P3ItemV2")
Add-Export "upload_job.py" "from .upload_job import UploadJob" @("UploadJob")
Add-Export "upload_error.py" "from .upload_error import UploadError" @("UploadError")
Add-Export "pdf_upload.py" "from .pdf_upload import PdfUpload" @("PdfUpload")
Add-Export "pdf_conversion_job.py" "from .pdf_conversion_job import PdfConversionJob" @("PdfConversionJob")
Add-Export "import_job.py" "from .import_job import ImportFile, ImportJob, StagingRow" @("ImportFile", "ImportJob", "StagingRow")
Add-Export "flow_trace.py" "from .flow_trace import FlowKeyAlias, FlowRun, TraceChain, TraceChainStep" @("FlowKeyAlias", "FlowRun", "TraceChain", "TraceChainStep")

$script:lines.Add('')
$script:lines.Add('__all__ = [')
foreach ($name in $exports) {
    $script:lines.Add("    `"$name`",")
}
$script:lines.Add(']')

$initPath = Join-Path $modelsRoot "__init__.py"
$script:lines -join [Environment]::NewLine | Set-Content -Encoding UTF8 $initPath

Write-Host "Generated model exports at $initPath"
