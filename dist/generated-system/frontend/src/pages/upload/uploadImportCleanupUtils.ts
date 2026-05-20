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
