param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedAppRoot = "generated\mvp-import-flow\form-analysis-server"
)

$ErrorActionPreference = "Stop"

& (Join-Path $ProjectRoot "tools\apply-upload-page-refactor.ps1") `
    -ProjectRoot $ProjectRoot `
    -GeneratedAppRoot $GeneratedAppRoot

$frontendRoot = Join-Path $ProjectRoot (Join-Path $GeneratedAppRoot "frontend")
$uploadPagePath = Join-Path $frontendRoot "src\pages\UploadPage.tsx"
$moduleRoot = Join-Path $frontendRoot "src\pages\upload"

$requiredPaths = @(
    "uploadTypes.ts",
    "uploadFileAddUtils.ts",
    "uploadFileAddToastUtils.ts",
    "uploadAsyncUtils.ts",
    "uploadFileUtils.ts",
    "uploadCsvEditUtils.ts",
    "uploadCsvEditToastUtils.ts",
    "uploadEligibility.ts",
    "uploadProgress.ts",
    "uploadApiClient.ts",
    "uploadBatchOrchestrator.ts",
    "uploadPdfConversionOrchestrator.ts",
    "uploadPdfConvertToastUtils.ts",
    "uploadValidationOrchestrator.ts",
    "uploadValidationErrorUtils.ts",
    "uploadValidationToastUtils.ts",
    "uploadImportToastUtils.ts",
    "uploadImportCleanupUtils.ts",
    "useUploadApi.ts",
    "useUploadWorkflow.ts",
    "FileDropArea.tsx",
    "BatchActionBar.tsx",
    "BatchImportConfirmModal.tsx",
    "UploadedFileCard.tsx"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $moduleRoot $relativePath))) {
        throw "Missing UploadPage refactor module: $relativePath"
    }
}

$uploadPage = Get-Content -Raw -Encoding UTF8 $uploadPagePath
$types = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadTypes.ts")
$fileAddUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadFileAddUtils.ts")
$fileAddToastUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadFileAddToastUtils.ts")
$asyncUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadAsyncUtils.ts")
$utils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadFileUtils.ts")
$csvEditUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadCsvEditUtils.ts")
$csvEditToastUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadCsvEditToastUtils.ts")
$eligibility = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadEligibility.ts")
$progress = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadProgress.ts")
$apiClient = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadApiClient.ts")
$batchOrchestrator = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadBatchOrchestrator.ts")
$pdfConversionOrchestrator = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadPdfConversionOrchestrator.ts")
$pdfConvertToastUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadPdfConvertToastUtils.ts")
$validationOrchestrator = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationOrchestrator.ts")
$validationErrorUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationErrorUtils.ts")
$validationToastUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationToastUtils.ts")
$importToastUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadImportToastUtils.ts")
$importCleanupUtils = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "uploadImportCleanupUtils.ts")
$uploadApiHook = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "useUploadApi.ts")
$workflow = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "useUploadWorkflow.ts")
$fileDropArea = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "FileDropArea.tsx")
$batchActionBar = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "BatchActionBar.tsx")
$batchImportConfirmModal = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "BatchImportConfirmModal.tsx")
$uploadedFileCard = Get-Content -Raw -Encoding UTF8 (Join-Path $moduleRoot "UploadedFileCard.tsx")

if ($uploadPage -notmatch "uploadFileUtils" -or $uploadPage -notmatch "uploadTypes" -or $uploadPage -notmatch "uploadProgress" -or $uploadPage -notmatch "useUploadApi" -or $uploadPage -notmatch "useUploadWorkflow" -or $uploadPage -notmatch "uploadEligibility") {
    throw "UploadPage does not import extracted upload modules."
}

if ($uploadPage -notmatch "uploadFileAddUtils") {
    throw "UploadPage does not import extracted file-add helper."
}

if ($uploadPage -notmatch "uploadFileAddToastUtils") {
    throw "UploadPage does not import extracted file-add toast helper."
}

if ($uploadPage -notmatch "uploadAsyncUtils") {
    throw "UploadPage does not import extracted async helper."
}

$asyncImportCount = ([regex]::Matches($uploadPage, 'import \{ delay[^}]* \} from "\./upload/uploadAsyncUtils";')).Count
if ($asyncImportCount -ne 1) {
    throw "UploadPage should import uploadAsyncUtils exactly once."
}
if ($uploadPage -match "scheduleAfterDelay" -and $uploadPage -notmatch 'import \{ delay \} from "\./upload/uploadAsyncUtils"') {
    throw "UploadPage still imports scheduleAfterDelay directly after Phase 24 extraction."
}

if ($pdfConversionOrchestrator -notmatch "buildUploadedCsvFilesFromPdfOutputs") {
    throw "uploadPdfConversionOrchestrator does not use extracted PDF output CSV file builder."
}

if ($uploadPage -match "\bbuildUploadedCsvFilesFromPdfOutputs\b") {
    throw "UploadPage still owns buildUploadedCsvFilesFromPdfOutputs; expected in orchestrator."
}

