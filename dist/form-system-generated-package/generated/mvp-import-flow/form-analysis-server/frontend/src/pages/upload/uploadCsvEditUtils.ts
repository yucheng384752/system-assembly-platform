import type { CsvData, UploadedFile } from "./uploadTypes";

export function buildCsvText(csv: CsvData): string {
  const escapeCell = (cell: string) => {
    const value = cell ?? "";
    if (/[\r\n,"]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };

  const lines: string[] = [];
  lines.push(csv.headers.map((cell) => escapeCell(cell ?? "")).join(","));
  csv.rows.forEach((row) => {
    lines.push(row.map((cell) => escapeCell(cell ?? "")).join(","));
  });
  return lines.join("\n");
}

export function updateCsvCellInFiles(
  files: UploadedFile[],
  fileId: string,
  rowIndex: number,
  colIndex: number,
  value: string
): UploadedFile[] {
  return files.map((file) => {
    if (file.id !== fileId || !file.csvData) return file;

    const rows = file.csvData.rows.map((row, currentRowIndex) =>
      currentRowIndex === rowIndex
        ? row.map((cell, currentColIndex) => (currentColIndex === colIndex ? value : cell))
        : row
    );

    const shouldResetV2Job = file.jobBackend === "import_v2";
    return {
      ...file,
      csvData: { ...file.csvData, rows },
      hasUnsavedChanges: true,
      status: "uploaded",
      validateProgress: 0,
      importProgress: 0,
      isValidated: false,
      validationErrors: undefined,
      processId: shouldResetV2Job ? undefined : file.processId,
    };
  });
}

export type SaveCsvChangesResult =
  | { outcome: "saved"; files: UploadedFile[] }
  | { outcome: "not-found-or-clean" }
  | { outcome: "unsupported-backend" };

export function saveCsvChangesInFiles(
  files: UploadedFile[],
  fileId: string
): SaveCsvChangesResult {
  const target = files.find((file) => file.id === fileId);
  if (!target || !target.csvData || !target.hasUnsavedChanges) {
    return { outcome: "not-found-or-clean" };
  }

  if (target.jobBackend !== "import_v2") {
    return { outcome: "unsupported-backend" };
  }

  const csvText = buildCsvText(target.csvData);
  const updatedFile = new File([csvText], target.name, { type: "text/csv" });

  return {
    outcome: "saved",
    files: files.map((file) =>
      file.id === fileId
        ? {
            ...file,
            file: updatedFile,
            size: updatedFile.size,
            hasUnsavedChanges: false,
            status: "uploaded",
            validateProgress: 0,
            importProgress: 0,
            processId: undefined,
            isValidated: false,
            validationErrors: undefined,
          }
        : file
    ),
  };
}
