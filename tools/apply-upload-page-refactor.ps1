param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedAppRoot = "generated\mvp-import-flow\form-analysis-server"
)

$ErrorActionPreference = "Stop"

$frontendRoot = Join-Path $ProjectRoot (Join-Path $GeneratedAppRoot "frontend")
$uploadPagePath = Join-Path $frontendRoot "src\pages\UploadPage.tsx"
$moduleRoot = Join-Path $frontendRoot "src\pages\upload"

if (-not (Test-Path $uploadPagePath)) {
    throw "UploadPage not found: $uploadPagePath"
}

New-Item -ItemType Directory -Force $moduleRoot | Out-Null

@'
export type FileType = "P1" | "P2" | "P3" | "PDF";

export interface CsvData {
  headers: string[];
  rows: string[][];
  colWidths: number[];
  starCells: Set<string>;
  emptyCells: Set<string>;
}

export interface UploadedFile {
  id: string;
  file: File;
  name: string;
  size: number;
  type: FileType;
  lotNo: string;
  status: "uploaded" | "validating" | "validated" | "importing" | "imported";
  jobBackend: "import_v2" | "pdf";
  uploadProgress: number;
  validateProgress: number;
  importProgress: number;
  csvData: CsvData | undefined;
  expanded: boolean;
  hasUnsavedChanges: boolean;
  processId: string | undefined;
  isValidated: boolean;
  validationErrors: any[] | undefined;
  pdfConvertStatus: "not_started" | "queued" | "uploading" | "processing" | "completed" | "failed" | undefined;
  pdfConvertJobId: string | undefined;
  pdfConvertProgress: number | undefined;
  pdfConvertError: string | undefined;
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadTypes.ts")

@'
import type { CsvData, FileType, UploadedFile } from "./uploadTypes";

export const MAX_SIZE_BYTES = 10 * 1024 * 1024;

export function detectFileType(name: string): FileType {
  if (name.toLowerCase().endsWith(".pdf")) return "PDF";
  if (name.startsWith("P1_")) return "P1";
  if (name.startsWith("P2_")) return "P2";
  return "P3";
}

export function deriveLotNoFromFilename(name: string): string {
  const base = name.replace(/\.csv$/i, "");
  const parts = base.split("_");
  const meaningful = parts.slice(1);
  if (meaningful.length === 0) return "";
  if (meaningful.length === 1) return normalizeLotNo(meaningful[0]);
  const head = normalize7Digits(meaningful[0]);
  const tailDigits = meaningful[1].replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

export function normalizeP3LotNo(value: string): string {
  const parts = value.split("_");
  if (parts.length < 2) return normalizeLotNo(value);
  const head = normalize7Digits(parts[0]);
  const tailDigits = parts[1].replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

function normalize7Digits(x: string): string {
  const digits = x.replace(/\D/g, "");
  return digits.padStart(7, "0").slice(-7);
}

export function normalizeLotNo(raw: string): string {
  const [a, b] = raw.split("_");
  const head = normalize7Digits(a ?? raw);
  if (!b) return head;
  const tailDigits = b.replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

export async function parseCsv(file: File): Promise<CsvData> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (!lines.length) {
    return { headers: [], rows: [], colWidths: [], starCells: new Set(), emptyCells: new Set() };
  }

  const rows = lines.map((line) => line.split(","));
  const headers = rows[0];
  const dataRows = rows.slice(1);
  const starCells = new Set<string>();
  const emptyCells = new Set<string>();

  for (let r = 0; r < dataRows.length; r++) {
    for (let c = 0; c < dataRows[r].length; c++) {
      const raw = dataRows[r][c];
      if (raw == null || raw.trim() === "") {
        emptyCells.add(`${r}_${c}`);
        continue;
      }

      let marked = false;
      let cleaned = raw;
      if (cleaned.includes("*")) {
        marked = true;
        cleaned = cleaned.replace(/\*/g, "");
      }
      if (cleaned !== cleaned.trim()) {
        marked = true;
      }
      if (marked) {
        starCells.add(`${r}_${c}`);
        dataRows[r][c] = cleaned;
      }
    }
  }

  const colWidths = new Array(headers.length).fill(0);
  const updateWidth = (col: number, value: string) => {
    colWidths[col] = Math.max(colWidths[col], value.length);
  };

  headers.forEach((header, index) => updateWidth(index, header));
  dataRows.forEach((row) => row.forEach((cell, index) => updateWidth(index, cell ?? "")));

  return {
    headers,
    rows: dataRows,
    colWidths: colWidths.map((length) => Math.max(80, Math.min(length * 10, 260))),
    starCells,
    emptyCells,
  };
}

export async function buildUploadedCsvFilesFromPdfOutputs(
  outputs: any[],
  existingNames: string[]
): Promise<UploadedFile[]> {
  const newCsvFiles: UploadedFile[] = [];
  const usedNames = new Set(existingNames);

  for (const output of outputs) {
    const filename = String(output.filename || "output.csv");
    const csvText = typeof output.csv_text === "string" ? output.csv_text : "";
    const safeName = usedNames.has(filename)
      ? `${filename.replace(/\.csv$/i, "")}__${Date.now().toString().slice(-6)}.csv`
      : filename;
    usedNames.add(safeName);

    const file = new File([csvText], safeName, { type: "text/csv" });
    const type = detectFileType(safeName);
    const lotNo = type === "P1" || type === "P2" ? deriveLotNoFromFilename(safeName) : "";
    const csvData = await parseCsv(file);

    newCsvFiles.push({
      id: `${safeName}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      name: safeName,
      size: file.size,
      type,
      lotNo,
      status: "uploaded",
      jobBackend: "import_v2",
      uploadProgress: 100,
      validateProgress: 0,
      importProgress: 0,
      expanded: false,
      csvData,
      hasUnsavedChanges: false,
      processId: undefined,
      isValidated: false,
      validationErrors: undefined,
      pdfConvertStatus: undefined,
      pdfConvertJobId: undefined,
      pdfConvertProgress: undefined,
      pdfConvertError: undefined,
    });
  }

  return newCsvFiles;
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadFileUtils.ts")

@'
import type { UploadedFile } from "./uploadTypes";
import { MAX_SIZE_BYTES, deriveLotNoFromFilename, detectFileType } from "./uploadFileUtils";

export type AddUploadFileNotice =
  | { type: "unsupported"; fileName: string }
  | { type: "likely-duplicate-skipped"; fileName: string }
  | { type: "same-name"; fileName: string }
  | { type: "too-large"; fileName: string; maxSizeMb: string };

interface BuildUploadFilesToAddOptions {
  fileList: FileList | null;
  existingFiles: UploadedFile[];
  confirmLikelyDuplicate: (file: File) => boolean;
}

function isSupportedUploadFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".csv") || lowerName.endsWith(".pdf");
}

function isLikelyDuplicateFile(file: File, files: UploadedFile[]): boolean {
  return files.some(
    (existingFile) =>
      existingFile.name === file.name &&
      existingFile.size === file.size &&
      existingFile.file.lastModified === file.lastModified
  );
}

function buildUploadedFile(file: File): UploadedFile {
  const type = detectFileType(file.name);
  const lotNo = type === "P1" || type === "P2" ? deriveLotNoFromFilename(file.name) : "";
  const id = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  return {
    id,
    file,
    name: file.name,
    size: file.size,
    type,
    lotNo,
    status: "uploaded",
    jobBackend: type === "PDF" ? "pdf" : "import_v2",
    uploadProgress: 100,
    validateProgress: 0,
    importProgress: 0,
    expanded: type === "PDF" ? false : true,
    csvData: undefined,
    hasUnsavedChanges: false,
    processId: undefined,
    isValidated: false,
    validationErrors: undefined,
    pdfConvertStatus: type === "PDF" ? "not_started" : undefined,
    pdfConvertJobId: undefined,
    pdfConvertProgress: type === "PDF" ? 0 : undefined,
    pdfConvertError: undefined,
  };
}

export function buildUploadFilesToAdd({
  fileList,
  existingFiles,
  confirmLikelyDuplicate,
}: BuildUploadFilesToAddOptions): { files: UploadedFile[]; notices: AddUploadFileNotice[] } {
  if (!fileList) return { files: [], notices: [] };

  const files: UploadedFile[] = [];
  const notices: AddUploadFileNotice[] = [];

  Array.from(fileList).forEach((file) => {
    if (!isSupportedUploadFile(file)) {
      notices.push({ type: "unsupported", fileName: file.name });
      return;
    }

    const comparisonFiles = [...existingFiles, ...files];
    if (isLikelyDuplicateFile(file, comparisonFiles)) {
      const proceed = confirmLikelyDuplicate(file);
      if (!proceed) {
        notices.push({ type: "likely-duplicate-skipped", fileName: file.name });
        return;
      }
    } else if (comparisonFiles.some((existingFile) => existingFile.name === file.name)) {
      notices.push({ type: "same-name", fileName: file.name });
    }

    if (file.size > MAX_SIZE_BYTES) {
      notices.push({
        type: "too-large",
        fileName: file.name,
        maxSizeMb: (MAX_SIZE_BYTES / 1024 / 1024).toFixed(0),
      });
      return;
    }

    files.push(buildUploadedFile(file));
  });

  return { files, notices };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadFileAddUtils.ts")

@'
import type { AddUploadFileNotice } from "./uploadFileAddUtils";

type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface FileAddToastOptions {
  notices: AddUploadFileNotice[];
  addedCount: number;
  showToast: ShowToast;
  t: TranslationFn;
}

export function showFileAddResultToasts({
  notices,
  addedCount,
  showToast,
  t,
}: FileAddToastOptions): void {
  notices.forEach((notice) => {
    if (notice.type === "unsupported") {
      showToast("error", t("upload.toast.onlyCsvOrPdf"));
    } else if (notice.type === "likely-duplicate-skipped") {
      showToast("info", "\u5df2\u7565\u904e\u7591\u4f3c\u91cd\u8907\u6a94\u6848\uff1a" + notice.fileName);
    } else if (notice.type === "same-name") {
      showToast("info", t("upload.toast.fileAlreadyExists", { fileName: notice.fileName }));
    } else if (notice.type === "too-large") {
      showToast("error", t("upload.toast.fileTooLarge", { maxSizeMb: notice.maxSizeMb }));
    }
  });

  if (addedCount > 0) {
    showToast("success", t("upload.toast.filesAdded", { count: addedCount }));
  }
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadFileAddToastUtils.ts")

@'
import type { CsvData, UploadedFile } from "./uploadTypes";

export function buildCsvText(csv: CsvData): string {
  const escapeCell = (cell: string) => {
    const value = cell ?? "";
    if (/[\r\n,"]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };

  const lines: string[] = [];
  lines.push(csv.headers.map((cell) => escapeCell(cell ?? "")).join(","));
  csv.rows.forEach((row) => {
    lines.push(row.map((cell) => escapeCell(cell ?? "")).join(","));
  });
  return lines.join("\n");
}

export function updateCsvCellInFiles(
  files: UploadedFile[],
  fileId: string,
  rowIndex: number,
  colIndex: number,
  value: string
): UploadedFile[] {
  return files.map((file) => {
    if (file.id !== fileId || !file.csvData) return file;

    const rows = file.csvData.rows.map((row, currentRowIndex) =>
      currentRowIndex === rowIndex
        ? row.map((cell, currentColIndex) => (currentColIndex === colIndex ? value : cell))
        : row
    );

    const shouldResetV2Job = file.jobBackend === "import_v2";
    return {
      ...file,
      csvData: { ...file.csvData, rows },
      hasUnsavedChanges: true,
      status: "uploaded",
      validateProgress: 0,
      importProgress: 0,
      isValidated: false,
      validationErrors: undefined,
      processId: shouldResetV2Job ? undefined : file.processId,
    };
  });
}

export type SaveCsvChangesResult =
  | { outcome: "saved"; files: UploadedFile[] }
  | { outcome: "not-found-or-clean" }
  | { outcome: "unsupported-backend" };

export function saveCsvChangesInFiles(
  files: UploadedFile[],
  fileId: string
): SaveCsvChangesResult {
  const target = files.find((file) => file.id === fileId);
  if (!target || !target.csvData || !target.hasUnsavedChanges) {
    return { outcome: "not-found-or-clean" };
  }

  if (target.jobBackend !== "import_v2") {
    return { outcome: "unsupported-backend" };
  }

  const csvText = buildCsvText(target.csvData);
  const updatedFile = new File([csvText], target.name, { type: "text/csv" });

  return {
    outcome: "saved",
    files: files.map((file) =>
      file.id === fileId
        ? {
            ...file,
            file: updatedFile,
            size: updatedFile.size,
            hasUnsavedChanges: false,
            status: "uploaded",
            validateProgress: 0,
            importProgress: 0,
            processId: undefined,
            isValidated: false,
            validationErrors: undefined,
          }
        : file
    ),
  };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadCsvEditUtils.ts")

@'
type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface CsvEditToastOptions {
  showToast: ShowToast;
  t: TranslationFn;
}

export function showCsvEditDisabledToast({ showToast, t }: CsvEditToastOptions): void {
  showToast("info", t("upload.editDisabledNotice"));
}

export function showCsvSaveErrorToast({ showToast, t }: CsvEditToastOptions): void {
  showToast("error", t("upload.errors.saveError"));
}

export function showCsvChangesAppliedToast({ showToast, t }: CsvEditToastOptions): void {
  showToast("success", t("upload.toast.changesAppliedRevalidate"));
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadCsvEditToastUtils.ts")

@'
import type { UploadedFile } from "./uploadTypes";

export function fileHasValidationErrors(file: UploadedFile): boolean {
  return Array.isArray(file.validationErrors) && file.validationErrors.length > 0;
}

export function fileEligibleForValidate(file: UploadedFile): boolean {
  if (file.status === "validating" || file.status === "importing") return false;
  if (file.type === "PDF") {
    return !file.isValidated;
  }
  if (file.status === "uploaded") return true;
  if (file.status === "validated" && fileHasValidationErrors(file)) return true;
  return false;
}

export function fileEligibleForConvert(file: UploadedFile): boolean {
  if (file.type !== "PDF") return false;
  if (!file.isValidated) return false;
  return (
    file.pdfConvertStatus !== "queued" &&
    file.pdfConvertStatus !== "uploading" &&
    file.pdfConvertStatus !== "processing" &&
    file.pdfConvertStatus !== "completed"
  );
}

export function fileEligibleForBatchImport(file: UploadedFile): boolean {
  return (
    file.status === "validated" &&
    Boolean(file.processId) &&
    !file.hasUnsavedChanges &&
    !fileHasValidationErrors(file)
  );
}

export function fileHasBlockingImportErrors(file: UploadedFile): boolean {
  return file.status === "validated" && fileHasValidationErrors(file);
}

export function fileIsUploadedButUnvalidated(file: UploadedFile): boolean {
  return file.status === "uploaded";
}

export function fileHasImportJob(file: UploadedFile): boolean {
  return file.status === "validated" && Boolean(file.processId);
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadEligibility.ts")

@'
import type { UploadedFile } from "./uploadTypes";
import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileIsUploadedButUnvalidated } from "./uploadEligibility";
import { showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast } from "./uploadImportToastUtils";

export type ValidateOutcome =
  | { outcome: "passed"; totalRows: number }
  | { outcome: "errors"; totalRows: number; errorCount: number }
  | { outcome: "failed"; message: string };

type ToastKind = "success" | "error" | "info" | "warning";
type ToastOptions = { key?: string; durationMs?: number | null };
type ShowToast = (kind: ToastKind, message: string, options?: ToastOptions) => void;
type Translate = (key: string, options?: Record<string, unknown>) => string;

interface BatchValidationOptions {
  filesRef: { current: UploadedFile[] };
  setIsValidatingAll: (value: boolean) => void;
  handleValidate: (fileId: string, options?: { silentToast?: boolean }) => Promise<ValidateOutcome>;
  showToast: ShowToast;
  t: Translate;
}

interface BatchConversionOptions {
  filesRef: { current: UploadedFile[] };
  setIsConvertingAll: (value: boolean) => void;
  handlePdfConvert: (fileId: string) => Promise<boolean>;
  showToast: ShowToast;
  t: Translate;
}

interface ImportJobStatus {
  status: string;
  total_rows?: number;
  error_summary?: { error?: string };
}

interface BatchImportOptions {
  validatedFiles: UploadedFile[];
  commitImportJob: (jobId: string) => Promise<ImportJobStatus>;
  fetchImportJob: (jobId: string) => Promise<ImportJobStatus>;
  sleep: (ms: number) => Promise<void>;
  setImportProgress: (fileId: string, progress: number) => void;
  completeImport: (fileId: string) => void;
  toImportProgress: (jobStatus: string) => number;
  showToast: ShowToast;
  t: Translate;
}

interface BatchImportWorkflowOptions {
  files: UploadedFile[];
  commitImportJob: (jobId: string) => Promise<ImportJobStatus>;
  fetchImportJob: (jobId: string) => Promise<ImportJobStatus>;
  sleep: (ms: number) => Promise<void>;
  beginImport: (fileIds: string[], progress: number) => void;
  setImportProgress: (fileId: string, progress: number) => void;
  completeImport: (fileId: string) => void;
  resetImport: (fileIds: string[]) => void;
  toImportProgress: (jobStatus: string) => number;
  schedulePostImportCleanup: (fileIds: string[]) => void;
  logError: (message: string, error: unknown) => void;
  showToast: ShowToast;
  t: Translate;
}

interface SingleImportOptions {
  file: UploadedFile;
  commitImportJob: (jobId: string) => Promise<ImportJobStatus>;
  fetchImportJob: (jobId: string) => Promise<ImportJobStatus>;
  sleep: (ms: number) => Promise<void>;
  setImportProgress: (fileId: string, progress: number) => void;
  completeImport: (fileId: string) => void;
  toImportProgress: (jobStatus: string) => number;
  t: Translate;
}

export async function runBatchValidation({
  filesRef,
  setIsValidatingAll,
  handleValidate,
  showToast,
  t,
}: BatchValidationOptions): Promise<void> {
  const targets = filesRef.current.filter(fileEligibleForValidate);
  if (targets.length === 0) {
    showToast("info", t("upload.batchValidate.toast.noEligible"));
    return;
  }

  setIsValidatingAll(true);
  showToast("info", t("upload.batchValidate.toast.start", { count: targets.length }), {
    key: "validateAll",
    durationMs: null,
  });

  let okCount = 0;
  let errorCount = 0;
  let failCount = 0;

  for (let index = 0; index < targets.length; index++) {
    const file = targets[index];
    showToast(
      "info",
      t("upload.batchValidate.toast.progress", {
        current: index + 1,
        total: targets.length,
        fileName: file.name,
      }),
      { key: "validateAll", durationMs: null }
    );

    const result = await handleValidate(file.id, { silentToast: true });
    if (result.outcome === "passed") okCount += 1;
    else if (result.outcome === "errors") errorCount += 1;
    else failCount += 1;
  }

  setIsValidatingAll(false);
  if (failCount > 0) {
    showToast("error", t("upload.batchValidate.toast.doneWithFailures", { ok: okCount, errors: errorCount, failed: failCount }), { key: "validateAll", durationMs: 2500 });
  } else if (errorCount > 0) {
    showToast("error", t("upload.batchValidate.toast.doneWithErrors", { ok: okCount, errors: errorCount }), { key: "validateAll", durationMs: 2500 });
  } else {
    showToast("success", t("upload.batchValidate.toast.doneAllPassed", { ok: okCount }), { key: "validateAll", durationMs: 2500 });
  }
}

export async function runBatchConversion({
  filesRef,
  setIsConvertingAll,
  handlePdfConvert,
  showToast,
  t,
}: BatchConversionOptions): Promise<void> {
  const targets = filesRef.current.filter(fileEligibleForConvert);
  if (targets.length === 0) {
    showToast("info", t("upload.batchConvert.toast.noEligible"));
    return;
  }

  setIsConvertingAll(true);
  showToast("info", t("upload.batchConvert.toast.start", { count: targets.length }), {
    key: "convertAll",
    durationMs: null,
  });

  let okCount = 0;
  let failCount = 0;

  for (let index = 0; index < targets.length; index++) {
    const file = targets[index];
    showToast(
      "info",
      t("upload.batchConvert.toast.progress", {
        current: index + 1,
        total: targets.length,
        fileName: file.name,
      }),
      { key: "convertAll", durationMs: null }
    );

    const ok = await handlePdfConvert(file.id);
    if (ok) okCount += 1; else failCount += 1;
  }

  setIsConvertingAll(false);
  if (failCount > 0) {
    showToast("error", t("upload.batchConvert.toast.doneWithFailures", { ok: okCount, failed: failCount }), { key: "convertAll", durationMs: 2500 });
  } else {
    showToast("success", t("upload.batchConvert.toast.doneAllPassed", { ok: okCount }), { key: "convertAll", durationMs: 2500 });
  }
}

export async function runBatchImport({
  validatedFiles,
  commitImportJob,
  fetchImportJob,
  sleep,
  setImportProgress,
  completeImport,
  toImportProgress,
  showToast,
  t,
}: BatchImportOptions): Promise<number> {
  let totalImported = 0;

  for (const [index, file] of validatedFiles.entries()) {
    showToast(
      "info",
      t("upload.batchImport.toast.progress", {
        current: index + 1,
        total: validatedFiles.length,
        fileName: file.name,
      }),
      { key: "import", durationMs: null }
    );

    const progress = Math.round((index / validatedFiles.length) * 80) + 10;
    setImportProgress(file.id, progress);

    const jobId = file.processId as string;
    let committedJob: ImportJobStatus;
    try {
      committedJob = await commitImportJob(jobId);
    } catch (error: any) {
      const errorMessage = error?.message || t("upload.errors.importFailed");
      throw new Error(t("upload.batchImport.error.fileImportFailed", { fileName: file.name, errorMessage }));
    }

    for (let pollIndex = 0; pollIndex < 300; pollIndex++) {
      await sleep(1000);
      committedJob = await fetchImportJob(jobId);
      setImportProgress(file.id, toImportProgress(committedJob.status));
      if (committedJob.status === "COMPLETED" || committedJob.status === "FAILED") break;
    }

    if (committedJob.status !== "COMPLETED") {
      const errorMessage = committedJob.error_summary?.error || t("upload.errors.importFailed");
      throw new Error(t("upload.batchImport.error.fileImportFailed", { fileName: file.name, errorMessage }));
    }

    totalImported += Number(committedJob.total_rows || 0);
    completeImport(file.id);
  }

  return totalImported;
}

export async function runBatchImportWorkflow({
  files,
  commitImportJob,
  fetchImportJob,
  sleep,
  beginImport,
  setImportProgress,
  completeImport,
  resetImport,
  toImportProgress,
  schedulePostImportCleanup,
  logError,
  showToast,
  t,
}: BatchImportWorkflowOptions): Promise<void> {
  const totalFiles = files.length;
  const validatedFiles = files.filter(fileEligibleForBatchImport);
  const filesWithErrors = files.filter(fileHasBlockingImportErrors);
  const unvalidatedFiles = files.filter(fileIsUploadedButUnvalidated);

  if (validatedFiles.length === 0) {
    showBatchImportUnavailableToast({
      filesWithErrorsCount: filesWithErrors.length,
      unvalidatedFilesCount: unvalidatedFiles.length,
      showToast,
      t,
    });
    return;
  }

  const isSingleFile = totalFiles === 1;

  if (!isSingleFile && filesWithErrors.length > 0) {
    showBatchImportSkipErrorsToast({
      errorCount: filesWithErrors.length,
      validCount: validatedFiles.length,
      showToast,
      t,
    });
  }

  showBatchImportStartToast({
    isSingleFile,
    fileCount: validatedFiles.length,
    showToast,
    t,
  });

  const importingIds = validatedFiles.map((file) => file.id);
  beginImport(importingIds, 10);

  try {
    const totalImported = await runBatchImport({
      validatedFiles,
      commitImportJob,
      fetchImportJob,
      sleep,
      setImportProgress,
      completeImport,
      toImportProgress,
      showToast,
      t,
    });

    showBatchImportCompletedToast({
      isSingleFile,
      fileCount: validatedFiles.length,
      rowCount: totalImported,
      showToast,
      t,
    });

    schedulePostImportCleanup(importingIds);
  } catch (error) {
    logError("Batch import error:", error);
    const errorMessage = error instanceof Error ? error.message : t("upload.batchImport.error.generic");
    showImportErrorToast({ message: errorMessage, showToast, t });
    resetImport(importingIds);
  }
}

export async function runSingleImport({
  file,
  commitImportJob,
  fetchImportJob,
  sleep,
  setImportProgress,
  completeImport,
  toImportProgress,
  t,
}: SingleImportOptions): Promise<void> {
  const jobId = file.processId as string;
  let committedJob: ImportJobStatus;

  setImportProgress(file.id, 60);

  try {
    committedJob = await commitImportJob(jobId);
  } catch (error: any) {
    throw new Error(error?.message || t("upload.errors.importFailed"));
  }

  for (let pollIndex = 0; pollIndex < 300; pollIndex++) {
    await sleep(1000);
    committedJob = await fetchImportJob(jobId);
    setImportProgress(file.id, toImportProgress(committedJob.status));
    if (committedJob.status === "COMPLETED" || committedJob.status === "FAILED") break;
  }

  if (committedJob.status !== "COMPLETED") {
    throw new Error(committedJob.error_summary?.error || t("upload.errors.importFailed"));
  }

  completeImport(file.id);
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadBatchOrchestrator.ts")

@'
type PdfConvertStatusResponse = {
  status?: string;
  progress?: number;
  error_summary?: { error?: string };
};

type PdfConvertOutcome =
  | { outcome: "completed" }
  | { outcome: "failed"; message: string }
  | { outcome: "still-processing" };

interface PdfConversionOptions {
  processId: string;
  triggerPdfConvert: (processId: string) => Promise<{ job_id?: string }>;
  fetchPdfConvertStatus: (processId: string) => Promise<PdfConvertStatusResponse>;
  sleep: (ms: number) => Promise<void>;
  attachPdfConvertJob: (jobId: string | undefined) => void;
  updatePdfConvertProgress: (status: string, progress: number, errorText: string) => void;
  toPdfConvertProgress: (convertStatus: string) => number;
  fallbackErrorText: string;
}

export async function runPdfConversion({
  processId,
  triggerPdfConvert,
  fetchPdfConvertStatus,
  sleep,
  attachPdfConvertJob,
  updatePdfConvertProgress,
  toPdfConvertProgress,
  fallbackErrorText,
}: PdfConversionOptions): Promise<PdfConvertOutcome> {
  const trigger = await triggerPdfConvert(processId);
  attachPdfConvertJob(trigger.job_id);

  const maxTries = 1800;
  const maxConsecutiveErrors = 10;
  let consecutiveErrors = 0;

  for (let index = 0; index < maxTries; index++) {
    let current: PdfConvertStatusResponse;
    try {
      current = await fetchPdfConvertStatus(processId);
      consecutiveErrors = 0;
    } catch {
      consecutiveErrors += 1;
      if (consecutiveErrors >= maxConsecutiveErrors) {
        return { outcome: "failed", message: fallbackErrorText };
      }
      await sleep(3000);
      continue;
    }

    const status = String(current.status || "");
    const progress = typeof current.progress === "number"
      ? current.progress
      : toPdfConvertProgress(status);
    const errorText = current.error_summary?.error
      ? String(current.error_summary.error)
      : fallbackErrorText;

    updatePdfConvertProgress(status, progress, errorText);

    if (status === "COMPLETED") return { outcome: "completed" };
    if (status === "FAILED") return { outcome: "failed", message: errorText };

    await sleep(1000);
  }

  return { outcome: "still-processing" };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadPdfConversionOrchestrator.ts")

@'
import type { CsvData, UploadedFile } from "./uploadTypes";
import type { ValidateOutcome } from "./uploadBatchOrchestrator";
import { buildCsvText } from "./uploadCsvEditUtils";
import { flattenImportValidationErrors } from "./uploadValidationErrorUtils";

interface PdfValidationOptions {
  file: UploadedFile;
  uploadPdf: (file: File, filename: string) => Promise<{ process_id?: string }>;
  beginPdfValidation: (fileId: string) => void;
  completePdfUpload: (fileId: string, processId: string | undefined) => void;
  failPdfValidation: (fileId: string) => void;
  fallbackErrorText: string;
}

interface ImportJobStatus {
  id?: string;
  status?: string;
  total_rows?: number;
  error_count?: number;
  error_summary?: { error?: string };
}

interface CsvValidationOptions {
  file: UploadedFile;
  createImportJob: (input: {
    tableCode: string;
    allowDuplicate: boolean;
    file: File;
    filename: string;
  }) => Promise<ImportJobStatus>;
  parseCsv: (file: File) => Promise<CsvData>;
  confirmDuplicate: (duplicateOf: string) => boolean;
  sleep: (ms: number) => Promise<void>;
  beginCsvValidation: (fileId: string) => void;
  setValidationUploadSource: (fileId: string, file: File) => void;
  setValidationProgress: (fileId: string, progress: number) => void;
  prepareCsvValidationJob: (fileId: string, csvData: CsvData, jobId: string | undefined) => void;
  updateValidationPoll: (fileId: string, jobStatus: string, validateProgress: number) => void;
  fetchImportJob: (jobId: string) => Promise<ImportJobStatus>;
  toValidateProgress: (jobStatus: string) => number;
  validationTimeoutText: string;
}

export async function runPdfValidation({
  file,
  uploadPdf,
  beginPdfValidation,
  completePdfUpload,
  failPdfValidation,
  fallbackErrorText,
}: PdfValidationOptions): Promise<ValidateOutcome> {
  beginPdfValidation(file.id);

  try {
    const data = await uploadPdf(file.file, file.name);
    completePdfUpload(file.id, data.process_id);
    return { outcome: "passed", totalRows: 0 };
  } catch (error: any) {
    failPdfValidation(file.id);
    return { outcome: "failed", message: error?.message || fallbackErrorText };
  }
}

export async function runCsvValidationJob({
  file,
  createImportJob,
  parseCsv,
  confirmDuplicate,
  sleep,
  beginCsvValidation,
  setValidationUploadSource,
  setValidationProgress,
  prepareCsvValidationJob,
  updateValidationPoll,
  fetchImportJob,
  toValidateProgress,
  validationTimeoutText,
}: CsvValidationOptions): Promise<{ jobId: string; lastJob: ImportJobStatus }> {
  beginCsvValidation(file.id);

  const fileToUpload = file.csvData
    ? new File([buildCsvText(file.csvData)], file.name, { type: "text/csv" })
    : file.file;

  const createJob = (allowDuplicate: boolean) =>
    createImportJob({
      tableCode: file.type,
      allowDuplicate,
      file: fileToUpload,
      filename: file.name,
    });

  setValidationUploadSource(file.id, fileToUpload);
  setValidationProgress(file.id, 25);

  let createdJob: ImportJobStatus;
  try {
    createdJob = await createJob(false);
  } catch (error: any) {
    const detailObj = typeof error?.detail === "object" && error.detail ? error.detail : null;
    const duplicateDetected = detailObj?.error_code === "DUPLICATE_FILE_CONTENT";
    if (!duplicateDetected) throw error;

    const duplicateOf = detailObj?.duplicate_of?.uploaded_filename || "Unknown file";
    if (!confirmDuplicate(duplicateOf)) {
      throw new Error("Duplicate import cancelled by user");
    }
    createdJob = await createJob(true);
  }

  setValidationProgress(file.id, 40);

  const csvData = file.csvData ?? await parseCsv(fileToUpload);
  setValidationProgress(file.id, 90);
  prepareCsvValidationJob(file.id, csvData, createdJob.id);

  const jobId = createdJob.id as string;
  let lastJob = createdJob;
  for (let pollIndex = 0; pollIndex < 120; pollIndex++) {
    await sleep(1000);
    lastJob = await fetchImportJob(jobId);
    updateValidationPoll(file.id, String(lastJob.status || ""), toValidateProgress(String(lastJob.status || "")));
    if (lastJob.status === "READY" || lastJob.status === "FAILED") break;
  }

  if (!lastJob || (lastJob.status !== "READY" && lastJob.status !== "FAILED")) {
    throw new Error(validationTimeoutText);
  }

  return { jobId, lastJob };
}

interface CommitCsvValidationResultOptions {
  fileId: string;
  target: UploadedFile;
  lastJob: ImportJobStatus;
  fetchImportErrors: (jobId: string) => Promise<unknown[]>;
  completeValidationFailure: (fileId: string, message: string) => void;
  completeValidationWithErrors: (fileId: string, errors: any[]) => void;
  completeValidationPassed: (fileId: string) => void;
  showValidationResultToast: (opts: any) => void;
  showToast: any;
  t: any;
  silent?: boolean;
}

export async function commitCsvValidationResult({
  fileId,
  target,
  lastJob,
  fetchImportErrors,
  completeValidationFailure,
  completeValidationWithErrors,
  completeValidationPassed,
  showValidationResultToast,
  showToast,
  t,
  silent,
}: CommitCsvValidationResultOptions): Promise<ValidateOutcome> {
  const totalRows = Number(lastJob.total_rows || 0);
  const errorCount = Number(lastJob.error_count || 0);

  if (lastJob.status === "FAILED") {
    const message = lastJob.error_summary?.error || t("upload.errors.validateFailed");
    completeValidationFailure(fileId, message);
    showValidationResultToast({ kind: "csv-failed", silent, fileName: target.name, message, showToast, t });
    return { outcome: "failed", message };
  }

  if (errorCount > 0) {
    const errorRows = await fetchImportErrors(lastJob.id as string);
    const flattenedErrors = flattenImportValidationErrors(errorRows);
    completeValidationWithErrors(fileId, flattenedErrors);
    showValidationResultToast({ kind: "csv-errors", silent, fileName: target.name, totalRows, errorCount, showToast, t });
    return { outcome: "errors", totalRows, errorCount };
  }

  completeValidationPassed(fileId);
  showValidationResultToast({ kind: "csv-passed", silent, fileName: target.name, totalRows, showToast, t });
  return { outcome: "passed", totalRows };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationOrchestrator.ts")

@'
type ImportValidationError = {
  row_index: number;
  field: string;
  error_code: string;
  message: string;
};

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

export function flattenImportValidationErrors(errorRows: unknown): ImportValidationError[] {
  if (!Array.isArray(errorRows)) return [];

  return errorRows.flatMap((rawRow) => {
    const row = asRecord(rawRow);
    const rowIndex0 = Math.max(0, Number(row.row_index || 1) - 1);
    const errors = Array.isArray(row.errors) ? row.errors : [];

    if (errors.length === 0) {
      return [{
        row_index: rowIndex0,
        field: "row",
        error_code: "INVALID",
        message: "Row is invalid",
      }];
    }

    return errors.map((rawError) => {
      const error = asRecord(rawError);
      return {
        row_index: rowIndex0,
        field: String(error.field ?? error.column ?? "row"),
        error_code: String(error.error_code ?? "INVALID"),
        message: String(error.message ?? JSON.stringify(error)),
      };
    });
  });
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationErrorUtils.ts")

@'
import type { ValidateOutcome } from "./uploadBatchOrchestrator";

type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

type ValidationToastKind =
  | "pdf"
  | "edit-disabled"
  | "csv-failed"
  | "csv-errors"
  | "csv-passed"
  | "csv-exception";

interface ValidationToastOptions {
  kind: ValidationToastKind;
  silent?: boolean;
  result?: ValidateOutcome;
  fileName?: string;
  message?: string;
  totalRows?: number;
  errorCount?: number;
  showToast: ShowToast;
  t: TranslationFn;
}

export function showValidationResultToast({
  kind,
  silent,
  result,
  fileName,
  message,
  totalRows,
  errorCount,
  showToast,
  t,
}: ValidationToastOptions): void {
  if (silent) return;

  if (kind === "pdf") {
    if (result?.outcome === "passed") {
      showToast("success", t("upload.toast.pdfUploadedReadyToConvert"));
    } else {
      showToast("error", result?.message || message || t("upload.errors.pdfUploadFailed"));
    }
    return;
  }

  if (kind === "edit-disabled") {
    showToast("info", t("upload.editDisabledNotice"));
    return;
  }

  if (kind === "csv-failed") {
    showToast("error", t("upload.toast.validationFailedWithMessage", { fileName, message }));
    return;
  }

  if (kind === "csv-errors") {
    showToast("error", t("upload.toast.validationDoneWithInvalidRowsNoEdit", { fileName, totalRows, errorCount }));
    return;
  }

  if (kind === "csv-passed") {
    showToast("success", t("upload.toast.validationPassedAllRows", { fileName, totalRows }));
    return;
  }

  showToast("error", message || t("upload.errors.validationProcessError"));
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadValidationToastUtils.ts")

@'
type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface ImportToastBaseOptions {
  showToast: ShowToast;
  t: TranslationFn;
}

interface BatchImportAvailabilityToastOptions extends ImportToastBaseOptions {
  filesWithErrorsCount: number;
  unvalidatedFilesCount: number;
}

interface BatchImportToastOptions extends ImportToastBaseOptions {
  isSingleFile: boolean;
  fileCount: number;
  rowCount?: number;
}

interface RemainingFilesToastOptions extends ImportToastBaseOptions {
  remainingCount: number;
  wasOnlyFile?: boolean;
}

interface ImportErrorToastOptions extends ImportToastBaseOptions {
  message: string;
}

interface FileImportToastOptions extends ImportToastBaseOptions {
  fileName: string;
}

export function showBatchImportUnavailableToast({
  filesWithErrorsCount,
  unvalidatedFilesCount,
  showToast,
  t,
}: BatchImportAvailabilityToastOptions): void {
  if (filesWithErrorsCount > 0) {
    showToast("error", t("upload.batchImport.title.hasErrors", { count: filesWithErrorsCount }));
  } else if (unvalidatedFilesCount > 0) {
    showToast("error", t("upload.batchImport.title.notValidated", { count: unvalidatedFilesCount }));
  } else {
    showToast("error", t("upload.batchImport.title.noValidated"));
  }
}

export function showBatchImportSkipErrorsToast({
  errorCount,
  validCount,
  showToast,
  t,
}: ImportToastBaseOptions & { errorCount: number; validCount: number }): void {
  showToast("info", t("upload.batchImport.info.multiUploadSkipErrors", { errorCount, validCount }));
}

export function showBatchImportStartToast({
  isSingleFile,
  fileCount,
  showToast,
  t,
}: BatchImportToastOptions): void {
  showToast(
    "info",
    isSingleFile
      ? t("upload.batchImport.toast.startSingle")
      : t("upload.batchImport.toast.startBatch", { count: fileCount }),
    { key: "import", durationMs: null }
  );
}

export function showBatchImportCompletedToast({
  isSingleFile,
  fileCount,
  rowCount,
  showToast,
  t,
}: BatchImportToastOptions): void {
  showToast(
    "success",
    isSingleFile
      ? t("upload.batchImport.toast.completedSingle", { fileCount, rowCount })
      : t("upload.batchImport.toast.completedBatch", { fileCount, rowCount }),
    { key: "import", durationMs: 2500 }
  );
}

export function showBatchImportCleanupToast({
  remainingCount,
  showToast,
  t,
}: RemainingFilesToastOptions): void {
  if (remainingCount > 0) {
    showToast("info", t("upload.batchImport.toast.remainingFiles", { count: remainingCount }));
  } else {
    showToast("info", t("upload.batchImport.toast.allDone"));
  }
}

export function showSingleImportStartToast({
  fileName,
  showToast,
  t,
}: FileImportToastOptions): void {
  showToast("info", t("upload.toast.importStarting", { fileName }), { key: "import", durationMs: null });
}

export function showSingleImportCompletedToast({
  fileName,
  showToast,
  t,
}: FileImportToastOptions): void {
  showToast("success", t("upload.toast.importCompleted", { fileName }), { key: "import", durationMs: 2500 });
}

export function showSingleImportCleanupToast({
  remainingCount,
  wasOnlyFile,
  showToast,
  t,
}: RemainingFilesToastOptions): void {
  if (wasOnlyFile) {
    showToast("info", t("upload.toast.pageResetContinueUpload"));
  } else {
    showToast("info", t("upload.batchImport.toast.remainingFiles", { count: remainingCount }));
  }
}

export function showImportErrorToast({
  message,
  showToast,
}: ImportErrorToastOptions): void {
  showToast("error", message, { key: "import", durationMs: 4000 });
}

export function showMissingImportTargetToast({ showToast, t }: ImportToastBaseOptions): void {
  showToast("error", t("upload.toast.missingFileOrJobId"));
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadImportToastUtils.ts")

@'
type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface PdfConvertToastBaseOptions {
  showToast: ShowToast;
  t: TranslationFn;
}

interface PdfConvertProcessToastOptions extends PdfConvertToastBaseOptions {
  processId: string;
}

interface PdfConvertCsvToastOptions extends PdfConvertProcessToastOptions {
  count: number;
}

interface PdfConvertErrorToastOptions extends PdfConvertProcessToastOptions {
  message: string;
}

export function showMissingPdfConvertProcessToast({ showToast, t }: PdfConvertToastBaseOptions): void {
  showToast("error", t("upload.toast.missingProcessIdUploadPdf"));
}

export function showPdfConvertFetchingCsvToast({
  processId,
  showToast,
  t,
}: PdfConvertProcessToastOptions): void {
  showToast("info", t("upload.toast.pdfConvertFetchingCsv"), {
    key: `pdfIngest:${processId}`,
    durationMs: null,
  });
}

export function showPdfConvertGotCsvToast({
  processId,
  count,
  showToast,
  t,
}: PdfConvertCsvToastOptions): void {
  showToast("success", t("upload.toast.pdfConvertGotCsv", { count }), {
    key: `pdfIngest:${processId}`,
    durationMs: 2500,
  });
}

export function showPdfConvertNoCsvToast({
  processId,
  showToast,
  t,
}: PdfConvertProcessToastOptions): void {
  showToast("info", t("upload.toast.pdfConvertNoCsv"), {
    key: `pdfIngest:${processId}`,
    durationMs: 2500,
  });
}

export function showPdfConvertOutputErrorToast({
  processId,
  message,
  showToast,
}: PdfConvertErrorToastOptions): void {
  showToast("error", message, {
    key: `pdfIngest:${processId}`,
    durationMs: 3000,
  });
}

export function showPdfConvertFailedToast({
  message,
  showToast,
}: PdfConvertToastBaseOptions & { message: string }): void {
  showToast("error", message);
}

export function showPdfConvertStillProcessingToast({ showToast, t }: PdfConvertToastBaseOptions): void {
  showToast("info", t("upload.toast.pdfConvertStillProcessing"));
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadPdfConvertToastUtils.ts")

@'
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface FileDropAreaProps {
  onFiles: (files: FileList | null) => void;
}

export function FileDropArea({ onFiles }: FileDropAreaProps) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(false);
    onFiles(event.dataTransfer.files);
  };

  const handleDragOver: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(true);
  };

  const handleDragLeave: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(false);
  };

  const handleChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    onFiles(event.target.files);
    event.target.value = "";
  };

  return (
    <div className="upload-drop-wrapper">
      <div
        className={`upload-drop-area ${
          dragging ? "upload-drop-area--dragging" : ""
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <div className="upload-drop-icon">⬆</div>
        <p className="upload-drop-main-text">{t("upload.dropMain")}</p>
        <p className="upload-drop-sub-text">{t("upload.dropSub")}</p>
        <label className="upload-drop-button">
          {t("upload.chooseFile")}
          <input type="file" accept=".csv,.pdf" multiple onChange={handleChange} />
        </label>
      </div>
    </div>
  );
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "FileDropArea.tsx")

@'
import { useTranslation } from "react-i18next";
import type { UploadedFile } from "./uploadTypes";
import {
  fileEligibleForConvert,
  fileEligibleForValidate,
  fileHasImportJob,
  fileHasValidationErrors,
} from "./uploadEligibility";

interface BatchActionBarProps {
  files: UploadedFile[];
  isValidatingAll: boolean;
  isConvertingAll: boolean;
  onValidateAll: () => void;
  onConvertAll: () => void;
  onBatchImport: () => void;
}

export function BatchActionBar({
  files,
  isValidatingAll,
  isConvertingAll,
  onValidateAll,
  onConvertAll,
  onBatchImport,
}: BatchActionBarProps) {
  const { t } = useTranslation();
  const eligibleCount = files.filter(fileEligibleForValidate).length;
  const anyBusy = files.some((file) => file.status === "validating" || file.status === "importing");
  const validateDisabled = isValidatingAll || anyBusy || eligibleCount === 0;

  let validateTitle = "";
  if (validateDisabled) {
    validateTitle = eligibleCount === 0
      ? t("upload.batchValidate.title.noEligible")
      : t("upload.batchValidate.title.busy");
  } else {
    validateTitle = t("upload.batchValidate.title.ready", { count: eligibleCount });
  }

  const convertEligibleCount = files.filter(fileEligibleForConvert).length;
  const anyConverting = files.some(
    (file) =>
      file.pdfConvertStatus === "queued" ||
      file.pdfConvertStatus === "uploading" ||
      file.pdfConvertStatus === "processing"
  );
  const convertDisabled = isConvertingAll || anyConverting || convertEligibleCount === 0;

  const validatedFiles = files.filter(fileHasImportJob);
  const validFilesWithoutErrors = validatedFiles.filter((file) => !fileHasValidationErrors(file));
  const filesWithErrors = validatedFiles.filter(fileHasValidationErrors);
  const importDisabled = validFilesWithoutErrors.length === 0;

  let importTitle = "";
  if (importDisabled) {
    importTitle = filesWithErrors.length > 0
      ? t("upload.batchImport.title.hasErrors", { count: filesWithErrors.length })
      : t("upload.batchImport.title.noValidated");
  } else {
    importTitle = t("upload.batchImport.title.ready", { validCount: validFilesWithoutErrors.length });
    if (filesWithErrors.length > 0) {
      importTitle += ` ${t("upload.batchImport.title.skipErrorsSuffix", { errorCount: filesWithErrors.length })}`;
    }
  }

  return (
    <div className="batch-actions">
      <button
        className={`btn-secondary ${validateDisabled ? "btn-secondary--disabled" : ""}`}
        onClick={onValidateAll}
        disabled={validateDisabled}
        title={validateTitle}
        style={{ marginRight: "10px" }}
      >
        {isValidatingAll
          ? t("upload.batchValidate.buttonLabelBusy")
          : t("upload.batchValidate.buttonLabel", { count: eligibleCount })}
      </button>

      {(convertEligibleCount > 0 || isConvertingAll) && (
        <button
          className={`btn-secondary ${convertDisabled ? "btn-secondary--disabled" : ""}`}
          onClick={onConvertAll}
          disabled={convertDisabled}
          title={
            convertDisabled
              ? t("upload.batchConvert.title.busy")
              : t("upload.batchConvert.title.ready", { count: convertEligibleCount })
          }
          style={{ marginRight: "10px" }}
        >
          {isConvertingAll
            ? t("upload.batchConvert.buttonLabelBusy")
            : t("upload.batchConvert.buttonLabel", { count: convertEligibleCount })}
        </button>
      )}

      <button
        className={`btn-primary batch-import-btn ${importDisabled ? "btn-primary--disabled" : ""}`}
        onClick={onBatchImport}
        disabled={importDisabled}
        title={importTitle}
      >
        {t("upload.batchImport.buttonLabel", { count: validFilesWithoutErrors.length })}
        {filesWithErrors.length > 0 && (
          <span style={{ color: "#f59e0b", marginLeft: "8px" }}>
            {t("upload.batchImport.errorBadge", { count: filesWithErrors.length })}
          </span>
        )}
      </button>
    </div>
  );
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "BatchActionBar.tsx")

@'
import { useTranslation } from "react-i18next";
import { Modal } from "../../components/common/Modal";
import type { UploadedFile } from "./uploadTypes";
import {
  fileEligibleForBatchImport,
  fileHasBlockingImportErrors,
} from "./uploadEligibility";

interface BatchImportConfirmModalProps {
  open: boolean;
  files: UploadedFile[];
  onClose: () => void;
  onConfirm: () => void;
}

export function BatchImportConfirmModal({
  open,
  files,
  onClose,
  onConfirm,
}: BatchImportConfirmModalProps) {
  const { t } = useTranslation();
  const validFilesWithoutErrors = files.filter(fileEligibleForBatchImport);
  const filesWithErrors = files.filter(fileHasBlockingImportErrors);

  return (
    <Modal
      open={open}
      title={t("upload.batchImport.confirm.title")}
      onClose={onClose}
      onConfirm={onConfirm}
      confirmText={t("upload.batchImport.confirm.confirmText")}
      maxWidth="min(720px, 92vw)"
    >
      <div className="batch-import-confirm">
        <p style={{ marginBottom: "12px" }}>
          {t("upload.batchImport.confirm.summary", { count: validFilesWithoutErrors.length })}
        </p>
        <p style={{ marginBottom: "12px", color: "#dc2626", fontWeight: "bold" }}>
          {t("upload.batchImport.confirm.warning")}
        </p>
        {filesWithErrors.length > 0 && (
          <p
            style={{
              padding: "8px 12px",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "4px",
              color: "#7f1d1d",
              fontSize: "14px",
            }}
          >
            {t("upload.batchImport.confirm.skipNotice", { count: filesWithErrors.length })}
          </p>
        )}
        {validFilesWithoutErrors.length > 0 && (
          <div className="batch-import-confirm__list-wrap">
            <p style={{ fontWeight: "bold", marginBottom: "8px" }}>
              {t("upload.batchImport.confirm.pendingListTitle")}
            </p>
            <ul className="batch-import-confirm__list">
              {validFilesWithoutErrors.map((file) => (
                <li key={file.id} className="batch-import-confirm__item">
                  <div className="batch-import-confirm__row">
                    <span className="batch-import-confirm__type">{file.type}</span>
                    <span className="batch-import-confirm__name" title={file.name}>
                      {file.name}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  );
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "BatchImportConfirmModal.tsx")

@'
import { useCallback, useEffect, useRef, useState } from "react";
import type { CsvData, UploadedFile } from "./uploadTypes";

export function useUploadWorkflow() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const filesRef = useRef(files);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => prev.filter((file) => file.id !== fileId));
  }, []);

  const toggleFileExpanded = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, expanded: !file.expanded } : file
      )
    );
  }, []);

  const beginPdfValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "validating", validateProgress: 10 } : file
      )
    );
  }, []);

  const completePdfUpload = useCallback((fileId: string, processId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "uploaded",
              validateProgress: 100,
              processId,
              isValidated: true,
              validationErrors: undefined,
              hasUnsavedChanges: false,
              expanded: false,
              pdfConvertStatus: "not_started",
              pdfConvertJobId: undefined,
              pdfConvertProgress: 0,
              pdfConvertError: undefined,
            }
          : file
      )
    );
  }, []);

  const failPdfValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "uploaded", validateProgress: 0 } : file
      )
    );
  }, []);

  const beginCsvValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "validating", validateProgress: 10 } : file
      )
    );
  }, []);

  const setValidationUploadSource = useCallback((fileId: string, fileToUpload: File) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, file: fileToUpload, size: fileToUpload.size } : file
      )
    );
  }, []);

  const setValidationProgress = useCallback((fileId: string, validateProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, validateProgress } : file
      )
    );
  }, []);

  const prepareCsvValidationJob = useCallback((fileId: string, csvData: CsvData, jobId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validating",
              validateProgress: 50,
              csvData,
              expanded: true,
              processId: jobId,
              isValidated: false,
              validationErrors: undefined,
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const updateValidationPoll = useCallback((fileId: string, jobStatus: string, validateProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: jobStatus === "READY" || jobStatus === "FAILED" ? "validated" : "validating",
              validateProgress,
            }
          : file
      )
    );
  }, []);

  const completeValidationFailure = useCallback((fileId: string, message: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              isValidated: true,
              validationErrors: [{ row_index: 0, field: "system", error_code: "FAILED", message }],
            }
          : file
      )
    );
  }, []);

  const completeValidationWithErrors = useCallback((fileId: string, validationErrors: any[]) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              validateProgress: 100,
              isValidated: true,
              validationErrors,
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const completeValidationPassed = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              validateProgress: 100,
              isValidated: true,
              validationErrors: [],
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const failCsvValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "uploaded", validateProgress: 0 } : file
      )
    );
  }, []);

  const beginPdfConvert = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus: "queued",
              pdfConvertProgress: 10,
              pdfConvertError: undefined,
            }
          : file
      )
    );
  }, []);

  const attachPdfConvertJob = useCallback((fileId: string, jobId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, pdfConvertJobId: jobId } : file
      )
    );
  }, []);

  const updatePdfConvertProgress = useCallback((fileId: string, status: string, progress: number, fallbackError: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus:
                status === "COMPLETED"
                  ? "completed"
                  : status === "FAILED"
                  ? "failed"
                  : status === "UPLOADING"
                  ? "uploading"
                  : status === "PROCESSING"
                  ? "processing"
                  : status === "QUEUED"
                  ? "queued"
                  : "not_started",
              pdfConvertProgress: progress,
              pdfConvertError: status === "FAILED" ? fallbackError : undefined,
            }
          : file
      )
    );
  }, []);

  const replacePdfWithCsvFiles = useCallback((fileId: string, newCsvFiles: UploadedFile[]) => {
    setFiles((prev) => {
      const withoutPdf = prev.filter((file) => file.id !== fileId);
      return [...withoutPdf, ...newCsvFiles];
    });
  }, []);

  const failPdfConvert = useCallback((fileId: string, message: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus: "failed",
              pdfConvertProgress: 100,
              pdfConvertError: message,
            }
          : file
      )
    );
  }, []);

  const beginImport = useCallback((fileIds: string[], importProgress: number) => {
    const targetIds = new Set(fileIds);
    setFiles((prev) =>
      prev.map((file) =>
        targetIds.has(file.id)
          ? { ...file, status: "importing", importProgress }
          : file
      )
    );
  }, []);

  const setImportProgress = useCallback((fileId: string, importProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, importProgress } : file
      )
    );
  }, []);

  const completeImport = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "imported", importProgress: 100 } : file
      )
    );
  }, []);

  const resetImport = useCallback((fileIds: string[]) => {
    const targetIds = new Set(fileIds);
    setFiles((prev) =>
      prev.map((file) =>
        targetIds.has(file.id)
          ? { ...file, status: "validated", importProgress: 0 }
          : file
      )
    );
  }, []);

  const removeImportedFiles = useCallback((fileIds: string[]) => {
    const targetIds = new Set(fileIds);
    const remainingFiles = filesRef.current.filter((file) => !targetIds.has(file.id));
    setFiles(remainingFiles);
    return remainingFiles;
  }, []);

  return {
    files,
    setFiles,
    filesRef,
    removeFile,
    toggleFileExpanded,
    beginPdfValidation,
    completePdfUpload,
    failPdfValidation,
    beginCsvValidation,
    setValidationUploadSource,
    setValidationProgress,
    prepareCsvValidationJob,
    updateValidationPoll,
    completeValidationFailure,
    completeValidationWithErrors,
    completeValidationPassed,
    failCsvValidation,
    beginPdfConvert,
    attachPdfConvertJob,
    updatePdfConvertProgress,
    replacePdfWithCsvFiles,
    failPdfConvert,
    beginImport,
    setImportProgress,
    completeImport,
    resetImport,
    removeImportedFiles,
  };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "useUploadWorkflow.ts")