if ($uploadPage -notmatch "uploadBatchOrchestrator") {
    throw "UploadPage does not import extracted batch orchestration helpers."
}

if ($uploadPage -notmatch "uploadPdfConversionOrchestrator") {
    throw "UploadPage does not import extracted PDF conversion orchestration helper."
}

if ($uploadPage -notmatch "uploadPdfConvertToastUtils") {
    throw "UploadPage does not import extracted PDF conversion toast helper."
}

if ($uploadPage -notmatch "uploadCsvEditUtils") {
    throw "UploadPage does not import extracted CSV edit helpers."
}

if ($uploadPage -notmatch "uploadCsvEditToastUtils") {
    throw "UploadPage does not import extracted CSV edit toast helper."
}

if ($uploadPage -notmatch "uploadValidationOrchestrator") {
    throw "UploadPage does not import extracted validation helpers."
}

if ($uploadPage -notmatch "uploadValidationToastUtils") {
    throw "UploadPage does not import extracted validation toast helper."
}

if ($uploadPage -notmatch "uploadImportToastUtils") {
    throw "UploadPage does not import extracted import toast helper."
}

if ($uploadPage -notmatch "useUploadApi") {
    throw "UploadPage does not import extracted upload API hook."
}

if ($uploadPage -notmatch './upload/FileDropArea') {
    throw "UploadPage does not import extracted FileDropArea component."
}

if ($uploadPage -notmatch './upload/UploadedFileCard') {
    throw "UploadPage does not import extracted UploadedFileCard component."
}

if ($uploadPage -notmatch './upload/BatchActionBar') {
    throw "UploadPage does not import extracted BatchActionBar component."
}

if ($uploadPage -notmatch './upload/BatchImportConfirmModal') {
    throw "UploadPage does not import extracted BatchImportConfirmModal component."
}

if ($uploadPage -match "function FileDropArea" -or $uploadPage -match "interface FileDropAreaProps") {
    throw "UploadPage still owns FileDropArea component."
}

if ($uploadPage -match "function UploadedFileCard" -or $uploadPage -match "interface UploadedFileCardProps" -or $uploadPage -match "function CsvEditor" -or $uploadPage -match "interface CsvEditorProps") {
    throw "UploadPage still owns UploadedFileCard/CsvEditor component."
}

if ($uploadPage -match 'className="batch-actions"' -or $uploadPage -match "const eligibleCount = files\.filter\(fileEligibleForValidate\)" -or $uploadPage -match "const convertEligibleCount = files\.filter\(fileEligibleForConvert\)") {
    throw "UploadPage still owns batch action bar rendering logic."
}

if ($uploadPage -match 'className="batch-import-confirm"' -or $uploadPage -match "const validFilesWithoutErrors = files\.filter\(fileEligibleForBatchImport\)" -or $uploadPage -match "batch-import-confirm__list") {
    throw "UploadPage still owns batch import confirmation modal rendering logic."
}

if ($uploadPage -match "const targets = .*fileEligibleForValidate" -or $uploadPage -match "const targets = .*fileEligibleForConvert" -or $uploadPage -match "for \(let i = 0; i < targets\.length; i\+\+\)" -or $uploadPage -match "upload\.batchValidate\.toast\.doneWithFailures" -or $uploadPage -match "upload\.batchConvert\.toast\.doneWithFailures") {
    throw "UploadPage still owns batch validation/conversion orchestration."
}

if ($uploadPage -notmatch "runBatchValidation\(\{" -or $uploadPage -notmatch "runBatchConversion\(\{") {
    throw "UploadPage does not delegate batch validation/conversion orchestration."
}

if ($uploadPage -notmatch "runBatchImportWorkflow\(\{" -or $uploadPage -match "for \(const \[index, file\] of validatedFiles\.entries\(\)\)" -or $uploadPage -match "totalImported \+= Number\(committedJob\.total_rows") {
    throw "UploadPage does not delegate batch import commit/poll orchestration."
}

if ($uploadPage -notmatch "runSingleImportWorkflow\(\{") {
    throw "UploadPage does not delegate single import orchestration to runSingleImportWorkflow."
}

if ($uploadPage -match "runSingleImport\(\{" -or $uploadPage -match "setImportProgress\(id, 60\)" -or $uploadPage -match "setImportProgress\(id, toImportProgress\(committedJob\.status\)\)" -or $uploadPage -match "completeImport\(id\)") {
    throw "UploadPage still owns single import commit/poll details; expected in orchestrator."
}

if ($uploadPage -notmatch "runPdfConvertWorkflow\(\{") {
    throw "UploadPage does not delegate PDF conversion to runPdfConvertWorkflow."
}

