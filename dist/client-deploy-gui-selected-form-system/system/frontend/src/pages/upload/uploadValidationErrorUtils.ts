type ImportValidationError = {
  row_index: number;
  field: string;
  error_code: string;
  message: string;
};

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

export function flattenImportValidationErrors(errorRows: unknown): ImportValidationError[] {
  if (!Array.isArray(errorRows)) return [];

  return errorRows.flatMap((rawRow) => {
    const row = asRecord(rawRow);
    const rowIndex0 = Math.max(0, Number(row.row_index || 1) - 1);
    const errors = Array.isArray(row.errors) ? row.errors : [];

    if (errors.length === 0) {
      return [{
        row_index: rowIndex0,
        field: "row",
        error_code: "INVALID",
        message: "Row is invalid",
      }];
    }

    return errors.map((rawError) => {
      const error = asRecord(rawError);
      return {
        row_index: rowIndex0,
        field: String(error.field ?? error.column ?? "row"),
        error_code: String(error.error_code ?? "INVALID"),
        message: String(error.message ?? JSON.stringify(error)),
      };
    });
  });
}
