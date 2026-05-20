import type { UploadedFile } from "./uploadTypes";
import { fileEligibleForConvert, fileEligibleForValidate } from "./uploadEligibility";

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