if ($uploadPage -match "runPdfConversion\(\{" -or $uploadPage -match "const maxTries = 1800" -or $uploadPage -match "consecutiveErrors" -or $uploadPage -match "for \(let i = 0; i < maxTries; i\+\+\)" -or $uploadPage -match "uploadApi\.fetchPdfConvertStatus\(target\.processId\)") {
    throw "UploadPage still owns PDF conversion polling details; expected in orchestrator."
}

if ($pdfConversionOrchestrator -notmatch "export async function runPdfConvertWorkflow") {
    throw "uploadPdfConversionOrchestrator is missing runPdfConvertWorkflow."
}

if ($pdfConversionOrchestrator -notmatch "buildUploadedCsvFilesFromPdfOutputs" -or $pdfConversionOrchestrator -notmatch "beginPdfConvert\(fileId\)") {
    throw "uploadPdfConversionOrchestrator is missing expected runPdfConvertWorkflow internals."
}

if ($uploadPage -match "const buildCsvText =" -or $uploadPage -match "const shouldResetV2Job =" -or $uploadPage -match "csvData: \{ \.\.\.f\.csvData, rows \}" -or $uploadPage -match "new File\(\[csv_text\]" -or $uploadPage -match "const updatedFile = new File") {
    throw "UploadPage still owns CSV edit/save helper details."
}