@'
export function toValidateProgress(jobStatus: string): number {
  switch (jobStatus) {
    case "UPLOADED":
      return 25;
    case "PARSING":
      return 45;
    case "VALIDATING":
      return 75;
    case "READY":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}

export function toImportProgress(jobStatus: string): number {
  switch (jobStatus) {
    case "COMMITTING":
      return 60;
    case "COMPLETED":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}

export function toPdfConvertProgress(convertStatus: string): number {
  switch (convertStatus) {
    case "NOT_STARTED":
      return 0;
    case "QUEUED":
      return 10;
    case "UPLOADING":
      return 25;
    case "PROCESSING":
      return 65;
    case "COMPLETED":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadProgress.ts")

@'
type TranslationFn = (key: string) => string;

interface UploadApiClientOptions {
  t: TranslationFn;
  getTenantHeaders: () => HeadersInit;
}

interface CreateImportJobInput {
  tableCode: string;
  allowDuplicate: boolean;
  file: File;
  filename: string;
}

interface UploadApiError extends Error {
  detail?: unknown;
  response?: unknown;
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const errorData = await response.json().catch(() => ({ detail: fallback }));
  if (typeof errorData.detail === "string") return errorData.detail;
  return errorData.detail?.detail || errorData.message || fallback;
}

async function throwApiError(response: Response, fallback: string): Promise<never> {
  const errorData = await response.json().catch(() => ({ detail: fallback }));
  const message =
    typeof errorData.detail === "string"
      ? errorData.detail
      : errorData.detail?.detail || errorData.message || fallback;
  const error = new Error(message) as UploadApiError;
  error.detail = errorData.detail;
  error.response = errorData;
  throw error;
}

export function createUploadApiClient({ t, getTenantHeaders }: UploadApiClientOptions) {
  return {
    async uploadPdf(file: File, filename: string) {
      const formData = new FormData();
      formData.append("file", file, filename);
      const response = await fetch("/api/upload/pdf", {
        method: "POST",
        headers: getTenantHeaders(),
        body: formData,
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.pdfUploadFailed"));
      }
      return response.json();
    },

    async createImportJob({ tableCode, allowDuplicate, file, filename }: CreateImportJobInput) {
      const formData = new FormData();
      formData.append("table_code", tableCode);
      formData.append("allow_duplicate", allowDuplicate ? "true" : "false");
      formData.append("files", file, filename);
      const response = await fetch("/api/v2/import/jobs", {
        method: "POST",
        headers: getTenantHeaders(),
        body: formData,
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.uploadFailed"));
      }
      return response.json();
    },

    async fetchPdfConvertStatus(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert/status`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchPdfConvertStatusFailed")));
      }
      return response.json();
    },

    async fetchPdfConvertedCsvOutputs(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert/outputs?include_csv_text=1`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchCsvOutputsFailed")));
      }
      return response.json();
    },

    async fetchImportJob(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchImportStatusFailed")));
      }
      return response.json();
    },

    async fetchImportErrors(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}/errors?page=1&page_size=200`, {
        headers: getTenantHeaders(),
      });
      return response.ok ? response.json() : [];
    },

    async triggerPdfConvert(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert`, {
        method: "POST",
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.triggerPdfConvertFailed"));
      }
      return response.json();
    },

    async commitImportJob(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}/commit`, {
        method: "POST",
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.importFailed"));
      }
      return response.json();
    },
  };
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadApiClient.ts")

@'
import { useMemo } from "react";
import { TENANT_STORAGE_KEY } from "../../services/tenant";
import { createUploadApiClient } from "./uploadApiClient";

type TranslationFn = (key: string) => string;

function buildTenantHeaders(): HeadersInit {
  const id = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  return id ? { "X-Tenant-Id": id } : {};
}

export function useUploadApi(t: TranslationFn) {
  return useMemo(
    () => createUploadApiClient({ t, getTenantHeaders: buildTenantHeaders }),
    [t]
  );
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "useUploadApi.ts")

@'
export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function scheduleAfterDelay(ms: number, action: () => void): void {
  window.setTimeout(action, ms);
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadAsyncUtils.ts")

@'
import { scheduleAfterDelay } from "./uploadAsyncUtils";
import { showBatchImportCleanupToast, showSingleImportCleanupToast } from "./uploadImportToastUtils";
import type { UploadedFile } from "./uploadTypes";

type ShowToast = (type: "success" | "error" | "info", message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface BatchCleanupOptions {
  ids: string[];
  removeImportedFiles: (ids: string[]) => UploadedFile[];
  showToast: ShowToast;
  t: TranslationFn;
}

interface SingleCleanupOptions {
  id: string;
  filesRef: { current: UploadedFile[] };
  removeImportedFiles: (ids: string[]) => UploadedFile[];
  showToast: ShowToast;
  t: TranslationFn;
}

export function scheduleBatchPostImportCleanup({
  ids,
  removeImportedFiles,
  showToast,
  t,
}: BatchCleanupOptions): void {
  scheduleAfterDelay(2000, () => {
    const remainingFiles = removeImportedFiles(ids);
    showBatchImportCleanupToast({
      remainingCount: remainingFiles.length,
      showToast,
      t,
    });
  });
}

export function scheduleSinglePostImportCleanup({
  id,
  filesRef,
  removeImportedFiles,
  showToast,
  t,
}: SingleCleanupOptions): void {
  scheduleAfterDelay(2000, () => {
    const currentFiles = filesRef.current;
    const remainingFiles = removeImportedFiles([id]);
    showSingleImportCleanupToast({
      remainingCount: remainingFiles.length,
      wasOnlyFile: currentFiles.length === 1,
      showToast,
      t,
    });
  });
}
'@ | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "uploadImportCleanupUtils.ts")

$content = Get-Content -Raw -Encoding UTF8 $uploadPagePath

if ($content -notmatch "uploadFileUtils") {
    $content = $content.Replace(
        'import { TENANT_STORAGE_KEY } from "../services/tenant";',
        "import { TENANT_STORAGE_KEY } from `"../services/tenant`";`r`nimport { createUploadApiClient } from `"./upload/uploadApiClient`";`r`nimport type { CsvData, FileType, UploadedFile } from `"./upload/uploadTypes`";`r`nimport { MAX_SIZE_BYTES, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from `"./upload/uploadFileUtils`";`r`nimport { toImportProgress, toPdfConvertProgress, toValidateProgress } from `"./upload/uploadProgress`";`r`nimport { useUploadWorkflow } from `"./upload/useUploadWorkflow`";"
    )
}

if ($content -notmatch 'import \{ fileEligibleForBatchImport') {
    $content = $content.Replace(
        'import { toImportProgress, toPdfConvertProgress, toValidateProgress } from "./upload/uploadProgress";',
        "import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from `"./upload/uploadEligibility`";`r`nimport { toImportProgress, toPdfConvertProgress, toValidateProgress } from `"./upload/uploadProgress`";"
    )
}

if ($content -notmatch 'import \{ FileDropArea \}') {
    $content = $content.Replace(
        'import { useUploadWorkflow } from "./upload/useUploadWorkflow";',
        "import { FileDropArea } from `"./upload/FileDropArea`";`r`nimport { useUploadWorkflow } from `"./upload/useUploadWorkflow`";"
    )
}

$content = $content.Replace(
    'import { useUploadWorkflow } from "./upload/useUploadWorkflow";',
    'import { useUploadWorkflow } from "./upload/useUploadWorkflow";'
)

$content = $content.Replace(
    'import { MAX_SIZE_BYTES, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from "./upload/uploadFileUtils";',
    'import { MAX_SIZE_BYTES, buildUploadedCsvFilesFromPdfOutputs, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from "./upload/uploadFileUtils";'
)

$localEligibilityPattern = '(?s)\r?\n  const fileHasValidationErrors = \(f: UploadedFile\): boolean => \{\r?\n    return Array\.isArray\(f\.validationErrors\) && f\.validationErrors\.length > 0;\r?\n  \};\r?\n\r?\n  const fileEligibleForValidate = \(f: UploadedFile\): boolean => \{\r?\n.*?    return false;\r?\n  \};\r?\n'
$content = [regex]::Replace($content, $localEligibilityPattern, "`r`n", 1)

$fileDropAreaPattern = '(?s)\r?\n/\* ------------.*?\*/\r?\n\r?\ninterface FileDropAreaProps \{.*?function FileDropArea\(\{ onFiles \}: FileDropAreaProps\) \{.*?\r?\n\}\r?\n\r?\n(?=/\* ------------.*?UploadedFileCardProps)'
$content = [regex]::Replace($content, $fileDropAreaPattern, "`r`n", 1)

$uploadedFileCardStart = $content.IndexOf("interface UploadedFileCardProps")
if ($uploadedFileCardStart -ge 0) {
    $uploadedFileCardCommentStart = $content.LastIndexOf("/*", $uploadedFileCardStart)
    if ($uploadedFileCardCommentStart -ge 0) {
        $uploadedFileCardStart = $uploadedFileCardCommentStart
    }

    $uploadedFileCardSource = $content.Substring($uploadedFileCardStart).TrimStart()
    $uploadedFileCardSource = $uploadedFileCardSource.Replace(
        "function UploadedFileCard({",
        "export function UploadedFileCard({"
    )

    $uploadedFileCardModule = @'
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ProgressBar } from "../../components/common/ProgressBar";
import type { CsvData, UploadedFile } from "./uploadTypes";

const EDIT_ENABLED =
  String((import.meta as any).env?.VITE_ENABLE_CSV_EDIT ?? "true").toLowerCase() === "true";

'@ + $uploadedFileCardSource

    $uploadedFileCardModule | Set-Content -Encoding UTF8 (Join-Path $moduleRoot "UploadedFileCard.tsx")
    $content = $content.Substring(0, $uploadedFileCardStart).TrimEnd() + "`r`n"
}

if ($content -notmatch 'import \{ UploadedFileCard \}') {
    $content = $content.Replace(
        'import { FileDropArea } from "./upload/FileDropArea";',
        "import { FileDropArea } from `"./upload/FileDropArea`";`r`nimport { UploadedFileCard } from `"./upload/UploadedFileCard`";"
    )
}

if ($content -notmatch 'import \{ BatchActionBar \}') {
    $content = $content.Replace(
        'import { FileDropArea } from "./upload/FileDropArea";',
        "import { BatchActionBar } from `"./upload/BatchActionBar`";`r`nimport { FileDropArea } from `"./upload/FileDropArea`";"
    )
}

if ($content -notmatch 'import \{ BatchImportConfirmModal \}') {
    $content = $content.Replace(
        'import { BatchActionBar } from "./upload/BatchActionBar";',
        "import { BatchActionBar } from `"./upload/BatchActionBar`";`r`nimport { BatchImportConfirmModal } from `"./upload/BatchImportConfirmModal`";"
    )
}

if ($content -notmatch 'uploadBatchOrchestrator') {
    $content = $content.Replace(
        'import { toImportProgress, toPdfConvertProgress, toValidateProgress } from "./upload/uploadProgress";',
        "import { runBatchConversion, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from `"./upload/uploadBatchOrchestrator`";`r`nimport { toImportProgress, toPdfConvertProgress, toValidateProgress } from `"./upload/uploadProgress`";"
    )
}

if ($content -notmatch 'uploadPdfConversionOrchestrator') {
    $content = $content.Replace(
        'import { toImportProgress, toPdfConvertProgress, toValidateProgress } from "./upload/uploadProgress";',
        "import { runPdfConversion } from `"./upload/uploadPdfConversionOrchestrator`";`r`nimport { toImportProgress, toPdfConvertProgress, toValidateProgress } from `"./upload/uploadProgress`";"
    )
}

if ($content -notmatch 'uploadValidationOrchestrator') {
    $content = $content.Replace(
        'import { runPdfConversion } from "./upload/uploadPdfConversionOrchestrator";',
        "import { runPdfConversion } from `"./upload/uploadPdfConversionOrchestrator`";`r`nimport { runCsvValidationJob, runPdfValidation } from `"./upload/uploadValidationOrchestrator`";"
    )
}

$content = $content.Replace(
    'import { runPdfValidation } from "./upload/uploadValidationOrchestrator";',
    'import { runCsvValidationJob, runPdfValidation } from "./upload/uploadValidationOrchestrator";'
)

if ($content -notmatch 'uploadCsvEditUtils') {
    $content = $content.Replace(
        'import { MAX_SIZE_BYTES, buildUploadedCsvFilesFromPdfOutputs, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from "./upload/uploadFileUtils";',
        "import { buildCsvText, saveCsvChangesInFiles, updateCsvCellInFiles } from `"./upload/uploadCsvEditUtils`";`r`nimport { MAX_SIZE_BYTES, buildUploadedCsvFilesFromPdfOutputs, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from `"./upload/uploadFileUtils`";"
    )
}

if ($content -notmatch 'uploadCsvEditToastUtils') {
    $content = $content.Replace(
        'import { saveCsvChangesInFiles, updateCsvCellInFiles } from "./upload/uploadCsvEditUtils";',
        "import { saveCsvChangesInFiles, updateCsvCellInFiles } from `"./upload/uploadCsvEditUtils`";`r`nimport { showCsvChangesAppliedToast, showCsvEditDisabledToast, showCsvSaveErrorToast } from `"./upload/uploadCsvEditToastUtils`";"
    )
}

if ($content -notmatch 'uploadFileAddUtils') {
    $content = $content.Replace(
        'import { saveCsvChangesInFiles, updateCsvCellInFiles } from "./upload/uploadCsvEditUtils";',
        "import { saveCsvChangesInFiles, updateCsvCellInFiles } from `"./upload/uploadCsvEditUtils`";`r`nimport { buildUploadFilesToAdd } from `"./upload/uploadFileAddUtils`";"
    )
}

if ($content -notmatch 'uploadFileAddToastUtils') {
    $content = $content.Replace(
        'import { buildUploadFilesToAdd } from "./upload/uploadFileAddUtils";',
        "import { buildUploadFilesToAdd } from `"./upload/uploadFileAddUtils`";`r`nimport { showFileAddResultToasts } from `"./upload/uploadFileAddToastUtils`";"
    )
}

$handleFilesPattern = '(?s)  const handleFiles = \(fileList: FileList \| null\) => \{\r?\n    if \(!fileList\) return;\r?\n\r?\n    const newFiles: UploadedFile\[\] = \[\];\r?\n    Array\.from\(fileList\)\.forEach\(\(file\) => \{.*?\r?\n    \}\r?\n  \};'
$handleFilesReplacement = @'
  const handleFiles = (fileList: FileList | null) => {
    const result = buildUploadFilesToAdd({
      fileList,
      existingFiles: files,
      confirmLikelyDuplicate: (file) =>
        window.confirm("\u5075\u6e2c\u5230\u7591\u4f3c\u91cd\u8907\u6a94\u6848\uff1a" + file.name + "\n\u662f\u5426\u4ecd\u8981\u52a0\u5165\u4e0a\u50b3\u6e05\u55ae\uff1f"),
    });

    showFileAddResultToasts({
      notices: result.notices,
      addedCount: result.files.length,
      showToast,
      t,
    });

    if (result.files.length) {
      setFiles((prev) => [...prev, ...result.files]);
    }
  };
'@
$content = [regex]::Replace($content, $handleFilesPattern, $handleFilesReplacement, 1)

$handleFilesAnyPattern = '(?s)  const handleFiles = \(fileList: FileList \| null\) => \{.*?\r?\n  \};\r?\n\r?\n(?=  const handleValidate\s*=)'
$content = [regex]::Replace($content, $handleFilesAnyPattern, ($handleFilesReplacement + "`r`n`r`n"), 1)

$handleFilesToValidationPattern = '(?s)  const handleFiles = \(fileList: FileList \| null\) => \{.*?\r?\n  \};\r?\n\r?\n(?=  const handleValidate\s*=)'
$content = [regex]::Replace($content, $handleFilesToValidationPattern, ($handleFilesReplacement + "`r`n`r`n"), 1)

$content = $content.Replace(
    'import type { CsvData, FileType, UploadedFile } from "./upload/uploadTypes";',
    'import type { CsvData } from "./upload/uploadTypes";'
)

$content = $content.Replace(
    'import { MAX_SIZE_BYTES, buildUploadedCsvFilesFromPdfOutputs, deriveLotNoFromFilename, detectFileType, normalizeP3LotNo, normalizeLotNo, parseCsv } from "./upload/uploadFileUtils";',
    'import { buildUploadedCsvFilesFromPdfOutputs, parseCsv } from "./upload/uploadFileUtils";'
)

$content = $content.Replace(
    'import { buildCsvText, saveCsvChangesInFiles, updateCsvCellInFiles } from "./upload/uploadCsvEditUtils";',
    'import { saveCsvChangesInFiles, updateCsvCellInFiles } from "./upload/uploadCsvEditUtils";'
)

$content = $content.Replace(
    'import { runBatchConversion, runBatchValidation, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";',
    'import { runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";'
)
$content = $content.Replace(
    'import { runBatchConversion, runBatchImport, runBatchValidation, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";',
    'import { runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";'
)
$content = $content.Replace(
    'import { runBatchConversion, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";',
    'import { runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";'
)

$batchActionPattern = '(?s)\{files\.length > 0 && \(\r?\n\s*<div className="batch-actions">.*?\r?\n\s*</div>\r?\n\s*\)\}'
$batchActionReplacement = @'
{files.length > 0 && (
            <BatchActionBar
              files={files}
              isValidatingAll={isValidatingAll}
              isConvertingAll={isConvertingAll}
              onValidateAll={handleValidateAll}
              onConvertAll={handleConvertAll}
              onBatchImport={handleBatchImportClick}
            />
          )}
'@
$content = [regex]::Replace($content, $batchActionPattern, $batchActionReplacement, 1)

$batchConfirmModalPattern = '(?s)\r?\n\s*<Modal\r?\n\s*open=\{showBatchImportConfirm\}.*?maxWidth="min\(720px, 92vw\)"\r?\n\s*>\r?\n\s*\{\(\(\) => \{\r?\n\s*const validFilesWithoutErrors = files\.filter\(fileEligibleForBatchImport\);.*?\r?\n\s*\}\)\(\)\}\r?\n\s*</Modal>'
$batchConfirmModalReplacement = @'

      <BatchImportConfirmModal
        open={showBatchImportConfirm}
        files={files}
        onClose={() => setShowBatchImportConfirm(false)}
        onConfirm={performBatchImport}
      />
'@
$content = [regex]::Replace($content, $batchConfirmModalPattern, $batchConfirmModalReplacement, 1)

$validateOutcomePattern = '(?s)\r?\n  type ValidateOutcome =\r?\n    \| \{ outcome: ''passed''; totalRows: number \}\r?\n    \| \{ outcome: ''errors''; totalRows: number; errorCount: number \}\r?\n    \| \{ outcome: ''failed''; message: string \};\r?\n'
$content = [regex]::Replace($content, $validateOutcomePattern, "`r`n", 1)

$handleValidateAllPattern = '(?s)  const handleValidateAll = async \(\) => \{\r?\n    const currentFiles = filesRef\.current;\r?\n    const targets = currentFiles\.filter\(fileEligibleForValidate\);.*?\r?\n  \};\r?\n\r?\n'
$handleValidateAllReplacement = @'
  const handleValidateAll = () =>
    runBatchValidation({
      filesRef,
      setIsValidatingAll,
      handleValidate,
      showToast,
      t,
    });

'@
$content = [regex]::Replace($content, $handleValidateAllPattern, $handleValidateAllReplacement, 1)

$handleConvertAllPattern = '(?s)  const handleConvertAll = async \(\) => \{\r?\n    const currentFiles = filesRef\.current;\r?\n    const targets = currentFiles\.filter\(fileEligibleForConvert\);.*?\r?\n  \};\r?\n\r?\n'
$handleConvertAllReplacement = @'
  const handleConvertAll = () =>
    runBatchConversion({
      filesRef,
      setIsConvertingAll,
      handlePdfConvert,
      showToast,
      t,
    });

'@
$content = [regex]::Replace($content, $handleConvertAllPattern, $handleConvertAllReplacement, 1)

$batchImportLoopPattern = '(?s)    try \{\r?\n      let totalImported = 0;\r?\n      \r?\n      for \(const \[index, file\] of validatedFiles\.entries\(\)\) \{.*?\r?\n        completeImport\(file\.id\);\r?\n      \}'
$batchImportLoopReplacement = @'
    try {
      const totalImported = await runBatchImport({
        validatedFiles,
        commitImportJob: uploadApi.commitImportJob,
        fetchImportJob: uploadApi.fetchImportJob,
        sleep,
        setImportProgress,
        completeImport,
        toImportProgress,
        showToast,
        t,
      })
'@
$content = [regex]::Replace($content, $batchImportLoopPattern, $batchImportLoopReplacement, 1)

$singleImportLoopPattern = '(?s)    try \{\r?\n      const jobId = target\.processId as string;\r?\n      const commitResponse = \{ ok: true, json: async \(\) => uploadApi\.commitImportJob\(jobId\) \} as any;\r?\n\r?\n\s*setImportProgress\(id, 60\);\r?\n\r?\n      if \(!commitResponse\.ok\) \{.*?\r?\n      completeImport\(id\);'
$singleImportLoopReplacement = @'
    try {
      await runSingleImport({
        file: target,
        commitImportJob: uploadApi.commitImportJob,
        fetchImportJob: uploadApi.fetchImportJob,
        sleep,
        setImportProgress,
        completeImport,
        toImportProgress,
        t,
      });
'@
$content = [regex]::Replace($content, $singleImportLoopPattern, $singleImportLoopReplacement, 1)

$pdfConvertPollPattern = '(?s)      const trigger = await uploadApi\.triggerPdfConvert\(target\.processId\);\r?\n      attachPdfConvertJob\(fileId, trigger\.job_id\);\r?\n\r?\n      // Poll status until completed/failed\..*?      showToast\(''info'', t\(''upload\.toast\.pdfConvertStillProcessing''\)\);'
$pdfConvertPollReplacement = @'
      const conversionResult = await runPdfConversion({
        processId: target.processId,
        triggerPdfConvert: uploadApi.triggerPdfConvert,
        fetchPdfConvertStatus: uploadApi.fetchPdfConvertStatus,
        sleep,
        attachPdfConvertJob: (jobId) => attachPdfConvertJob(fileId, jobId),
        updatePdfConvertProgress: (status, progress, errorText) =>
          updatePdfConvertProgress(fileId, status, progress, errorText),
        toPdfConvertProgress,
        fallbackErrorText: t('upload.toast.pdfConvertFailed'),
      });

      if (conversionResult.outcome === 'completed') {
        try {
          showToast('info', t('upload.toast.pdfConvertFetchingCsv'), { key: `pdfIngest:${target.processId}`, durationMs: null });
          const outputsResp = await uploadApi.fetchPdfConvertedCsvOutputs(target.processId);
          const outputs = Array.isArray(outputsResp) ? outputsResp : (outputsResp?.outputs || []);

          const newCsvFiles = await buildUploadedCsvFilesFromPdfOutputs(
            outputs,
            filesRef.current.map((file) => file.name)
          );

          if (newCsvFiles.length) {
            replacePdfWithCsvFiles(fileId, newCsvFiles);
            showToast(
              'success',
              t('upload.toast.pdfConvertGotCsv', { count: newCsvFiles.length }),
              { key: `pdfIngest:${target.processId}`, durationMs: 2500 }
            );
          } else {
            showToast('info', t('upload.toast.pdfConvertNoCsv'), { key: `pdfIngest:${target.processId}`, durationMs: 2500 });
          }
        } catch (e: any) {
          showToast(
            'error',
            e?.message || t('upload.toast.pdfConvertCreateCsvJobFailed'),
            { key: `pdfIngest:${target.processId}`, durationMs: 3000 }
          );
        }
        return true;
      }

      if (conversionResult.outcome === 'failed') {
        failPdfConvert(fileId, conversionResult.message || t('upload.toast.pdfConvertFailed'));
        showToast('error', conversionResult.message);
        return false;
      }

      showToast('info', t('upload.toast.pdfConvertStillProcessing'));
'@
$content = [regex]::Replace($content, $pdfConvertPollPattern, $pdfConvertPollReplacement, 1)

$buildCsvTextPattern = '(?s)\r?\n  const buildCsvText = \(csv: CsvData\): string => \{\r?\n    const escapeCell = \(cell: string\) => \{.*?\r?\n  \};\r?\n\r?\n'
$content = [regex]::Replace($content, $buildCsvTextPattern, "`r`n", 1)

$updateCellPattern = '(?s)  const updateCell = \(\r?\n    fileId: string,\r?\n    rowIndex: number,\r?\n    colIndex: number,\r?\n    value: string\r?\n  \) => \{\r?\n    if \(!EDIT_ENABLED\) return;\r?\n    setFiles\(\(prev\) =>\r?\n      prev\.map\(\(f\) => \{.*?\r?\n      \}\)\r?\n    \);\r?\n  \};'
$updateCellReplacement = @'
  const updateCell = (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => {
    if (!EDIT_ENABLED) return;
    setFiles((prev) => updateCsvCellInFiles(prev, fileId, rowIndex, colIndex, value));
  };
'@
$content = [regex]::Replace($content, $updateCellPattern, $updateCellReplacement, 1)

$saveChangesPattern = '(?s)  const handleSaveChanges = async \(fileId: string\) => \{\r?\n    if \(!EDIT_ENABLED\) \{.*?\r?\n    showToast\(''success'', t\(''upload\.toast\.changesAppliedRevalidate''\)\);\r?\n  \};'
$saveChangesReplacement = @'
  const handleSaveChanges = async (fileId: string) => {
    if (!EDIT_ENABLED) {
      showCsvEditDisabledToast({ showToast, t });
      return;
    }

    const result = saveCsvChangesInFiles(files, fileId);
    if (result.outcome === "not-found-or-clean") return;
    if (result.outcome === "unsupported-backend") {
      showCsvSaveErrorToast({ showToast, t });
      return;
    }

    setFiles(result.files);
    showCsvChangesAppliedToast({ showToast, t });
  };
'@
$content = [regex]::Replace($content, $saveChangesPattern, $saveChangesReplacement, 1)

$content = $content.Replace(
    "      showToast(`"info`", t('upload.editDisabledNotice'));",
    "      showCsvEditDisabledToast({ showToast, t });"
)

$content = $content.Replace(
    "      showToast('error', t('upload.errors.saveError'));",
    "      showCsvSaveErrorToast({ showToast, t });"
)

$content = $content.Replace(
    "    showToast('success', t('upload.toast.changesAppliedRevalidate'));",
    "    showCsvChangesAppliedToast({ showToast, t });"
)

$pdfValidationPattern = '(?s)    if \(target\.type === ''PDF''\) \{\r?\n      beginPdfValidation\(fileId\);\r?\n\r?\n      try \{\r?\n        const data = await uploadApi\.uploadPdf\(target\.file, target\.name\);\r?\n        completePdfUpload\(fileId, data\.process_id\);\r?\n\r?\n        if \(!options\?\.silentToast\) showToast\(''success'', t\(''upload\.toast\.pdfUploadedReadyToConvert''\)\);\r?\n        return \{ outcome: ''passed'', totalRows: 0 \};\r?\n      \} catch \(e: any\) \{\r?\n        failPdfValidation\(fileId\);\r?\n        const msg = e\?\.message \|\| t\(''upload\.errors\.pdfUploadFailed''\);\r?\n        if \(!options\?\.silentToast\) showToast\(''error'', msg\);\r?\n        return \{ outcome: ''failed'', message: msg \};\r?\n      \}\r?\n    \}'
$pdfValidationReplacement = @'
    if (target.type === 'PDF') {
      const result = await runPdfValidation({
        file: target,
        uploadPdf: uploadApi.uploadPdf,
        beginPdfValidation,
        completePdfUpload,
        failPdfValidation,
        fallbackErrorText: t('upload.errors.pdfUploadFailed'),
      });
      if (!options?.silentToast) {
        if (result.outcome === 'passed') {
          showToast('success', t('upload.toast.pdfUploadedReadyToConvert'));
        } else {
          showToast('error', result.message);
        }
      }
      return result;
    }
'@
$content = [regex]::Replace($content, $pdfValidationPattern, $pdfValidationReplacement, 1)

$csvValidationJobPattern = '(?s)    beginCsvValidation\(fileId\);\s*try \{.*?if \(!lastJob \|\| \(lastJob\.status !== ''READY'' && lastJob\.status !== ''FAILED''\)\) \{\s*throw new Error\(t\(''upload\.errors\.validationTimeout''\)\);\s*\}'
$csvValidationJobReplacement = @'
    try {
      const { jobId, lastJob } = await runCsvValidationJob({
        file: target,
        createImportJob: uploadApi.createImportJob,
        parseCsv,
        confirmDuplicate: (duplicateOf) =>
          window.confirm(
            t('upload.confirm.duplicateFile')
              .replace('{{filename}}', target.name)
              .replace('{{duplicateOf}}', duplicateOf)
          ),
        sleep,
        beginCsvValidation,
        setValidationUploadSource,
        setValidationProgress,
        prepareCsvValidationJob,
        updateValidationPoll,
        fetchImportJob: uploadApi.fetchImportJob,
        toValidateProgress,
        validationTimeoutText: t('upload.errors.validationTimeout'),
      });
'@
$content = [regex]::Replace($content, $csvValidationJobPattern, $csvValidationJobReplacement, 1)

$flattenValidationErrorsPattern = '(?s)        const flattenedErrors = \(Array\.isArray\(errorRows\) \? errorRows : \[\]\)\.flatMap\(\(row: any\) => \{\r?\n          const rowIndex0 = Math\.max\(0, Number\(row\.row_index \|\| 1\) - 1\);.*?\r?\n        \}\);'
$content = [regex]::Replace($content, $flattenValidationErrorsPattern, "        const flattenedErrors = flattenImportValidationErrors(errorRows);", 1)

$content = $content.Replace(
    "      if (!options?.silentToast) {`r`n        if (result.outcome === 'passed') {`r`n          showToast('success', t('upload.toast.pdfUploadedReadyToConvert'));`r`n        } else {`r`n          showToast('error', result.message);`r`n        }`r`n      }",
    "      showValidationResultToast({`r`n        kind: `"pdf`",`r`n        silent: options?.silentToast,`r`n        result,`r`n        showToast,`r`n        t,`r`n      });"
)

$pdfValidationToastPattern = '(?s)      if \(!options\?\.silentToast\) \{\r?\n        if \(result\.outcome === ''passed''\) \{\r?\n          showToast\(''success'', t\(''upload\.toast\.pdfUploadedReadyToConvert''\)\);\r?\n        \} else \{\r?\n          showToast\(''error'', result\.message\);\r?\n        \}\r?\n      \}'
$pdfValidationToastReplacement = @'
      showValidationResultToast({
        kind: "pdf",
        silent: options?.silentToast,
        result,
        showToast,
        t,
      });
'@
$content = [regex]::Replace($content, $pdfValidationToastPattern, $pdfValidationToastReplacement, 1)

$content = $content.Replace(
    '      if (!options?.silentToast) showToast("info", t(''upload.editDisabledNotice''));',
    '      showValidationResultToast({ kind: "edit-disabled", silent: options?.silentToast, showToast, t });'
)

$content = $content.Replace(
    "        if (!options?.silentToast) showToast('error', t('upload.toast.validationFailedWithMessage', { fileName: target.name, message }));",
    "        showValidationResultToast({`r`n          kind: `"csv-failed`",`r`n          silent: options?.silentToast,`r`n          fileName: target.name,`r`n          message,`r`n          showToast,`r`n          t,`r`n        });"
)

$content = $content.Replace(
    "        if (!options?.silentToast) {`r`n          showToast('error', t('upload.toast.validationDoneWithInvalidRowsNoEdit', { fileName: target.name, totalRows, errorCount }));`r`n        }",
    "        showValidationResultToast({`r`n          kind: `"csv-errors`",`r`n          silent: options?.silentToast,`r`n          fileName: target.name,`r`n          totalRows,`r`n          errorCount,`r`n          showToast,`r`n          t,`r`n        });"
)

$content = $content.Replace(
    "        if (!options?.silentToast) showToast('success', t('upload.toast.validationPassedAllRows', { fileName: target.name, totalRows }));",
    "        showValidationResultToast({`r`n          kind: `"csv-passed`",`r`n          silent: options?.silentToast,`r`n          fileName: target.name,`r`n          totalRows,`r`n          showToast,`r`n          t,`r`n        });"
)

$content = $content.Replace(
    '      if (!options?.silentToast) showToast("error", errorMessage);',
    '      showValidationResultToast({ kind: "csv-exception", silent: options?.silentToast, message: errorMessage, showToast, t });'
)

$batchUnavailablePattern = '(?s)      if \(filesWithErrors\.length > 0\) \{\r?\n        showToast\("error", t\(''upload\.batchImport\.title\.hasErrors'', \{ count: filesWithErrors\.length \}\)\);\r?\n      \} else if \(unvalidatedFiles\.length > 0\) \{\r?\n        showToast\("error", t\(''upload\.batchImport\.title\.notValidated'', \{ count: unvalidatedFiles\.length \}\)\);\r?\n      \} else \{\r?\n        showToast\("error", t\(''upload\.batchImport\.title\.noValidated''\)\);\r?\n      \}'
$batchUnavailableReplacement = @'
      showBatchImportUnavailableToast({
        filesWithErrorsCount: filesWithErrors.length,
        unvalidatedFilesCount: unvalidatedFiles.length,
        showToast,
        t,
      });
'@
$content = [regex]::Replace($content, $batchUnavailablePattern, $batchUnavailableReplacement)

$content = $content.Replace(
    "      showToast(`"info`", t('upload.batchImport.info.multiUploadSkipErrors', { errorCount: filesWithErrors.length, validCount: validatedFiles.length }));",
    "      showBatchImportSkipErrorsToast({`r`n        errorCount: filesWithErrors.length,`r`n        validCount: validatedFiles.length,`r`n        showToast,`r`n        t,`r`n      });"
)

