export type FileType = "P1" | "P2" | "P3" | "PDF";

export interface CsvData {
  headers: string[];
  rows: string[][];
  colWidths: number[];
  starCells: Set<string>;
  emptyCells: Set<string>;
}

export interface UploadedFile {
  id: string;
  file: File;
  name: string;
  size: number;
  type: FileType;
  lotNo: string;
  status: "uploaded" | "validating" | "validated" | "importing" | "imported";
  jobBackend: "import_v2" | "pdf";
  uploadProgress: number;
  validateProgress: number;
  importProgress: number;
  csvData: CsvData | undefined;
  expanded: boolean;
  hasUnsavedChanges: boolean;
  processId: string | undefined;
  isValidated: boolean;
  validationErrors: any[] | undefined;
  pdfConvertStatus: "not_started" | "queued" | "uploading" | "processing" | "completed" | "failed" | undefined;
  pdfConvertJobId: string | undefined;
  pdfConvertProgress: number | undefined;
  pdfConvertError: string | undefined;
}
