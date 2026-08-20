import type { UploadedFile } from "./uploadTypes";
import { buildUploadFilesToAdd } from "./uploadFileAddUtils";
import { showFileAddResultToasts } from "./uploadFileAddToastUtils";

type ToastType = "success" | "error" | "info";
type ShowToast = (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface AddUploadFilesWorkflowOptions {
  fileList: FileList | null;
  existingFiles: UploadedFile[];
  setFiles: (updater: (files: UploadedFile[]) => UploadedFile[]) => void;
  confirmLikelyDuplicate: (file: File) => boolean;
  showToast: ShowToast;
  t: TranslationFn;
}

export function runAddUploadFilesWorkflow({
  fileList,
  existingFiles,
  setFiles,
  confirmLikelyDuplicate,
  showToast,
  t,
}: AddUploadFilesWorkflowOptions): void {
  const result = buildUploadFilesToAdd({
    fileList,
    existingFiles,
    confirmLikelyDuplicate,
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
}