$batchStartToastPattern = '(?s)    showToast\(\r?\n      "info",\r?\n      isSingleFile\r?\n        \? t\(''upload\.batchImport\.toast\.startSingle''\)\r?\n        : t\(''upload\.batchImport\.toast\.startBatch'', \{ count: validatedFiles\.length \}\),\r?\n      \{ key: ''import'', durationMs: null \}\r?\n    \);'
$batchStartToastReplacement = @'
    showBatchImportStartToast({
      isSingleFile,
      fileCount: validatedFiles.length,
      showToast,
      t,
    });
'@
$content = [regex]::Replace($content, $batchStartToastPattern, $batchStartToastReplacement, 1)

$batchCompletedToastPattern = '(?s)      showToast\(\r?\n        "success",\r?\n        isSingleFile\r?\n          \? t\(''upload\.batchImport\.toast\.completedSingle'', \{ fileCount: validatedFiles\.length, rowCount: totalImported \}\)\r?\n          : t\(''upload\.batchImport\.toast\.completedBatch'', \{ fileCount: validatedFiles\.length, rowCount: totalImported \}\),\r?\n        \{ key: ''import'', durationMs: 2500 \}\r?\n      \);'
$batchCompletedToastReplacement = @'
      showBatchImportCompletedToast({
        isSingleFile,
        fileCount: validatedFiles.length,
        rowCount: totalImported,
        showToast,
        t,
      });
