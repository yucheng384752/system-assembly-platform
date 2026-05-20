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
