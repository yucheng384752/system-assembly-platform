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