'@
$content = [regex]::Replace($content, $batchCompletedToastPattern, $batchCompletedToastReplacement, 1)

$batchCleanupToastPattern = '(?s)        if \(remainingFiles\.length > 0\) \{\r?\n          showToast\("info", t\(''upload\.batchImport\.toast\.remainingFiles'', \{ count: remainingFiles\.length \}\)\);\r?\n        \} else \{\r?\n          showToast\("info", t\(''upload\.batchImport\.toast\.allDone''\)\);\r?\n        \}'
$batchCleanupToastReplacement = @'
        showBatchImportCleanupToast({
          remainingCount: remainingFiles.length,
          showToast,
          t,
        });
'@
$content = [regex]::Replace($content, $batchCleanupToastPattern, $batchCleanupToastReplacement, 1)

$content = $content.Replace(
    '      showToast("error", errorMessage, { key: ''import'', durationMs: 4000 });',
    '      showImportErrorToast({ message: errorMessage, showToast, t });'
)

$content = $content.Replace(
    "      showToast('error', t('upload.toast.missingFileOrJobId'));",
    "      showMissingImportTargetToast({ showToast, t });"
)

$content = $content.Replace(
    "    showToast('info', t('upload.toast.importStarting', { fileName: target.name }), { key: 'import', durationMs: null });",
    "    showSingleImportStartToast({ fileName: target.name, showToast, t });"
)

