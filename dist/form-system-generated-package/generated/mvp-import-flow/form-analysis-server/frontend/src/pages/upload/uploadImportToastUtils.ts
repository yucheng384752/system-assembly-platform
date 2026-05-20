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