if ($uploadPage -notmatch "buildUploadFilesToAdd\(\{" -or $uploadPage -match "const newFiles: UploadedFile\[\]" -or $uploadPage -match "lowerName\.endsWith" -or $uploadPage -match "isLikelyDuplicate" -or $uploadPage -match "file\.size > MAX_SIZE_BYTES" -or $uploadPage -match "detectFileType\(file\.name\)" -or $uploadPage -match "jobBackend: type === `"PDF`"") {
    throw "UploadPage does not delegate file-add workflow."
}

if ($uploadPage -notmatch "showFileAddResultToasts\(\{" -or $uploadPage -match "upload\.toast\.onlyCsvOrPdf" -or $uploadPage -match "upload\.toast\.fileAlreadyExists" -or $uploadPage -match "upload\.toast\.fileTooLarge" -or $uploadPage -match "upload\.toast\.filesAdded") {
    throw "UploadPage does not delegate file-add toast handling."
}

if ($uploadPage -notmatch "updateCsvCellInFiles\(prev, fileId, rowIndex, colIndex, value\)" -or $uploadPage -notmatch "saveCsvChangesInFiles\(files, fileId\)") {
    throw "UploadPage does not delegate CSV edit/save helper logic."
}

if ($uploadPage -notmatch "showCsvEditDisabledToast\(\{" -or $uploadPage -notmatch "showCsvSaveErrorToast\(\{" -or $uploadPage -notmatch "showCsvChangesAppliedToast\(\{" -or $uploadPage -match "upload\.toast\.changesAppliedRevalidate" -or $uploadPage -match "upload\.errors\.saveError") {
    throw "UploadPage does not delegate CSV edit/save toast handling."
}

if ($uploadPage -notmatch "runPdfValidation\(\{" -or $uploadPage -match "uploadApi\.uploadPdf\(target\.file, target\.name\)" -or $uploadPage -match "completePdfUpload\(fileId, data\.process_id\)" -or $uploadPage -match "failPdfValidation\(fileId\);\r?\n\s*const msg") {
    throw "UploadPage does not delegate PDF validation helper logic."
}

if ($uploadPage -notmatch "runCsvValidationJob\(\{" -or $uploadPage -match "const createImportJob = async \(allowDuplicate: boolean\)" -or $uploadPage -match "DUPLICATE_FILE_CONTENT" -or $uploadPage -match "const fileToUpload = target\.csvData" -or $uploadPage -match "for \(let i = 0; i < 120; i\+\+\)" -or $uploadPage -match "uploadApi\.fetchImportJob\(jobId\)") {
    throw "UploadPage does not delegate CSV validation job orchestration."
}

if ($uploadPage -match "\.flatMap\(\(row: any\)" -or $uploadPage -match "rowIndex0" -or $uploadPage -match "Row is invalid") {
    throw "UploadPage still owns validation error flattening logic."
}

if ($uploadPage -notmatch "showValidationResultToast," -or $uploadPage -match "upload\.toast\.pdfUploadedReadyToConvert" -or $uploadPage -match "upload\.toast\.validationFailedWithMessage" -or $uploadPage -match "upload\.toast\.validationDoneWithInvalidRowsNoEdit" -or $uploadPage -match "upload\.toast\.validationPassedAllRows") {
    throw "UploadPage does not delegate validation result toast handling."
}

if ($uploadPage -match "upload\.batchImport\.toast\.startSingle" -or $uploadPage -match "upload\.batchImport\.toast\.completedBatch" -or $uploadPage -match "upload\.batchImport\.toast\.allDone" -or $uploadPage -match "upload\.toast\.importStarting" -or $uploadPage -match "upload\.toast\.importCompleted" -or $uploadPage -match "upload\.toast\.pageResetContinueUpload") {
    throw "UploadPage still owns import result toast details."
}

if ($uploadPage -match "showSingleImportStartToast\(\{" -or $uploadPage -match "showSingleImportCompletedToast\(\{" -or $uploadPage -match "showImportErrorToast\(\{" -or $uploadPage -match "scheduleSinglePostImportCleanup\(\{") {
    throw "UploadPage still owns single import toast/cleanup helpers; expected in orchestrator."
}

if ($batchOrchestrator -notmatch "export async function runSingleImportWorkflow") {
    throw "uploadBatchOrchestrator is missing runSingleImportWorkflow."
}

if ($batchOrchestrator -notmatch "showSingleImportStartToast" -or $batchOrchestrator -notmatch "showSingleImportCompletedToast") {
    throw "uploadBatchOrchestrator is missing single import toast helpers."
}

if ($batchOrchestrator -notmatch "scheduleSinglePostImportCleanup") {
    throw "uploadBatchOrchestrator is missing scheduleSinglePostImportCleanup."
}

if ($uploadPage -match "showPdfConvertFetchingCsvToast\(\{" -or $uploadPage -match "showPdfConvertGotCsvToast\(\{" -or $uploadPage -match "showPdfConvertStillProcessingToast\(\{" -or $uploadPage -match "upload\.toast\.pdfConvertFetchingCsv" -or $uploadPage -match "upload\.toast\.pdfConvertGotCsv" -or $uploadPage -match "upload\.toast\.pdfConvertNoCsv" -or $uploadPage -match "upload\.toast\.pdfConvertStillProcessing" -or $uploadPage -match "upload\.toast\.missingProcessIdUploadPdf") {
    throw "UploadPage still owns PDF conversion toast helpers; expected in orchestrator."
}

if ($pdfConversionOrchestrator -notmatch "showPdfConvertFetchingCsvToast" -or $pdfConversionOrchestrator -notmatch "showPdfConvertGotCsvToast" -or $pdfConversionOrchestrator -notmatch "showPdfConvertStillProcessingToast") {
    throw "uploadPdfConversionOrchestrator is missing PDF conversion toast helpers."
}

if ($uploadPage -match 'import \{ ProgressBar \}') {
    throw "UploadPage still imports ProgressBar after card extraction."
}

if ([regex]::Matches($uploadPage, "uploadEligibility").Count -ne 1) {
    throw "UploadPage should import uploadEligibility exactly once."
}

if ($uploadPage -match "type FileType =") {
    throw "UploadPage still owns FileType; expected extracted type module."
}

foreach ($localPredicate in @(
    "const fileHasValidationErrors =",
    "const fileEligibleForValidate =",
    "const fileEligibleForConvert =",
    'f\.status === "validated" &&\s*f\.processId',
    'f\.status === "uploaded"',
    'f\.validationErrors &&\s*f\.validationErrors\.length > 0'
)) {
    if ($uploadPage -match $localPredicate) {
        throw "UploadPage still owns extracted eligibility predicate: $localPredicate"
    }
}

foreach ($predicateUsage in @(
    "fileEligibleForValidate",
    "fileEligibleForConvert",
    "fileEligibleForBatchImport",
    "fileHasBlockingImportErrors",
    "fileIsUploadedButUnvalidated",
    "fileHasImportJob"
)) {
    if ($uploadPage -notmatch $predicateUsage) {
        throw "UploadPage is missing extracted eligibility predicate usage: $predicateUsage"
    }
}

if ($uploadPage -match "const toValidateProgress =") {
    throw "UploadPage still owns progress mapping; expected extracted progress module."
}

if ($uploadPage -match "const fetchPdfConvertStatus =") {
    throw "UploadPage still owns PDF status API helper; expected extracted API client."
}

if ($uploadPage -match "useRef\(files\)" -or $uploadPage -match "useEffect\(\(\) => \{\s*filesRef\.current = files") {
    throw "UploadPage still owns filesRef synchronization; expected workflow hook."
}

if ($uploadPage -notmatch "const \{ files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles \} = useUploadWorkflow\(\)") {
    throw "UploadPage does not use the extracted upload workflow hook."
}

if ($uploadPage -notmatch "const handleToggleExpand = toggleFileExpanded" -or $uploadPage -notmatch "const handleRemoveFile = removeFile") {
    throw "UploadPage does not delegate basic file state transitions to workflow hook actions."
}

if ($uploadPage -notmatch "beginPdfValidation," -or $uploadPage -notmatch "completePdfUpload," -or $uploadPage -notmatch "failPdfValidation,") {
    throw "UploadPage does not delegate PDF validation state transitions to workflow hook actions."
}

if ($uploadPage -notmatch "beginCsvValidation," `
    -or $uploadPage -notmatch "setValidationUploadSource," `
    -or $uploadPage -notmatch "setValidationProgress," `
    -or $uploadPage -notmatch "prepareCsvValidationJob," `
    -or $uploadPage -notmatch "updateValidationPoll," `
    -or $uploadPage -notmatch "completeValidationFailure," `
    -or $uploadPage -notmatch "completeValidationWithErrors," `
    -or $uploadPage -notmatch "completeValidationPassed," `
    -or $uploadPage -notmatch "failCsvValidation\(fileId\)") {
    throw "UploadPage does not delegate CSV validation state transitions to workflow hook actions."
}

if ($uploadPage -notmatch "beginPdfConvert," `
    -or $uploadPage -notmatch "attachPdfConvertJob," `
    -or $uploadPage -notmatch "updatePdfConvertProgress," `
    -or $uploadPage -notmatch "replacePdfWithCsvFiles," `
    -or $uploadPage -notmatch "failPdfConvert,") {
    throw "UploadPage does not pass PDF conversion workflow hooks to runPdfConvertWorkflow."
}

if ($uploadPage -match "beginPdfConvert\(fileId\)" `
    -or $uploadPage -match "attachPdfConvertJob: \(jobId\) =>" `
    -or $uploadPage -match "updatePdfConvertProgress\(fileId, status" `
    -or $uploadPage -match "replacePdfWithCsvFiles\(fileId, newCsvFiles\)" `
    -or $uploadPage -match "failPdfConvert\(fileId, e\?\.message") {
    throw "UploadPage still owns PDF conversion state transition calls; expected in orchestrator."
}

if ($uploadPage -notmatch "beginImport," `
    -or $uploadPage -notmatch "runBatchImportWorkflow\(\{" `
    -or $uploadPage -notmatch "runSingleImportWorkflow\(\{") {
    throw "UploadPage does not delegate import state transitions to workflow hook actions."
}

if ($uploadPage -match "beginImport\(\[id\], 20\)" `
    -or $uploadPage -match "runSingleImport\(\{" `
    -or $uploadPage -match "resetImport\(\[id\]\)") {
    throw "UploadPage still owns single import orchestration detail; expected in runSingleImportWorkflow."
}

$forbiddenPdfTransitions = @(
    "status: 'validating', validateProgress: 10",
    "processId: data\.process_id",
    "pdfConvertStatus: 'not_started'",
    "status: 'uploaded', validateProgress: 0"
)

foreach ($pdfTransition in $forbiddenPdfTransitions) {
    if ($uploadPage -match $pdfTransition) {
        throw "UploadPage still owns PDF validation transition detail: $pdfTransition"
    }
}

$forbiddenCsvTransitions = @(
    'status: "validating", validateProgress: 10',
    'file: fileToUpload, size: fileToUpload\.size',
    'processId: createdJob\.id',
    'status: lastJob\.status',
    "validationErrors: \[\{ row_index: 0, field: 'system'",
    'validationErrors: flattenedErrors',
    'validationErrors: \[\]',
    'status: "uploaded", validateProgress: 0'
)

foreach ($csvTransition in $forbiddenCsvTransitions) {
    if ($uploadPage -match $csvTransition) {
        throw "UploadPage still owns CSV validation transition detail: $csvTransition"
    }
}

$forbiddenPdfConvertTransitions = @(
    "pdfConvertStatus: 'queued'",
    "pdfConvertJobId: trigger\.job_id",
    "pdfConvertStatus:\s*status === 'COMPLETED'",
    "pdfConvertError:\s*status === 'FAILED'",
    "const withoutPdf = prev\.filter",
    "pdfConvertStatus: 'failed'",
    "pdfConvertProgress: 100,\s*pdfConvertError: e\?\.message"
)

foreach ($pdfConvertTransition in $forbiddenPdfConvertTransitions) {
    if ($uploadPage -match $pdfConvertTransition) {
        throw "UploadPage still owns PDF conversion transition detail: $pdfConvertTransition"
    }
}

$forbiddenPdfOutputBuildDetails = @(
    "const newCsvFiles: UploadedFile\[\] = \[\]",
    "newCsvFiles\.push",
    "const safeName = filesRef\.current\.some",
    "new File\(\[csvText\], safeName"
)

foreach ($pdfOutputBuildDetail in $forbiddenPdfOutputBuildDetails) {
    if ($uploadPage -match $pdfOutputBuildDetail) {
        throw "UploadPage still owns PDF output CSV file construction detail: $pdfOutputBuildDetail"
    }
}

$forbiddenImportTransitions = @(
    'status: "importing", importProgress',
    'status: "imported", importProgress',
    'status: "validated", importProgress: 0',
    'setFiles\(remainingFiles\)',
    'setFiles\(\[\]\)',
    'const withoutPdf = prev\.filter'
)

foreach ($importTransition in $forbiddenImportTransitions) {
    if ($uploadPage -match $importTransition) {
        throw "UploadPage still owns import transition detail: $importTransition"
    }
}

if ($uploadPage -notmatch "const uploadApi = useUploadApi\(t\)" -or $uploadPage -notmatch "uploadApi\.fetchImportJob") {
    throw "UploadPage does not use extracted upload API hook."
}

if ($uploadPage -match "TENANT_STORAGE_KEY" -or $uploadPage -match "buildTenantHeaders" -or $uploadPage -match "createUploadApiClient" -or $uploadPage -match "const uploadApi = useMemo") {
    throw "UploadPage still owns upload API setup details."
}

if ($uploadPage -match "const sleep = \(ms: number\)" -or $uploadPage -match "setTimeout\(resolve, ms\)" -or $uploadPage -match "\bsleep,") {
    throw "UploadPage still owns async delay plumbing."
}

if ($uploadPage -notmatch "sleep: delay") {
    throw "UploadPage does not delegate async delay helper."
}

if ($uploadPage -match "setTimeout\(\(\) =>") {
    throw "UploadPage still owns direct setTimeout cleanup scheduling."
}

if ($uploadPage -match "scheduleAfterDelay\(2000,") {
    throw "UploadPage still directly calls scheduleAfterDelay; expected cleanup helpers."
}

if ($uploadPage -match "uploadApi\.uploadApi") {
    throw "UploadPage contains duplicated uploadApi namespace replacement."
}

$requiredApiUsages = @(
    "uploadApi\.uploadPdf",
    "uploadApi\.createImportJob",
    "uploadApi\.fetchImportErrors",
    "uploadApi\.triggerPdfConvert",
    "uploadApi\.commitImportJob"
)

foreach ($usage in $requiredApiUsages) {
    if ($uploadPage -notmatch $usage) {
        throw "UploadPage is missing expected API client usage: $usage"
    }
}

$forbiddenInlineFetches = @(
    "fetch\('/api/upload/pdf'",
    "fetch\('/api/v2/import/jobs'",
    "fetch\(`/api/v2/import/jobs/\$\{jobId\}/errors",
    "fetch\(`/api/upload/pdf/\$\{target\.processId\}/convert",
    "fetch\(`/api/v2/import/jobs/\$\{jobId\}/commit"
)

