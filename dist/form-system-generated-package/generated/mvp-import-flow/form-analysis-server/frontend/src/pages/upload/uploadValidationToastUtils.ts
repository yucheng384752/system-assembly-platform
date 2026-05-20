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
