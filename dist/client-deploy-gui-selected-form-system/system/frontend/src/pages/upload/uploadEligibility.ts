import type { UploadedFile } from "./uploadTypes";

export function fileHasValidationErrors(file: UploadedFile): boolean {
  return Array.isArray(file.validationErrors) && file.validationErrors.length > 0;
}

export function fileEligibleForValidate(file: UploadedFile): boolean {
  if (file.status === "validating" || file.status === "importing") return false;
  if (file.type === "PDF") {
    return !file.isValidated;
  }
  if (file.status === "uploaded") return true;
  if (file.status === "validated" && fileHasValidationErrors(file)) return true;
  return false;
}

export function fileEligibleForConvert(file: UploadedFile): boolean {
  if (file.type !== "PDF") return false;
  if (!file.isValidated) return false;
  return (
    file.pdfConvertStatus !== "queued" &&
    file.pdfConvertStatus !== "uploading" &&
    file.pdfConvertStatus !== "processing" &&
    file.pdfConvertStatus !== "completed"
  );
}

export function fileEligibleForBatchImport(file: UploadedFile): boolean {
  return (
    file.status === "validated" &&
    Boolean(file.processId) &&
    !file.hasUnsavedChanges &&
    !fileHasValidationErrors(file)
  );
}

export function fileHasBlockingImportErrors(file: UploadedFile): boolean {
  return file.status === "validated" && fileHasValidationErrors(file);
}

export function fileIsUploadedButUnvalidated(file: UploadedFile): boolean {
  return file.status === "uploaded";
}

export function fileHasImportJob(file: UploadedFile): boolean {
  return file.status === "validated" && Boolean(file.processId);
}