foreach ($fetchPattern in $forbiddenInlineFetches) {
    if ($uploadPage -match $fetchPattern) {
        throw "UploadPage still owns inline fetch action: $fetchPattern"
    }
}

$requiredApiClientExports = @(
    "async uploadPdf",
    "async createImportJob",
    "async fetchImportErrors",
    "async triggerPdfConvert",
    "async commitImportJob"
)

foreach ($clientExport in $requiredApiClientExports) {
    if ($apiClient -notmatch $clientExport) {
        throw "uploadApiClient is missing expected action: $clientExport"
    }
}

if ($workflow -notmatch "export function useUploadWorkflow" -or $workflow -notmatch "const filesRef = useRef" -or $workflow -notmatch "removeFile" -or $workflow -notmatch "toggleFileExpanded") {
    throw "Upload workflow hook is missing expected state helpers."
}

foreach ($workflowAction in @("beginPdfValidation", "completePdfUpload", "failPdfValidation")) {
    if ($workflow -notmatch $workflowAction) {
        throw "Upload workflow hook is missing expected PDF validation action: $workflowAction"
    }
}

foreach ($workflowAction in @(
    "beginCsvValidation",
    "setValidationUploadSource",
    "setValidationProgress",
    "prepareCsvValidationJob",
    "updateValidationPoll",
    "completeValidationFailure",
    "completeValidationWithErrors",
    "completeValidationPassed",
    "failCsvValidation"
)) {
    if ($workflow -notmatch $workflowAction) {
        throw "Upload workflow hook is missing expected CSV validation action: $workflowAction"
    }
}

