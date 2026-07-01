import type { UploadedFile } from "./uploadTypes";
import { buildUploadedCsvFilesFromPdfOutputs } from "./uploadFileUtils";
import { showMissingPdfConvertProcessToast, showPdfConvertFailedToast, showPdfConvertFetchingCsvToast, showPdfConvertGotCsvToast, showPdfConvertNoCsvToast, showPdfConvertOutputErrorToast, showPdfConvertStillProcessingToast } from "./uploadPdfConvertToastUtils";

type ShowToast = (kind: "success" | "error" | "info" | "warning", message: string, options?: { key?: string; durationMs?: number | null }) => void;
type Translate = (key: string, options?: Record<string, unknown>) => string;

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

interface PdfConvertWorkflowOptions {
  fileId: string;
  filesRef: { current: UploadedFile[] };
  triggerPdfConvert: (processId: string) => Promise<{ job_id?: string }>;
  fetchPdfConvertStatus: (processId: string) => Promise<PdfConvertStatusResponse>;
  fetchPdfConvertedCsvOutputs: (processId: string) => Promise<any>;
  sleep: (ms: number) => Promise<void>;
  attachPdfConvertJob: (fileId: string, jobId: string | undefined) => void;
  updatePdfConvertProgress: (fileId: string, status: string, progress: number, errorText: string) => void;
  replacePdfWithCsvFiles: (fileId: string, newFiles: UploadedFile[]) => void;
  failPdfConvert: (fileId: string, errorText: string) => void;
  beginPdfConvert: (fileId: string) => void;
  toPdfConvertProgress: (convertStatus: string) => number;
  showToast: ShowToast;
  t: Translate;
}

export async function runPdfConvertWorkflow({
  fileId,
  filesRef,
  triggerPdfConvert,
  fetchPdfConvertStatus,
  fetchPdfConvertedCsvOutputs,
  sleep,
  attachPdfConvertJob,
  updatePdfConvertProgress,
  replacePdfWithCsvFiles,
  failPdfConvert,
  beginPdfConvert,
  toPdfConvertProgress,
  showToast,
  t,
}: PdfConvertWorkflowOptions): Promise<boolean> {
  const target = filesRef.current.find((file) => file.id === fileId);
  if (!target) return false;
  if (target.type !== "PDF") return false;
  const processId = target.processId;
  if (!processId) {
    showMissingPdfConvertProcessToast({ showToast, t });
    return false;
  }

  beginPdfConvert(fileId);

  try {
    const conversionResult = await runPdfConversion({
      processId,
      triggerPdfConvert,
      fetchPdfConvertStatus,
      sleep,
      attachPdfConvertJob: (jobId) => attachPdfConvertJob(fileId, jobId),
      updatePdfConvertProgress: (status, progress, errorText) =>
        updatePdfConvertProgress(fileId, status, progress, errorText),
      toPdfConvertProgress,
      fallbackErrorText: t("upload.toast.pdfConvertFailed"),
    });

    if (conversionResult.outcome === "completed") {
      try {
        showPdfConvertFetchingCsvToast({ processId, showToast, t });
        const outputsResp = await fetchPdfConvertedCsvOutputs(processId);
        const outputs = Array.isArray(outputsResp) ? outputsResp : (outputsResp?.outputs || []);

        const newCsvFiles = await buildUploadedCsvFilesFromPdfOutputs(
          outputs,
          filesRef.current.map((file) => file.name)
        );

        if (newCsvFiles.length) {
          replacePdfWithCsvFiles(fileId, newCsvFiles);
          showPdfConvertGotCsvToast({ processId, count: newCsvFiles.length, showToast, t });
        } else {
          showPdfConvertNoCsvToast({ processId, showToast, t });
        }
      } catch (e: any) {
        showPdfConvertOutputErrorToast({
          processId,
          message: e?.message || t("upload.toast.pdfConvertCreateCsvJobFailed"),
          showToast,
          t,
        });
      }
      return true;
    }

    if (conversionResult.outcome === "failed") {
      failPdfConvert(fileId, conversionResult.message || t("upload.toast.pdfConvertFailed"));
      showPdfConvertFailedToast({ message: conversionResult.message || t("upload.toast.pdfConvertFailed"), showToast, t });
      return false;
    }

    showPdfConvertStillProcessingToast({ showToast, t });
    return false;
  } catch (e: any) {
    failPdfConvert(fileId, e?.message || t("upload.toast.pdfConvertFailed"));
    showPdfConvertFailedToast({ message: e?.message || t("upload.toast.pdfConvertFailed"), showToast, t });
    return false;
  }
}
