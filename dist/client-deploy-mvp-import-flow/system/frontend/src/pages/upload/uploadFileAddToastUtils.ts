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