foreach ($workflowAction in @(
    "beginPdfConvert",
    "attachPdfConvertJob",
    "updatePdfConvertProgress",
    "replacePdfWithCsvFiles",
    "failPdfConvert"
)) {
    if ($workflow -notmatch $workflowAction) {
        throw "Upload workflow hook is missing expected PDF conversion action: $workflowAction"
    }
}

foreach ($workflowAction in @(
    "beginImport",
    "setImportProgress",
    "completeImport",
    "resetImport",
    "removeImportedFiles"
)) {
    if ($workflow -notmatch $workflowAction) {
        throw "Upload workflow hook is missing expected import action: $workflowAction"
    }
}

if ($utils -notmatch "buildUploadedCsvFilesFromPdfOutputs" -or $utils -notmatch "existingNames" -or $utils -notmatch "jobBackend: `"import_v2`"") {
    throw "Upload file utilities are missing expected PDF output CSV builder."
}

if ($fileAddUtils -notmatch "export function buildUploadFilesToAdd" -or $fileAddUtils -notmatch "confirmLikelyDuplicate" -or $fileAddUtils -notmatch "MAX_SIZE_BYTES" -or $fileAddUtils -notmatch "deriveLotNoFromFilename" -or $fileAddUtils -notmatch "jobBackend: type === `"PDF`" \? `"pdf`" : `"import_v2`"") {
    throw "Upload file-add utilities are missing expected workflow behavior."
}

if ($fileAddToastUtils -notmatch "export function showFileAddResultToasts" -or $fileAddToastUtils -notmatch "upload\.toast\.onlyCsvOrPdf" -or $fileAddToastUtils -notmatch "upload\.toast\.filesAdded" -or $fileAddToastUtils -notmatch "likely-duplicate-skipped") {
    throw "Upload file-add toast utilities are missing expected toast behavior."
}

if ($asyncUtils -notmatch "export function delay" -or $asyncUtils -notmatch "setTimeout\(resolve, ms\)" -or $asyncUtils -notmatch "export function scheduleAfterDelay" -or $asyncUtils -notmatch "window\.setTimeout\(action, ms\)") {
    throw "Upload async utilities are missing expected delay helper."
}

if ($csvEditUtils -notmatch "export function buildCsvText" -or $csvEditUtils -notmatch "export function updateCsvCellInFiles" -or $csvEditUtils -notmatch "export function saveCsvChangesInFiles" -or $csvEditUtils -notmatch "shouldResetV2Job" -or $csvEditUtils -notmatch "new File") {
    throw "Upload CSV edit utilities are missing expected helper exports."
}

if ($csvEditToastUtils -notmatch "export function showCsvEditDisabledToast" -or $csvEditToastUtils -notmatch "export function showCsvSaveErrorToast" -or $csvEditToastUtils -notmatch "upload\.toast\.changesAppliedRevalidate" -or $csvEditToastUtils -notmatch "upload\.errors\.saveError") {
    throw "Upload CSV edit toast utilities are missing expected toast behavior."
}

if ($fileDropArea -notmatch "export function FileDropArea" -or $fileDropArea -notmatch "upload-drop-area" -or $fileDropArea -notmatch "type=`"file`"") {
    throw "Extracted FileDropArea component is missing expected upload UI."
}

