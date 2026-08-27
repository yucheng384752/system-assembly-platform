import { saveCsvChangesInFiles, updateCsvCellInFiles } from "./uploadCsvEditUtils";
import {
  showCsvChangesAppliedToast,
  showCsvEditDisabledToast,
  showCsvSaveErrorToast,
} from "./uploadCsvEditToastUtils";
import type { UploadedFile } from "./uploadTypes";

type ShowToast = (type: "success" | "error" | "info", message: string, options?: { key?: string; durationMs?: number | null }) => void;
type TranslationFn = (key: string, values?: Record<string, unknown>) => string;

interface SaveCsvChangesWorkflowOptions {
  editEnabled: boolean;
  files: UploadedFile[];
  fileId: string;
  setFiles: (files: UploadedFile[]) => void;
  showToast: ShowToast;
  t: TranslationFn;
}

interface UpdateCsvCellWorkflowOptions {
  editEnabled: boolean;
  fileId: string;
  rowIndex: number;
  colIndex: number;
  value: string;
  setFiles: (updater: (files: UploadedFile[]) => UploadedFile[]) => void;
}

export function runUpdateCsvCellWorkflow({
  editEnabled,
  fileId,
  rowIndex,
  colIndex,
  value,
  setFiles,
}: UpdateCsvCellWorkflowOptions): void {
  if (!editEnabled) return;
  setFiles((prev) => updateCsvCellInFiles(prev, fileId, rowIndex, colIndex, value));
}

export function runSaveCsvChangesWorkflow({
  editEnabled,
  files,
  fileId,
  setFiles,
  showToast,
  t,
}: SaveCsvChangesWorkflowOptions): void {
  if (!editEnabled) {
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
}