$content = $content.Replace(
    "      showToast('success', t('upload.toast.importCompleted', { fileName: target.name }), { key: 'import', durationMs: 2500 });",
    "      showSingleImportCompletedToast({ fileName: target.name, showToast, t });"
)

$singleCleanupToastPattern = '(?s)        if \(currentFiles\.length === 1\) \{\r?\n          showToast\(''info'', t\(''upload\.toast\.pageResetContinueUpload''\)\);\r?\n        \} \r?\n        // .*?\r?\n        else \{\r?\n          showToast\(''info'', t\(''upload\.batchImport\.toast\.remainingFiles'', \{ count: remainingFiles\.length \}\)\);\r?\n        \}'
$singleCleanupToastReplacement = @'
        showSingleImportCleanupToast({
          remainingCount: remainingFiles.length,
          wasOnlyFile: currentFiles.length === 1,
          showToast,
          t,
        });
'@
$content = [regex]::Replace($content, $singleCleanupToastPattern, $singleCleanupToastReplacement, 1)

$content = $content.Replace(
    "      setTimeout(() => {",
    "      scheduleAfterDelay(2000, () => {"
)

$content = $content.Replace(
    "      }, 2000);",
    "      });"
)

$content = $content.Replace(
    "      showToast('error', t('upload.toast.missingProcessIdUploadPdf'));",
    "      showMissingPdfConvertProcessToast({ showToast, t });"
)

