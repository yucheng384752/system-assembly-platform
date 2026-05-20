import type { CsvData, UploadedFile } from "./uploadTypes";
import type { ValidateOutcome } from "./uploadBatchOrchestrator";
import { buildCsvText } from "./uploadCsvEditUtils";
import { flattenImportValidationErrors } from "./uploadValidationErrorUtils";

interface PdfValidationOptions {
  file: UploadedFile;
  uploadPdf: (file: File, filename: string) => Promise<{ process_id?: string }>;
  beginPdfValidation: (fileId: string) => void;
  completePdfUpload: (fileId: string, processId: string | undefined) => void;
  failPdfValidation: (fileId: string) => void;
  fallbackErrorText: string;
}

interface ImportJobStatus {
  id?: string;
  status?: string;
  total_rows?: number;
  error_count?: number;
  error_summary?: { error?: string };
}

interface CsvValidationOptions {
  file: UploadedFile;
  createImportJob: (input: {
    tableCode: string;
    allowDuplicate: boolean;
    file: File;
    filename: string;
  }) => Promise<ImportJobStatus>;
  parseCsv: (file: File) => Promise<CsvData>;
  confirmDuplicate: (duplicateOf: string) => boolean;
  sleep: (ms: number) => Promise<void>;
  beginCsvValidation: (fileId: string) => void;
  setValidationUploadSource: (fileId: string, file: File) => void;
  setValidationProgress: (fileId: string, progress: number) => void;
  prepareCsvValidationJob: (fileId: string, csvData: CsvData, jobId: string | undefined) => void;
  updateValidationPoll: (fileId: string, jobStatus: string, validateProgress: number) => void;
  fetchImportJob: (jobId: string) => Promise<ImportJobStatus>;
  toValidateProgress: (jobStatus: string) => number;
  validationTimeoutText: string;
}

export async function runPdfValidation({
  file,
  uploadPdf,
  beginPdfValidation,
  completePdfUpload,
  failPdfValidation,
  fallbackErrorText,
}: PdfValidationOptions): Promise<ValidateOutcome> {
  beginPdfValidation(file.id);

  try {
    const data = await uploadPdf(file.file, file.name);
    completePdfUpload(file.id, data.process_id);
    return { outcome: "passed", totalRows: 0 };
  } catch (error: any) {
    failPdfValidation(file.id);
    return { outcome: "failed", message: error?.message || fallbackErrorText };
  }
}

export async function runCsvValidationJob({
  file,
  createImportJob,
  parseCsv,
  confirmDuplicate,
  sleep,
  beginCsvValidation,
  setValidationUploadSource,
  setValidationProgress,
  prepareCsvValidationJob,
  updateValidationPoll,
  fetchImportJob,
  toValidateProgress,
  validationTimeoutText,
}: CsvValidationOptions): Promise<{ jobId: string; lastJob: ImportJobStatus }> {
  beginCsvValidation(file.id);

  const fileToUpload = file.csvData
    ? new File([buildCsvText(file.csvData)], file.name, { type: "text/csv" })
    : file.file;

  const createJob = (allowDuplicate: boolean) =>
    createImportJob({
      tableCode: file.type,
      allowDuplicate,
      file: fileToUpload,
      filename: file.name,
    });

  setValidationUploadSource(file.id, fileToUpload);
  setValidationProgress(file.id, 25);

  let createdJob: ImportJobStatus;
  try {
    createdJob = await createJob(false);
  } catch (error: any) {
    const detailObj = typeof error?.detail === "object" && error.detail ? error.detail : null;
    const duplicateDetected = detailObj?.error_code === "DUPLICATE_FILE_CONTENT";
    if (!duplicateDetected) throw error;

    const duplicateOf = detailObj?.duplicate_of?.uploaded_filename || "Unknown file";
    if (!confirmDuplicate(duplicateOf)) {
      throw new Error("Duplicate import cancelled by user");
    }
    createdJob = await createJob(true);
  }

  setValidationProgress(file.id, 40);

  const csvData = file.csvData ?? await parseCsv(fileToUpload);
  setValidationProgress(file.id, 90);
  prepareCsvValidationJob(file.id, csvData, createdJob.id);

  const jobId = createdJob.id as string;
  let lastJob = createdJob;
  for (let pollIndex = 0; pollIndex < 120; pollIndex++) {
    await sleep(1000);
    lastJob = await fetchImportJob(jobId);
    updateValidationPoll(file.id, String(lastJob.status || ""), toValidateProgress(String(lastJob.status || "")));
    if (lastJob.status === "READY" || lastJob.status === "FAILED") break;
  }

  if (!lastJob || (lastJob.status !== "READY" && lastJob.status !== "FAILED")) {
    throw new Error(validationTimeoutText);
  }

  return { jobId, lastJob };
}

interface CommitCsvValidationResultOptions {
  fileId: string;
  target: UploadedFile;
  lastJob: ImportJobStatus;
  fetchImportErrors: (jobId: string) => Promise<unknown[]>;
  completeValidationFailure: (fileId: string, message: string) => void;
  completeValidationWithErrors: (fileId: string, errors: any[]) => void;
  completeValidationPassed: (fileId: string) => void;
  showValidationResultToast: (opts: any) => void;
  showToast: any;
  t: any;
  silent?: boolean;
}

export async function commitCsvValidationResult({
  fileId,
  target,
  lastJob,
  fetchImportErrors,
  completeValidationFailure,
  completeValidationWithErrors,
  completeValidationPassed,
  showValidationResultToast,
  showToast,
  t,
  silent,
}: CommitCsvValidationResultOptions): Promise<ValidateOutcome> {
  const totalRows = Number(lastJob.total_rows || 0);
  const errorCount = Number(lastJob.error_count || 0);

  if (lastJob.status === "FAILED") {
    const message = lastJob.error_summary?.error || t("upload.errors.validateFailed");
    completeValidationFailure(fileId, message);
    showValidationResultToast({ kind: "csv-failed", silent, fileName: target.name, message, showToast, t });
    return { outcome: "failed", message };
  }

  if (errorCount > 0) {
    const errorRows = await fetchImportErrors(lastJob.id as string);
    const flattenedErrors = flattenImportValidationErrors(errorRows);
    completeValidationWithErrors(fileId, flattenedErrors);
    showValidationResultToast({ kind: "csv-errors", silent, fileName: target.name, totalRows, errorCount, showToast, t });
    return { outcome: "errors", totalRows, errorCount };
  }

  completeValidationPassed(fileId);
  showValidationResultToast({ kind: "csv-passed", silent, fileName: target.name, totalRows, showToast, t });
  return { outcome: "passed", totalRows };
}
