import type { UploadedFile } from "./uploadTypes";
import { MAX_SIZE_BYTES, deriveLotNoFromFilename, detectFileType, detectTableCode } from "./uploadFileUtils";

export type AddUploadFileNotice =
  | { type: "unsupported"; fileName: string }
  | { type: "likely-duplicate-skipped"; fileName: string }
  | { type: "same-name"; fileName: string }
  | { type: "too-large"; fileName: string; maxSizeMb: string };

interface BuildUploadFilesToAddOptions {
  fileList: FileList | null;
  existingFiles: UploadedFile[];
  confirmLikelyDuplicate: (file: File) => boolean;
  availableCodes?: string[];
}

function isSupportedUploadFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".csv") || lowerName.endsWith(".pdf");
}

function isLikelyDuplicateFile(file: File, files: UploadedFile[]): boolean {
  return files.some(
    (existingFile) =>
      existingFile.name === file.name &&
      existingFile.size === file.size &&
      existingFile.file.lastModified === file.lastModified
  );
}

function buildUploadedFile(file: File, availableCodes: string[] = []): UploadedFile {
  const detected = availableCodes.length > 0
    ? detectTableCode(file.name, availableCodes)
    : detectFileType(file.name);
  const type = detected ?? "UNKNOWN";
  const lotNo = type === "PDF" || type === "UNKNOWN" ? "" : deriveLotNoFromFilename(file.name);
  const id = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  return {
    id,
    file,
    name: file.name,
    size: file.size,
    type,
    lotNo,
    status: "uploaded",
    jobBackend: type === "PDF" ? "pdf" : "import_v2",
    uploadProgress: 100,
    validateProgress: 0,
    importProgress: 0,
    expanded: type === "PDF" ? false : true,
    csvData: undefined,
    hasUnsavedChanges: false,
    processId: undefined,
    isValidated: false,
    validationErrors: undefined,
    pdfConvertStatus: type === "PDF" ? "not_started" : undefined,
    pdfConvertJobId: undefined,
    pdfConvertProgress: type === "PDF" ? 0 : undefined,
    pdfConvertError: undefined,
  };
}

export function buildUploadFilesToAdd({
  fileList,
  existingFiles,
  confirmLikelyDuplicate,
  availableCodes = [],
}: BuildUploadFilesToAddOptions): { files: UploadedFile[]; notices: AddUploadFileNotice[] } {
  if (!fileList) return { files: [], notices: [] };

  const files: UploadedFile[] = [];
  const notices: AddUploadFileNotice[] = [];

  Array.from(fileList).forEach((file) => {
    if (!isSupportedUploadFile(file)) {
      notices.push({ type: "unsupported", fileName: file.name });
      return;
    }

    const comparisonFiles = [...existingFiles, ...files];
    if (isLikelyDuplicateFile(file, comparisonFiles)) {
      const proceed = confirmLikelyDuplicate(file);
      if (!proceed) {
        notices.push({ type: "likely-duplicate-skipped", fileName: file.name });
        return;
      }
    } else if (comparisonFiles.some((existingFile) => existingFile.name === file.name)) {
      notices.push({ type: "same-name", fileName: file.name });
    }

    if (file.size > MAX_SIZE_BYTES) {
      notices.push({
        type: "too-large",
        fileName: file.name,
        maxSizeMb: (MAX_SIZE_BYTES / 1024 / 1024).toFixed(0),
      });
      return;
    }

    files.push(buildUploadedFile(file, availableCodes));
  });

  return { files, notices };
}