$content = $content.Replace(
    "          showToast('info', t('upload.toast.pdfConvertFetchingCsv'), { key: `pdfIngest:${target.processId}`, durationMs: null });",
    "          showPdfConvertFetchingCsvToast({ processId: target.processId, showToast, t });"
)

$pdfConvertFetchingToastPattern = "showToast\('info', t\('upload\.toast\.pdfConvertFetchingCsv'\), \{ key: ``pdfIngest:\$\{target\.processId\}``, durationMs: null \}\);"
$content = [regex]::Replace(
    $content,
    $pdfConvertFetchingToastPattern,
    "showPdfConvertFetchingCsvToast({ processId: target.processId, showToast, t });",
    1
)

$pdfConvertGotCsvToastPattern = '(?s)            showToast\(\r?\n              ''success'',\r?\n              t\(''upload\.toast\.pdfConvertGotCsv'', \{ count: newCsvFiles\.length \}\),\r?\n              \{ key: `pdfIngest:\$\{target\.processId\}`, durationMs: 2500 \}\r?\n            \);'
$content = [regex]::Replace(
    $content,
    $pdfConvertGotCsvToastPattern,
    "            showPdfConvertGotCsvToast({ processId: target.processId, count: newCsvFiles.length, showToast, t });",
    1
)

$content = $content.Replace(
    "            showToast('info', t('upload.toast.pdfConvertNoCsv'), { key: `pdfIngest:${target.processId}`, durationMs: 2500 });",
    "            showPdfConvertNoCsvToast({ processId: target.processId, showToast, t });"
)

$pdfConvertNoCsvToastPattern = "showToast\('info', t\('upload\.toast\.pdfConvertNoCsv'\), \{ key: ``pdfIngest:\$\{target\.processId\}``, durationMs: 2500 \}\);"
$content = [regex]::Replace(
    $content,
    $pdfConvertNoCsvToastPattern,
    "showPdfConvertNoCsvToast({ processId: target.processId, showToast, t });",
    1
)

$pdfConvertOutputErrorToastPattern = '(?s)          showToast\(\r?\n            ''error'',\r?\n            e\?\.message \|\| t\(''upload\.toast\.pdfConvertCreateCsvJobFailed''\),\r?\n            \{ key: `pdfIngest:\$\{target\.processId\}`, durationMs: 3000 \}\r?\n          \);'
$content = [regex]::Replace(
    $content,
    $pdfConvertOutputErrorToastPattern,
    "          showPdfConvertOutputErrorToast({`r`n            processId: target.processId,`r`n            message: e?.message || t('upload.toast.pdfConvertCreateCsvJobFailed'),`r`n            showToast,`r`n            t,`r`n          });",
    1
)

$content = $content.Replace(
    "        showToast('error', conversionResult.message);",
    "        showPdfConvertFailedToast({ message: conversionResult.message || t('upload.toast.pdfConvertFailed'), showToast, t });"
)

$content = $content.Replace(
    "      showToast('info', t('upload.toast.pdfConvertStillProcessing'));",
    "      showPdfConvertStillProcessingToast({ showToast, t });"
)

$content = $content.Replace(
    "      showToast('error', e?.message || t('upload.toast.pdfConvertFailed'));",
    "      showPdfConvertFailedToast({ message: e?.message || t('upload.toast.pdfConvertFailed'), showToast, t });"
)

$legacyPdfConvertPollPattern = '(?s)      const trigger = await uploadApi\.triggerPdfConvert\(target\.processId\);.*?      showPdfConvertStillProcessingToast\(\{ showToast, t \}\);'
$legacyPdfConvertPollReplacement = @'
      const conversionResult = await runPdfConversion({
        processId: target.processId,
        triggerPdfConvert: uploadApi.triggerPdfConvert,
        fetchPdfConvertStatus: uploadApi.fetchPdfConvertStatus,
        sleep: delay,
        attachPdfConvertJob: (jobId) => attachPdfConvertJob(fileId, jobId),
        updatePdfConvertProgress: (status, progress, errorText) =>
          updatePdfConvertProgress(fileId, status, progress, errorText),
        toPdfConvertProgress,
        fallbackErrorText: t('upload.toast.pdfConvertFailed'),
      });

      if (conversionResult.outcome === 'completed') {
        try {
          showPdfConvertFetchingCsvToast({ processId: target.processId, showToast, t });
          const outputsResp = await uploadApi.fetchPdfConvertedCsvOutputs(target.processId);
          const outputs = Array.isArray(outputsResp) ? outputsResp : (outputsResp?.outputs || []);

          const newCsvFiles = await buildUploadedCsvFilesFromPdfOutputs(
            outputs,
            filesRef.current.map((file) => file.name)
          );

          if (newCsvFiles.length) {
            replacePdfWithCsvFiles(fileId, newCsvFiles);
            showPdfConvertGotCsvToast({ processId: target.processId, count: newCsvFiles.length, showToast, t });
          } else {
            showPdfConvertNoCsvToast({ processId: target.processId, showToast, t });
          }
        } catch (e: any) {
          showPdfConvertOutputErrorToast({
            processId: target.processId,
            message: e?.message || t('upload.toast.pdfConvertCreateCsvJobFailed'),
            showToast,
            t,
          });
        }
        return true;
      }

      if (conversionResult.outcome === 'failed') {
        failPdfConvert(fileId, conversionResult.message || t('upload.toast.pdfConvertFailed'));
        showPdfConvertFailedToast({ message: conversionResult.message || t('upload.toast.pdfConvertFailed'), showToast, t });
        return false;
      }

      showPdfConvertStillProcessingToast({ showToast, t });
'@
$content = [regex]::Replace($content, $legacyPdfConvertPollPattern, $legacyPdfConvertPollReplacement, 1)

$content = $content.Replace(
    'import { ProgressBar } from "../components/common/ProgressBar";' + "`r`n",
    ''
)