if ($batchActionBar -notmatch "export function BatchActionBar" -or $batchActionBar -notmatch "fileEligibleForValidate" -or $batchActionBar -notmatch "fileEligibleForConvert" -or $batchActionBar -notmatch "batch-import-btn") {
    throw "Extracted BatchActionBar component is missing expected batch UI."
}

if ($batchImportConfirmModal -notmatch "export function BatchImportConfirmModal" -or $batchImportConfirmModal -notmatch "fileEligibleForBatchImport" -or $batchImportConfirmModal -notmatch "fileHasBlockingImportErrors" -or $batchImportConfirmModal -notmatch "batch-import-confirm__list") {
    throw "Extracted BatchImportConfirmModal component is missing expected confirmation UI."
}

if ($uploadedFileCard -notmatch "export function UploadedFileCard" -or $uploadedFileCard -notmatch "function CsvEditor" -or $uploadedFileCard -notmatch "ProgressBar" -or $uploadedFileCard -notmatch "validation-errors-section") {
    throw "Extracted UploadedFileCard component is missing expected card/editor UI."
}

foreach ($predicateExport in @(
    "fileHasValidationErrors",
    "fileEligibleForValidate",
    "fileEligibleForConvert",
    "fileEligibleForBatchImport",
    "fileHasBlockingImportErrors",
    "fileIsUploadedButUnvalidated",
    "fileHasImportJob"
)) {
    if ($eligibility -notmatch "export function $predicateExport") {
        throw "Upload eligibility module is missing expected predicate: $predicateExport"
    }
}

if ($types -notmatch "export interface UploadedFile" -or $utils -notmatch "export async function parseCsv" -or $progress -notmatch "toValidateProgress" -or $apiClient -notmatch "createUploadApiClient") {
    throw "UploadPage refactor modules are missing expected exports."
}

if ($uploadApiHook -notmatch "export function useUploadApi" -or $uploadApiHook -notmatch "TENANT_STORAGE_KEY" -or $uploadApiHook -notmatch "createUploadApiClient" -or $uploadApiHook -notmatch "getTenantHeaders: buildTenantHeaders") {
    throw "Upload API hook is missing expected tenant/client setup behavior."
}

if ($batchOrchestrator -notmatch "export type ValidateOutcome" -or $batchOrchestrator -notmatch "export async function runBatchValidation" -or $batchOrchestrator -notmatch "export async function runBatchConversion" -or $batchOrchestrator -notmatch "export async function runBatchImport" -or $batchOrchestrator -notmatch "export async function runBatchImportWorkflow" -or $batchOrchestrator -notmatch "export async function runSingleImport" -or $batchOrchestrator -notmatch "commitImportJob" -or $batchOrchestrator -notmatch "fetchImportJob" -or $batchOrchestrator -notmatch "fileEligibleForValidate" -or $batchOrchestrator -notmatch "fileEligibleForConvert") {
    throw "Upload batch orchestration module is missing expected exports."
}

if ($uploadPage -match "const totalFiles = files\.length" -or $uploadPage -match "showBatchImportStartToast" -or $uploadPage -match "resetImport\(validatedFiles") {
    throw "UploadPage still owns batch import workflow orchestration."
}

