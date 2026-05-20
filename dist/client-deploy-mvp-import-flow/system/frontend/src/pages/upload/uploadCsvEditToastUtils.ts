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