$duplicateEligibilityImport = 'import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from "./upload/uploadEligibility";' + "`r`n" + 'import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from "./upload/uploadEligibility";'
$content = $content.Replace(
    $duplicateEligibilityImport,
    'import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from "./upload/uploadEligibility";'
)
$content = [regex]::Replace(
    $content,
    '(?m)^(import \{ fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated \} from "\./upload/uploadEligibility";\r?\n)(?:\1)+',
    '$1'
)

if ($content -notmatch 'import \{ useUploadWorkflow \}') {
    $content = $content.Replace(
        'import { toImportProgress, toPdfConvertProgress, toValidateProgress } from "./upload/uploadProgress";',
        "import { toImportProgress, toPdfConvertProgress, toValidateProgress } from `"./upload/uploadProgress`";`r`nimport { useUploadWorkflow } from `"./upload/useUploadWorkflow`";"
    )
}

if ($content -notmatch 'import \{ createUploadApiClient \}') {
    $content = $content.Replace(
        'import { TENANT_STORAGE_KEY } from "../services/tenant";',
        "import { TENANT_STORAGE_KEY } from `"../services/tenant`";`r`nimport { createUploadApiClient } from `"./upload/uploadApiClient`";"
    )
}

if ($content -notmatch 'import \{ useUploadApi \}') {
    $content = $content.Replace(
        'import { createUploadApiClient } from "./upload/uploadApiClient";',
        'import { useUploadApi } from "./upload/useUploadApi";'
    )
}

if ($content -notmatch 'uploadAsyncUtils') {
    $content = $content.Replace(
        'import { useUploadApi } from "./upload/useUploadApi";',
        "import { useUploadApi } from `"./upload/useUploadApi`";`r`nimport { delay } from `"./upload/uploadAsyncUtils`";"
    )
}

$content = $content.Replace(
    'import { delay } from "./upload/uploadAsyncUtils";',
    'import { delay, scheduleAfterDelay } from "./upload/uploadAsyncUtils";'
)
$content = [regex]::Replace(
    $content,
    '(?m)^(import \{ delay, scheduleAfterDelay \} from "\./upload/uploadAsyncUtils";\r?\n)\1+',
    '$1'
)

if ($content -notmatch 'import \{ flattenImportValidationErrors \}') {
    $content = $content.Replace(
        'import { runCsvValidationJob, runPdfValidation } from "./upload/uploadValidationOrchestrator";',
        "import { runCsvValidationJob, runPdfValidation } from `"./upload/uploadValidationOrchestrator`";`r`nimport { flattenImportValidationErrors } from `"./upload/uploadValidationErrorUtils`";"
    )
}

if ($content -notmatch 'import \{ showValidationResultToast \}') {
    $content = $content.Replace(
        'import { flattenImportValidationErrors } from "./upload/uploadValidationErrorUtils";',
        "import { flattenImportValidationErrors } from `"./upload/uploadValidationErrorUtils`";`r`nimport { showValidationResultToast } from `"./upload/uploadValidationToastUtils`";"
    )
}

if ($content -notmatch 'uploadImportToastUtils') {
    $content = $content.Replace(
        'import { showValidationResultToast } from "./upload/uploadValidationToastUtils";',
        "import { showValidationResultToast } from `"./upload/uploadValidationToastUtils`";`r`nimport { showBatchImportCleanupToast, showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCleanupToast, showSingleImportCompletedToast, showSingleImportStartToast } from `"./upload/uploadImportToastUtils`";"
    )
}

if ($content -notmatch 'uploadPdfConvertToastUtils') {
    $content = $content.Replace(
        'import { runPdfConversion } from "./upload/uploadPdfConversionOrchestrator";',
        "import { runPdfConversion } from `"./upload/uploadPdfConversionOrchestrator`";`r`nimport { showMissingPdfConvertProcessToast, showPdfConvertFailedToast, showPdfConvertFetchingCsvToast, showPdfConvertGotCsvToast, showPdfConvertNoCsvToast, showPdfConvertOutputErrorToast, showPdfConvertStillProcessingToast } from `"./upload/uploadPdfConvertToastUtils`";"
    )
}

$pattern = '(?s)type FileType = "P1" \| "P2" \| "P3" \| "PDF";.*?async function parseCsv\(file: File\): Promise<CsvData> \{.*?\n\}\r?\n\r?\nexport function UploadPage\(\) \{'
if ($content -match $pattern) {
    $content = [regex]::Replace($content, $pattern, "export function UploadPage() {", 1)
}

$progressPattern = '(?s)\r?\n  const toValidateProgress = \(jobStatus: string\): number => \{.*?\n  \};\r?\n\r?\n  const toImportProgress = \(jobStatus: string\): number => \{.*?\n  \};\r?\n\r?\n  const toPdfConvertProgress = \(convertStatus: string\): number => \{.*?\n  \};\r?\n'
if ($content -match $progressPattern) {
    $content = [regex]::Replace($content, $progressPattern, "`r`n", 1)
}

if ($content -notmatch "const uploadApi =") {
    $content = $content.Replace(
        "  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));",
        "  const uploadApi = useMemo(() => createUploadApiClient({ t, getTenantHeaders: buildTenantHeaders }), [t]);`r`n`r`n  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));"
    )
}