if ($pdfConversionOrchestrator -notmatch "export async function runPdfConversion" -or $pdfConversionOrchestrator -notmatch "maxConsecutiveErrors" -or $pdfConversionOrchestrator -notmatch "fetchPdfConvertStatus" -or $pdfConversionOrchestrator -notmatch "updatePdfConvertProgress" -or $pdfConversionOrchestrator -notmatch 'outcome: "completed"') {
    throw "Upload PDF conversion orchestration module is missing expected exports."
}

if ($pdfConvertToastUtils -notmatch "export function showPdfConvertFetchingCsvToast" -or $pdfConvertToastUtils -notmatch "export function showPdfConvertGotCsvToast" -or $pdfConvertToastUtils -notmatch "export function showPdfConvertStillProcessingToast" -or $pdfConvertToastUtils -notmatch "upload\.toast\.pdfConvertFetchingCsv" -or $pdfConvertToastUtils -notmatch "upload\.toast\.pdfConvertGotCsv" -or $pdfConvertToastUtils -notmatch "upload\.toast\.pdfConvertStillProcessing") {
    throw "Upload PDF conversion toast utilities are missing expected toast behavior."
}

if ($validationOrchestrator -notmatch "export async function runPdfValidation" -or $validationOrchestrator -notmatch "export async function runCsvValidationJob" -or $validationOrchestrator -notmatch "uploadPdf" -or $validationOrchestrator -notmatch "beginPdfValidation" -or $validationOrchestrator -notmatch "completePdfUpload" -or $validationOrchestrator -notmatch "failPdfValidation" -or $validationOrchestrator -notmatch "DUPLICATE_FILE_CONTENT" -or $validationOrchestrator -notmatch "prepareCsvValidationJob" -or $validationOrchestrator -notmatch "updateValidationPoll") {
    throw "Upload validation orchestration module is missing expected exports."
}

if ($validationErrorUtils -notmatch "export function flattenImportValidationErrors" -or $validationErrorUtils -notmatch "row_index: rowIndex0" -or $validationErrorUtils -notmatch "error\.field \?\? error\.column" -or $validationErrorUtils -notmatch "Row is invalid") {
    throw "Upload validation error utilities are missing expected flattening behavior."
}

if ($validationToastUtils -notmatch "export function showValidationResultToast" -or $validationToastUtils -notmatch "upload\.toast\.pdfUploadedReadyToConvert" -or $validationToastUtils -notmatch "upload\.toast\.validationDoneWithInvalidRowsNoEdit" -or $validationToastUtils -notmatch "upload\.toast\.validationPassedAllRows") {
    throw "Upload validation toast utilities are missing expected toast behavior."
}

if ($importToastUtils -notmatch "export function showBatchImportStartToast" -or $importToastUtils -notmatch "export function showSingleImportCompletedToast" -or $importToastUtils -notmatch "upload\.batchImport\.toast\.completedBatch" -or $importToastUtils -notmatch "upload\.toast\.importStarting" -or $importToastUtils -notmatch "upload\.toast\.pageResetContinueUpload") {
    throw "Upload import toast utilities are missing expected toast behavior."
}

if ($uploadPage -notmatch "scheduleBatchPostImportCleanup\(\{") {
    throw "UploadPage does not delegate batch post-import cleanup scheduling to helper."
}

if ($importCleanupUtils -notmatch "export function scheduleBatchPostImportCleanup" `
    -or $importCleanupUtils -notmatch "export function scheduleSinglePostImportCleanup" `
    -or $importCleanupUtils -notmatch "scheduleAfterDelay" `
    -or $importCleanupUtils -notmatch "showBatchImportCleanupToast" `
    -or $importCleanupUtils -notmatch "showSingleImportCleanupToast") {
    throw "Upload import cleanup utilities are missing expected scheduling helpers."
}

# Phase 25: commitCsvValidationResult extraction
if ($uploadPage -notmatch 'commitCsvValidationResult') {
    throw "UploadPage does not delegate CSV validation result dispatch to commitCsvValidationResult."
}

if ($uploadPage -match 'import \{ flattenImportValidationErrors \}') {
    throw "UploadPage still imports flattenImportValidationErrors; it should be internal to uploadValidationOrchestrator after Phase 25."
}

if ($uploadPage -match 'completeValidationFailure\(fileId, message\)' -or $uploadPage -match 'completeValidationWithErrors\(fileId, flattenedErrors\)') {
    throw "UploadPage still has inline CSV validation result dispatch; it should be inside commitCsvValidationResult after Phase 25."
}

if ($validationOrchestrator -notmatch 'commitCsvValidationResult') {
    throw "uploadValidationOrchestrator.ts does not export commitCsvValidationResult."
}

if ($validationOrchestrator -notmatch 'flattenImportValidationErrors') {
    throw "uploadValidationOrchestrator.ts does not import flattenImportValidationErrors."
}

Write-Host "OK UploadPage refactor"
