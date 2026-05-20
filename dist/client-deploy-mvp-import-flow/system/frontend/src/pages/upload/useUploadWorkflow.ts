import { useCallback, useEffect, useRef, useState } from "react";
import type { CsvData, UploadedFile } from "./uploadTypes";

export function useUploadWorkflow() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const filesRef = useRef(files);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => prev.filter((file) => file.id !== fileId));
  }, []);

  const toggleFileExpanded = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, expanded: !file.expanded } : file
      )
    );
  }, []);

  const beginPdfValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "validating", validateProgress: 10 } : file
      )
    );
  }, []);

  const completePdfUpload = useCallback((fileId: string, processId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "uploaded",
              validateProgress: 100,
              processId,
              isValidated: true,
              validationErrors: undefined,
              hasUnsavedChanges: false,
              expanded: false,
              pdfConvertStatus: "not_started",
              pdfConvertJobId: undefined,
              pdfConvertProgress: 0,
              pdfConvertError: undefined,
            }
          : file
      )
    );
  }, []);

  const failPdfValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "uploaded", validateProgress: 0 } : file
      )
    );
  }, []);

  const beginCsvValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "validating", validateProgress: 10 } : file
      )
    );
  }, []);

  const setValidationUploadSource = useCallback((fileId: string, fileToUpload: File) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, file: fileToUpload, size: fileToUpload.size } : file
      )
    );
  }, []);

  const setValidationProgress = useCallback((fileId: string, validateProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, validateProgress } : file
      )
    );
  }, []);

  const prepareCsvValidationJob = useCallback((fileId: string, csvData: CsvData, jobId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validating",
              validateProgress: 50,
              csvData,
              expanded: true,
              processId: jobId,
              isValidated: false,
              validationErrors: undefined,
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const updateValidationPoll = useCallback((fileId: string, jobStatus: string, validateProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: jobStatus === "READY" || jobStatus === "FAILED" ? "validated" : "validating",
              validateProgress,
            }
          : file
      )
    );
  }, []);

  const completeValidationFailure = useCallback((fileId: string, message: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              isValidated: true,
              validationErrors: [{ row_index: 0, field: "system", error_code: "FAILED", message }],
            }
          : file
      )
    );
  }, []);

  const completeValidationWithErrors = useCallback((fileId: string, validationErrors: any[]) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              validateProgress: 100,
              isValidated: true,
              validationErrors,
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const completeValidationPassed = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              status: "validated",
              validateProgress: 100,
              isValidated: true,
              validationErrors: [],
              hasUnsavedChanges: false,
            }
          : file
      )
    );
  }, []);

  const failCsvValidation = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "uploaded", validateProgress: 0 } : file
      )
    );
  }, []);

  const beginPdfConvert = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus: "queued",
              pdfConvertProgress: 10,
              pdfConvertError: undefined,
            }
          : file
      )
    );
  }, []);

  const attachPdfConvertJob = useCallback((fileId: string, jobId: string | undefined) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, pdfConvertJobId: jobId } : file
      )
    );
  }, []);

  const updatePdfConvertProgress = useCallback((fileId: string, status: string, progress: number, fallbackError: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus:
                status === "COMPLETED"
                  ? "completed"
                  : status === "FAILED"
                  ? "failed"
                  : status === "UPLOADING"
                  ? "uploading"
                  : status === "PROCESSING"
                  ? "processing"
                  : status === "QUEUED"
                  ? "queued"
                  : "not_started",
              pdfConvertProgress: progress,
              pdfConvertError: status === "FAILED" ? fallbackError : undefined,
            }
          : file
      )
    );
  }, []);

  const replacePdfWithCsvFiles = useCallback((fileId: string, newCsvFiles: UploadedFile[]) => {
    setFiles((prev) => {
      const withoutPdf = prev.filter((file) => file.id !== fileId);
      return [...withoutPdf, ...newCsvFiles];
    });
  }, []);

  const failPdfConvert = useCallback((fileId: string, message: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId
          ? {
              ...file,
              pdfConvertStatus: "failed",
              pdfConvertProgress: 100,
              pdfConvertError: message,
            }
          : file
      )
    );
  }, []);

  const beginImport = useCallback((fileIds: string[], importProgress: number) => {
    const targetIds = new Set(fileIds);
    setFiles((prev) =>
      prev.map((file) =>
        targetIds.has(file.id)
          ? { ...file, status: "importing", importProgress }
          : file
      )
    );
  }, []);

  const setImportProgress = useCallback((fileId: string, importProgress: number) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, importProgress } : file
      )
    );
  }, []);

  const completeImport = useCallback((fileId: string) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === fileId ? { ...file, status: "imported", importProgress: 100 } : file
      )
    );
  }, []);

  const resetImport = useCallback((fileIds: string[]) => {
    const targetIds = new Set(fileIds);
    setFiles((prev) =>
      prev.map((file) =>
        targetIds.has(file.id)
          ? { ...file, status: "validated", importProgress: 0 }
          : file
      )
    );
  }, []);

  const removeImportedFiles = useCallback((fileIds: string[]) => {
    const targetIds = new Set(fileIds);
    const remainingFiles = filesRef.current.filter((file) => !targetIds.has(file.id));
    setFiles(remainingFiles);
    return remainingFiles;
  }, []);

  return {
    files,
    setFiles,
    filesRef,
    removeFile,
    toggleFileExpanded,
    beginPdfValidation,
    completePdfUpload,
    failPdfValidation,
    beginCsvValidation,
    setValidationUploadSource,
    setValidationProgress,
    prepareCsvValidationJob,
    updateValidationPoll,
    completeValidationFailure,
    completeValidationWithErrors,
    completeValidationPassed,
    failCsvValidation,
    beginPdfConvert,
    attachPdfConvertJob,
    updatePdfConvertProgress,
    replacePdfWithCsvFiles,
    failPdfConvert,
    beginImport,
    setImportProgress,
    completeImport,
    resetImport,
    removeImportedFiles,
  };
}