$tenantApiSetupPattern = '(?s)\r?\n  const buildTenantHeaders = \(\): HeadersInit => \{\r?\n    const id = window\.localStorage\.getItem\(TENANT_STORAGE_KEY\) \|\| '''';\r?\n    return id \? \{ ''X-Tenant-Id'': id \} : \{\};\r?\n  \};\r?\n\r?\n  const uploadApi = useMemo\(\(\) => createUploadApiClient\(\{ t, getTenantHeaders: buildTenantHeaders \}\), \[t\]\);'
$content = [regex]::Replace($content, $tenantApiSetupPattern, "`r`n  const uploadApi = useUploadApi(t);", 1)

$content = $content.Replace(
    "  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));`r`n",
    ""
)

$content = $content.Replace(
    "        sleep,",
    "        sleep: delay,"
)

$content = $content.Replace(
    "        sleep,`r`n",
    "        sleep: delay,`r`n"
)

$content = $content.Replace(
    'import { TENANT_STORAGE_KEY } from "../services/tenant";' + "`r`n",
    ''
)

$content = $content.Replace(
    'import { createUploadApiClient } from "./upload/uploadApiClient";' + "`r`n",
    ''
)

$apiHelperPattern = '(?s)\r?\n  const fetchPdfConvertStatus = async \(processId: string\) => \{.*?\n  \};\r?\n\r?\n  const fetchPdfConvertedCsvOutputs = async \(processId: string\) => \{.*?\n  \};\r?\n\r?\n  const fetchImportJob = async \(jobId: string\) => \{.*?\n  \};\r?\n'
if ($content -match $apiHelperPattern) {
    $content = [regex]::Replace($content, $apiHelperPattern, "`r`n", 1)
}

$content = $content.Replace(
    'import { useState, useRef, useEffect, useMemo, useCallback } from "react";',
    'import { useState, useMemo, useCallback } from "react";'
)

$content = $content.Replace(
    'import { useState, useMemo, useCallback } from "react";',
    'import { useState, useCallback } from "react";'
)

$content = $content.Replace(
    "  const [files, setFiles] = useState<UploadedFile[]>([]);",
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();"
)

$filesRefPattern = '(?s)\r?\n  // .*?\r?\n  // .*?\r?\n  const filesRef = useRef\(files\);\r?\n  useEffect\(\(\) => \{\r?\n    filesRef\.current = files;\r?\n  \}, \[files\]\);\r?\n'
$content = [regex]::Replace($content, $filesRefPattern, "`r`n", 1)

$content = $content.Replace(
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded } = useUploadWorkflow();",
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();"
)

$content = $content.Replace(
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation } = useUploadWorkflow();",
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();"
)

$content = $content.Replace(
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation } = useUploadWorkflow();",
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();"
)

$content = $content.Replace(
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert } = useUploadWorkflow();",
    "  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();"
)

$beginPdfValidationPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId \? \{ \.\.\.f, status: ''validating'', validateProgress: 10 \} : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $beginPdfValidationPattern, "      beginPdfValidation(fileId);", 1)

$completePdfUploadPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  status: ''uploaded'',\r?\n                  validateProgress: 100,\r?\n                  processId: data\.process_id,\r?\n                  isValidated: true,\r?\n                  validationErrors: undefined,\r?\n                  hasUnsavedChanges: false,\r?\n                  expanded: false,\r?\n\r?\n                  pdfConvertStatus: ''not_started'',\r?\n                  pdfConvertJobId: undefined,\r?\n                  pdfConvertProgress: 0,\r?\n                  pdfConvertError: undefined,\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $completePdfUploadPattern, "        completePdfUpload(fileId, data.process_id);", 1)

$failPdfValidationPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) => \(f\.id === fileId \? \{ \.\.\.f, status: ''uploaded'', validateProgress: 0 \} : f\)\)\r?\n        \);'
$content = [regex]::Replace($content, $failPdfValidationPattern, "        failPdfValidation(fileId);", 1)

$beginCsvValidationPattern = '(?s)    setFiles\(\(prev\) =>\r?\n      prev\.map\(\(f\) =>\r?\n        f\.id === fileId\r?\n          \? \{ \.\.\.f, status: "validating", validateProgress: 10 \}\r?\n          : f\r?\n      \)\r?\n    \);'
$content = [regex]::Replace($content, $beginCsvValidationPattern, "    beginCsvValidation(fileId);", 1)

$convertEligibilityPattern = '(?s)\r?\n  const fileEligibleForConvert = \(f: UploadedFile\): boolean => \{\r?\n    if \(f\.type !== ''PDF''\) return false;\r?\n    if \(!f\.isValidated\) return false;\r?\n    if \(f\.pdfConvertStatus === ''queued'' \|\| f\.pdfConvertStatus === ''uploading'' \|\| f\.pdfConvertStatus === ''processing'' \|\| f\.pdfConvertStatus === ''completed''\) return false;\r?\n    return true;\r?\n  \};\r?\n'
$content = [regex]::Replace($content, $convertEligibilityPattern, "`r`n", 1)

$validationUploadSourcePattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId\r?\n            \? \{ \.\.\.f, file: fileToUpload, size: fileToUpload\.size \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $validationUploadSourcePattern, "      setValidationUploadSource(fileId, fileToUpload);", 1)

$content = $content.Replace(
    "      setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, validateProgress: 25 } : f)));",
    "      setValidationProgress(fileId, 25);"
)

$content = $content.Replace(
    "      setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, validateProgress: 40 } : f)));",
    "      setValidationProgress(fileId, 40);"
)

$content = $content.Replace(
    "      setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, validateProgress: 90 } : f)));",
    "      setValidationProgress(fileId, 90);"
)

$prepareCsvValidationJobPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId\r?\n            \? \{\r?\n                \.\.\.f,\r?\n                status: "validating",\r?\n                validateProgress: 50,\r?\n                csvData,\r?\n                expanded: true,\r?\n                // .*?\r?\n                processId: createdJob\.id,\r?\n                isValidated: false,\r?\n                validationErrors: undefined,\r?\n                hasUnsavedChanges: false,\r?\n              \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $prepareCsvValidationJobPattern, "      prepareCsvValidationJob(fileId, csvData, createdJob.id);", 1)

$validationPollPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  status: lastJob\.status === ''READY'' \|\| lastJob\.status === ''FAILED'' \? ''validated'' : ''validating'',\r?\n                  validateProgress: toValidateProgress\(lastJob\.status\),\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $validationPollPattern, "        updateValidationPoll(fileId, lastJob.status, toValidateProgress(lastJob.status));", 1)

$validationFailurePattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  status: ''validated'',\r?\n                  isValidated: true,\r?\n                  validationErrors: \[\{ row_index: 0, field: ''system'', error_code: ''FAILED'', message \}\],\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $validationFailurePattern, "        completeValidationFailure(fileId, message);", 1)

$validationErrorsPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  status: ''validated'',\r?\n                  validateProgress: 100,\r?\n                  isValidated: true,\r?\n                  validationErrors: flattenedErrors,\r?\n                  hasUnsavedChanges: false,\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $validationErrorsPattern, "        completeValidationWithErrors(fileId, flattenedErrors);", 1)

$validationPassedPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  status: ''validated'',\r?\n                  validateProgress: 100,\r?\n                  isValidated: true,\r?\n                  validationErrors: \[\],\r?\n                  hasUnsavedChanges: false,\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $validationPassedPattern, "        completeValidationPassed(fileId);", 1)

$failCsvValidationPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId \r?\n            \? \{ \.\.\.f, status: "uploaded", validateProgress: 0 \} \r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $failCsvValidationPattern, "      failCsvValidation(fileId);", 1)

$beginPdfConvertPattern = '(?s)    setFiles\(\(prev\) =>\r?\n      prev\.map\(\(f\) =>\r?\n        f\.id === fileId\r?\n          \? \{\r?\n              \.\.\.f,\r?\n              pdfConvertStatus: ''queued'',\r?\n              pdfConvertProgress: 10,\r?\n              pdfConvertError: undefined,\r?\n            \}\r?\n          : f\r?\n      \)\r?\n    \);'
$content = [regex]::Replace($content, $beginPdfConvertPattern, "    beginPdfConvert(fileId);", 1)

$attachPdfConvertJobPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId\r?\n            \? \{\r?\n                \.\.\.f,\r?\n                pdfConvertJobId: trigger\.job_id,\r?\n              \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $attachPdfConvertJobPattern, "      attachPdfConvertJob(fileId, trigger.job_id);", 1)

$pdfConvertProgressPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === fileId\r?\n              \? \{\r?\n                  \.\.\.f,\r?\n                  pdfConvertStatus:.*?pdfConvertError:\r?\n                    status === ''FAILED'' \? \(errorText \|\| t\(''upload\.toast\.pdfConvertFailed''\)\) : undefined,\r?\n                \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $pdfConvertProgressPattern, "        updatePdfConvertProgress(fileId, status, progress, errorText || t('upload.toast.pdfConvertFailed'));", 1)

$replacePdfWithCsvPattern = '(?s)              setFiles\(\(prev\) => \{\r?\n                const withoutPdf = prev\.filter\(\(f\) => f\.id !== fileId\);\r?\n                return \[\.\.\.withoutPdf, \.\.\.newCsvFiles\];\r?\n              \}\);'
$content = [regex]::Replace($content, $replacePdfWithCsvPattern, "              replacePdfWithCsvFiles(fileId, newCsvFiles);", 1)

$failPdfConvertPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === fileId\r?\n            \? \{\r?\n                \.\.\.f,\r?\n                pdfConvertStatus: ''failed'',\r?\n                pdfConvertProgress: 100,\r?\n                pdfConvertError: e\?\.message \|\| t\(''upload\.toast\.pdfConvertFailed''\),\r?\n              \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $failPdfConvertPattern, "      failPdfConvert(fileId, e?.message || t('upload.toast.pdfConvertFailed'));", 1)

$pdfOutputBuildPattern = '(?s)            const newCsvFiles: UploadedFile\[\] = \[\];\r?\n            for \(const u of outputs\) \{.*?            \}\r?\n\r?\n            if \(newCsvFiles\.length\) \{'
$pdfOutputBuildReplacement = @'
            const newCsvFiles = await buildUploadedCsvFilesFromPdfOutputs(
              outputs,
              filesRef.current.map((file) => file.name)
            );

            if (newCsvFiles.length) {
'@
$content = [regex]::Replace($content, $pdfOutputBuildPattern, $pdfOutputBuildReplacement, 1)

$beginBatchImportPattern = '(?s)    setFiles\(prev => \r?\n      prev\.map\(f => \r?\n        validatedFiles\.some\(vf => vf\.id === f\.id\)\r?\n          \? \{ \.\.\.f, status: "importing", importProgress: 10 \}\r?\n          : f\r?\n      \)\r?\n    \);'
$content = [regex]::Replace($content, $beginBatchImportPattern, "    beginImport(validatedFiles.map((file) => file.id), 10);", 1)

$batchFileProgressPattern = '(?s)        setFiles\(prev => \r?\n          prev\.map\(f => \r?\n            f\.id === file\.id \r?\n              \? \{ \.\.\.f, importProgress: progress \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $batchFileProgressPattern, "        setImportProgress(file.id, progress);", 1)

$batchPollProgressPattern = "setFiles\(prev => prev\.map\(f => f\.id === file\.id \? \{ \.\.\.f, importProgress: toImportProgress\(committedJob\.status\) \} : f\)\);"
$content = [regex]::Replace($content, $batchPollProgressPattern, "setImportProgress(file.id, toImportProgress(committedJob.status));", 1)

$batchCompletePattern = '(?s)        setFiles\(prev => \r?\n          prev\.map\(f => \r?\n            f\.id === file\.id \r?\n              \? \{ \.\.\.f, status: "imported", importProgress: 100 \}\r?\n              : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $batchCompletePattern, "        completeImport(file.id);", 1)

$batchCleanupPattern = '(?s)        const currentFiles = filesRef\.current;\r?\n        const remainingFiles = currentFiles\.filter\(f => \r?\n          !validatedFiles\.some\(vf => vf\.id === f\.id\)\r?\n        \);\r?\n\r?\n        // .*?\r?\n        setFiles\(remainingFiles\);'
$content = [regex]::Replace($content, $batchCleanupPattern, "        const remainingFiles = removeImportedFiles(validatedFiles.map((file) => file.id));", 1)

$batchResetPattern = '(?s)      setFiles\(prev => \r?\n        prev\.map\(f => \r?\n          validatedFiles\.some\(vf => vf\.id === f\.id\)\r?\n            \? \{ \.\.\.f, status: "validated", importProgress: 0 \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $batchResetPattern, "      resetImport(validatedFiles.map((file) => file.id));", 1)

$singleBeginImportPattern = '(?s)    setFiles\(\(prev\) =>\r?\n      prev\.map\(\(f\) =>\r?\n        f\.id === id\r?\n          \? \{ \.\.\.f, status: "importing", importProgress: 20 \}\r?\n          : f\r?\n      \)\r?\n    \);'
$content = [regex]::Replace($content, $singleBeginImportPattern, "    beginImport([id], 20);", 1)

$singleCommitProgressPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) =>\r?\n            f\.id === id \? \{ \.\.\.f, importProgress: 60 \} : f\r?\n          \)\r?\n        \);'
$content = [regex]::Replace($content, $singleCommitProgressPattern, "        setImportProgress(id, 60);", 1)

$singlePollProgressPattern = '(?s)        setFiles\(\(prev\) =>\r?\n          prev\.map\(\(f\) => \(f\.id === id \? \{ \.\.\.f, importProgress: toImportProgress\(committedJob\.status\) \} : f\)\)\r?\n        \);'
$content = [regex]::Replace($content, $singlePollProgressPattern, "        setImportProgress(id, toImportProgress(committedJob.status));", 1)

$singleCompletePattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === id\r?\n            \? \{ \.\.\.f, status: "imported", importProgress: 100 \}\r?\n            : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $singleCompletePattern, "      completeImport(id);", 1)

$content = $content.Replace(
    "        const remainingFiles = currentFiles.filter(f => f.id !== id);",
    "        const remainingFiles = removeImportedFiles([id]);"
)

$content = $content.Replace(
    "          setFiles([]);",
    "          removeImportedFiles([id]);"
)

$content = $content.Replace(
    "          setFiles(remainingFiles);",
    "          removeImportedFiles([id]);"
)

$content = $content.Replace(
    "          showToast('info', t('upload.toast.pageResetContinueUpload'));`r`n          removeImportedFiles([id]);",
    "          showToast('info', t('upload.toast.pageResetContinueUpload'));"
)

$content = $content.Replace(
    "          showToast('info', t('upload.batchImport.toast.remainingFiles', { count: remainingFiles.length }));`r`n          removeImportedFiles([id]);",
    "          showToast('info', t('upload.batchImport.toast.remainingFiles', { count: remainingFiles.length }));"
)

$singleResetPattern = '(?s)      setFiles\(\(prev\) =>\r?\n        prev\.map\(\(f\) =>\r?\n          f\.id === id \? \{ \.\.\.f, status: "validated", importProgress: 0 \} : f\r?\n        \)\r?\n      \);'
$content = [regex]::Replace($content, $singleResetPattern, "      resetImport([id]);", 1)

$validImportFilterPattern = '(?s)files\.filter\(f => \r?\n\s*f\.status === "validated" && \r?\n\s*f\.processId && \r?\n\s*!f\.hasUnsavedChanges &&\r?\n\s*\(!f\.validationErrors \|\| f\.validationErrors\.length === 0\)\r?\n\s*\)'
$content = [regex]::Replace($content, $validImportFilterPattern, "files.filter(fileEligibleForBatchImport)")

$validImportJobWithoutErrorPattern = '(?s)files\.filter\(f => \r?\n\s*f\.status === "validated" && \r?\n\s*f\.processId && \r?\n\s*\(!f\.validationErrors \|\| f\.validationErrors\.length === 0\)\r?\n\s*\)'
$content = [regex]::Replace($content, $validImportJobWithoutErrorPattern, "files.filter(fileEligibleForBatchImport)")

$filesWithErrorsPattern = '(?s)files\.filter\(f => \r?\n\s*f\.status === "validated" && \r?\n\s*f\.validationErrors && \r?\n\s*f\.validationErrors\.length > 0\r?\n\s*\)'
$content = [regex]::Replace($content, $filesWithErrorsPattern, "files.filter(fileHasBlockingImportErrors)")

$content = $content.Replace(
    'files.filter(f => f.status === "uploaded")',
    'files.filter(fileIsUploadedButUnvalidated)'
)

$content = $content.Replace(
    'files.filter(f => f.status === "validated" && f.processId)',
    'files.filter(fileHasImportJob)'
)

$content = $content.Replace(
    'validatedFiles.filter(f => !f.validationErrors || f.validationErrors.length === 0)',
    'validatedFiles.filter((file) => !fileHasValidationErrors(file))'
)

$content = $content.Replace(
    'validatedFiles.filter(f => f.validationErrors && f.validationErrors.length > 0)',
    'validatedFiles.filter(fileHasValidationErrors)'
)

$toggleExpandPattern = '(?s)  const handleToggleExpand = \(fileId: string\) => \{\r?\n    setFiles\(\(prev\) =>\r?\n      prev\.map\(\(f\) =>\r?\n        f\.id === fileId \? \{ \.\.\.f, expanded: !f\.expanded \} : f\r?\n      \)\r?\n    \);\r?\n  \};'
$content = [regex]::Replace($content, $toggleExpandPattern, "  const handleToggleExpand = toggleFileExpanded;")

$removeFilePattern = '(?s)  const handleRemoveFile = \(fileId: string\) => \{\r?\n    setFiles\(\(prev\) => prev\.filter\(\(f\) => f\.id !== fileId\)\);\r?\n  \};'
$content = [regex]::Replace($content, $removeFilePattern, "  const handleRemoveFile = removeFile;")

$content = [regex]::Replace($content, "(?<!uploadApi\.)fetchPdfConvertStatus\(", "uploadApi.fetchPdfConvertStatus(")
$content = [regex]::Replace($content, "(?<!uploadApi\.)fetchPdfConvertedCsvOutputs\(", "uploadApi.fetchPdfConvertedCsvOutputs(")
$content = [regex]::Replace($content, "(?<!uploadApi\.)fetchImportJob\(", "uploadApi.fetchImportJob(")

$pdfUploadPattern = "(?s)const formData = new FormData\(\);\s*formData\.append\('file', target\.file, target\.name\);.*?const data = await res\.json\(\);"
$content = [regex]::Replace($content, $pdfUploadPattern, "const data = await uploadApi.uploadPdf(target.file, target.name);")

$createImportJobPattern = "(?s)const createImportJob = async \(allowDuplicate: boolean\) => \{\s*const formData = new FormData\(\);\s*formData\.append\('table_code', target\.type\);\s*formData\.append\('allow_duplicate', allowDuplicate \? 'true' : 'false'\);\s*formData\.append\('files', fileToUpload, target\.name\);\s*return fetch\('/api/v2/import/jobs', \{\s*method: 'POST',\s*headers: buildTenantHeaders\(\),\s*body: formData,\s*\}\);\s*\};"
$createImportJobReplacement = @'
const createImportJob = async (allowDuplicate: boolean) => {
          return uploadApi.createImportJob({
            tableCode: target.type,
            allowDuplicate,
            file: fileToUpload,
            filename: target.name,
          });
        };
'@
$content = [regex]::Replace($content, $createImportJobPattern, $createImportJobReplacement)

$createImportJobResponsePattern = "(?s)let createJobResponse = await createImportJob\(false\);\s*if \(!createJobResponse\.ok\) \{.*?const createdJob = await createJobResponse\.json\(\);"
$createImportJobResponseReplacement = @'
let createdJob: any;
        try {
          createdJob = await createImportJob(false);
        } catch (error: any) {
          const detailObj = typeof error?.detail === 'object' && error.detail ? error.detail : null;
          const duplicateDetected = detailObj?.error_code === 'DUPLICATE_FILE_CONTENT';

          if (!duplicateDetected) {
            throw error;
          }

          const duplicateOf = detailObj?.duplicate_of?.uploaded_filename || 'Unknown file';
          const proceed = window.confirm(
            t('upload.confirm.duplicateFile').replace('{{filename}}', target.name).replace('{{duplicateOf}}', duplicateOf)
          );
          if (!proceed) {
            throw new Error('Duplicate import cancelled by user');
          }
          createdJob = await createImportJob(true);
        }
'@
$content = [regex]::Replace($content, $createImportJobResponsePattern, $createImportJobResponseReplacement)

$importErrorsPattern = '(?s)const errorsRes = await fetch\(`/api/v2/import/jobs/\$\{jobId\}/errors\?page=1&page_size=200`,.*?const errorRows = errorsRes\.ok \? await errorsRes\.json\(\) : \[\];'
$content = [regex]::Replace($content, $importErrorsPattern, "const errorRows = await uploadApi.fetchImportErrors(jobId);")

$triggerConvertPattern = '(?s)const res = await fetch\(`/api/upload/pdf/\$\{target\.processId\}/convert`,.*?const trigger = await res\.json\(\);'
$content = [regex]::Replace($content, $triggerConvertPattern, "const trigger = await uploadApi.triggerPdfConvert(target.processId);")

$commitFetchPattern = '(?s)const commitResponse = await fetch\(`/api/v2/import/jobs/\$\{jobId\}/commit`, \{\s*method: ''POST'',\s*headers: buildTenantHeaders\(\),\s*\}\);'
$commitFetchReplacement = "const commitResponse = { ok: true, json: async () => uploadApi.commitImportJob(jobId) } as any;"
$content = [regex]::Replace($content, $commitFetchPattern, $commitFetchReplacement)

while ($content.Contains("uploadApi.uploadApi.")) {
    $content = $content.Replace("uploadApi.uploadApi.", "uploadApi.")
}

# Fix handlePdfConvert to return boolean so batch conversion can track per-file success/failure
if ($content -notmatch "handlePdfConvert = async \(fileId: string\): Promise<boolean>") {
    $content = $content.Replace(
        "  const handlePdfConvert = async (fileId: string) => {",
        "  const handlePdfConvert = async (fileId: string): Promise<boolean> => {"
    )
    $content = [regex]::Replace($content,
        "    if \(!target\) return;\r?\n    if \(target\.type !== 'PDF'\) return;",
        "    if (!target) return false;`r`n    if (target.type !== 'PDF') return false;")
    $content = [regex]::Replace($content,
        "      showMissingPdfConvertProcessToast\(\{ showToast, t \}\);\r?\n      return;",
        "      showMissingPdfConvertProcessToast({ showToast, t });`r`n      return false;")
    # still-processing path: return false
    $content = [regex]::Replace($content,
        "      showPdfConvertStillProcessingToast\(\{ showToast, t \}\);\r?\n    \} catch \(e: any\) \{",
        "      showPdfConvertStillProcessingToast({ showToast, t });`r`n      return false;`r`n    } catch (e: any) {")
    # catch path: return false
    $content = [regex]::Replace($content,
        "      failPdfConvert\(fileId, e\?\.message \|\| t\('upload\.toast\.pdfConvertFailed'\)\);\r?\n      showPdfConvertFailedToast\(\{ message: e\?\.message \|\| t\('upload\.toast\.pdfConvertFailed'\), showToast, t \}\);\r?\n    \}\r?\n  \};",
        "      failPdfConvert(fileId, e?.message || t('upload.toast.pdfConvertFailed'));`r`n      showPdfConvertFailedToast({ message: e?.message || t('upload.toast.pdfConvertFailed'), showToast, t });`r`n      return false;`r`n    }`r`n  };")
}

# Phase 24: Extract post-import cleanup scheduling into helpers
$batchCleanupSchedulePattern = '(?s)      scheduleAfterDelay\(2000, \(\) => \{.*?showBatchImportCleanupToast\(\{.*?\}\);\r?\n      \}\);'
$batchCleanupScheduleReplacement = @'
      scheduleBatchPostImportCleanup({
        ids: validatedFiles.map((file) => file.id),
        removeImportedFiles,
        showToast,
        t,
      });
'@
$content = [regex]::Replace($content, $batchCleanupSchedulePattern, $batchCleanupScheduleReplacement, 1)

$singleCleanupSchedulePattern = '(?s)      scheduleAfterDelay\(2000, \(\) => \{.*?showSingleImportCleanupToast\(\{.*?\}\);\r?\n      \}\);'
$singleCleanupScheduleReplacement = @'
      scheduleSinglePostImportCleanup({
        id,
        filesRef,
        removeImportedFiles,
        showToast,
        t,
      });
'@
$content = [regex]::Replace($content, $singleCleanupSchedulePattern, $singleCleanupScheduleReplacement, 1)

$content = $content.Replace(
    'import { showBatchImportCleanupToast, showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCleanupToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";',
    'import { showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";'
)

if ($content -notmatch 'uploadImportCleanupUtils') {
    $content = $content.Replace(
        'import { showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";',
        "import { showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from `"./upload/uploadImportToastUtils`";`r`nimport { scheduleBatchPostImportCleanup, scheduleSinglePostImportCleanup } from `"./upload/uploadImportCleanupUtils`";"
    )
}

$content = $content.Replace(
    'import { delay, scheduleAfterDelay } from "./upload/uploadAsyncUtils";',
    'import { delay } from "./upload/uploadAsyncUtils";'
)

# Phase 26: Extract batch import workflow orchestration from UploadPage
$performBatchImportPattern = '(?s)  const performBatchImport = async \(\) => \{.*?\r?\n  \};\r?\n\r?\n(?=  const performImport = async \(\) => \{)'
$performBatchImportReplacement = @'
  const performBatchImport = async () => {
    setShowBatchImportConfirm(false);

    await runBatchImportWorkflow({
      files,
      commitImportJob: uploadApi.commitImportJob,
      fetchImportJob: uploadApi.fetchImportJob,
      sleep: delay,
      beginImport,
      setImportProgress,
      completeImport,
      resetImport,
      toImportProgress,
      schedulePostImportCleanup: (ids) =>
        scheduleBatchPostImportCleanup({
          ids,
          removeImportedFiles,
          showToast,
          t,
        }),
      logError: console.error,
      showToast,
      t,
    });
  };

'@
$content = [regex]::Replace($content, $performBatchImportPattern, $performBatchImportReplacement, 1)

$content = $content.Replace(
    'import { showBatchImportCompletedToast, showBatchImportSkipErrorsToast, showBatchImportStartToast, showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";',
    'import { showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";'
)

# Phase 25: Extract CSV validation result dispatch into commitCsvValidationResult
$csvValidationResultPattern = '(?s)      if \(lastJob\.status === ''FAILED''\) \{.*?return \{ outcome: ''failed'', message \};\r?\n      \}\r?\n\r?\n      const totalRows = Number\(lastJob\.total_rows \|\| 0\);\r?\n      const errorCount = Number\(lastJob\.error_count \|\| 0\);\r?\n.*?return \{ outcome: ''passed'', totalRows \};\r?\n      \}'
$csvValidationResultReplacement = @'
      return await commitCsvValidationResult({
        fileId,
        target,
        lastJob,
        fetchImportErrors: uploadApi.fetchImportErrors,
        completeValidationFailure,
        completeValidationWithErrors,
        completeValidationPassed,
        showValidationResultToast,
        showToast,
        t,
        silent: options?.silentToast,
      });
'@
$content = [regex]::Replace($content, $csvValidationResultPattern, $csvValidationResultReplacement, 1)

$content = $content.Replace(
    'import { runCsvValidationJob, runPdfValidation } from "./upload/uploadValidationOrchestrator";',
    'import { commitCsvValidationResult, runCsvValidationJob, runPdfValidation } from "./upload/uploadValidationOrchestrator";'
)

$content = $content.Replace(
    'import { flattenImportValidationErrors } from "./upload/uploadValidationErrorUtils";' + "`r`n",
    ''
)
$content = $content.Replace(
    'import { flattenImportValidationErrors } from "./upload/uploadValidationErrorUtils";' + "`n",
    ''
)

Set-Content -Encoding UTF8 $uploadPagePath $content

Write-Host "Applied UploadPage refactor to $GeneratedAppRoot"
