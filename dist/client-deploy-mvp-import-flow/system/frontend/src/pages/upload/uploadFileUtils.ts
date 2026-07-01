import type { CsvData, FileType, UploadedFile } from "./uploadTypes";

export const MAX_SIZE_BYTES = 10 * 1024 * 1024;

export function detectFileType(name: string): FileType {
  if (name.toLowerCase().endsWith(".pdf")) return "PDF";
  if (name.startsWith("P1_")) return "P1";
  if (name.startsWith("P2_")) return "P2";
  return "P3";
}

export function deriveLotNoFromFilename(name: string): string {
  const base = name.replace(/\.csv$/i, "");
  const parts = base.split("_");
  const meaningful = parts.slice(1);
  if (meaningful.length === 0) return "";
  if (meaningful.length === 1) return normalizeLotNo(meaningful[0]);
  const head = normalize7Digits(meaningful[0]);
  const tailDigits = meaningful[1].replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

export function normalizeP3LotNo(value: string): string {
  const parts = value.split("_");
  if (parts.length < 2) return normalizeLotNo(value);
  const head = normalize7Digits(parts[0]);
  const tailDigits = parts[1].replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

function normalize7Digits(x: string): string {
  const digits = x.replace(/\D/g, "");
  return digits.padStart(7, "0").slice(-7);
}

export function normalizeLotNo(raw: string): string {
  const [a, b] = raw.split("_");
  const head = normalize7Digits(a ?? raw);
  if (!b) return head;
  const tailDigits = b.replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

export async function parseCsv(file: File): Promise<CsvData> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (!lines.length) {
    return { headers: [], rows: [], colWidths: [], starCells: new Set(), emptyCells: new Set() };
  }

  const rows = lines.map((line) => line.split(","));
  const headers = rows[0];
  const dataRows = rows.slice(1);
  const starCells = new Set<string>();
  const emptyCells = new Set<string>();

  for (let r = 0; r < dataRows.length; r++) {
    for (let c = 0; c < dataRows[r].length; c++) {
      const raw = dataRows[r][c];
      if (raw == null || raw.trim() === "") {
        emptyCells.add(`${r}_${c}`);
        continue;
      }

      let marked = false;
      let cleaned = raw;
      if (cleaned.includes("*")) {
        marked = true;
        cleaned = cleaned.replace(/\*/g, "");
      }
      if (cleaned !== cleaned.trim()) {
        marked = true;
      }
      if (marked) {
        starCells.add(`${r}_${c}`);
        dataRows[r][c] = cleaned;
      }
    }
  }

  const colWidths = new Array(headers.length).fill(0);
  const updateWidth = (col: number, value: string) => {
    colWidths[col] = Math.max(colWidths[col], value.length);
  };

  headers.forEach((header, index) => updateWidth(index, header));
  dataRows.forEach((row) => row.forEach((cell, index) => updateWidth(index, cell ?? "")));

  return {
    headers,
    rows: dataRows,
    colWidths: colWidths.map((length) => Math.max(80, Math.min(length * 10, 260))),
    starCells,
    emptyCells,
  };
}

export async function buildUploadedCsvFilesFromPdfOutputs(
  outputs: any[],
  existingNames: string[]
): Promise<UploadedFile[]> {
  const usedNames = new Set(existingNames);

  // Resolve unique names synchronously (order matters for deduplication)
  const intermediates = outputs.map((output) => {
    const filename = String(output.filename || "output.csv");
    const csvText = typeof output.csv_text === "string" ? output.csv_text : "";
    const safeName = usedNames.has(filename)
      ? `${filename.replace(/\.csv$/i, "")}__${Date.now().toString().slice(-6)}.csv`
      : filename;
    usedNames.add(safeName);
    const file = new File([csvText], safeName, { type: "text/csv" });
    const type = detectFileType(safeName);
    const lotNo = type === "P1" || type === "P2" ? deriveLotNoFromFilename(safeName) : "";
    return { safeName, file, type, lotNo };
  });

  // Parse all CSVs in parallel (each file is independent)
  const csvDatas = await Promise.all(intermediates.map(({ file }) => parseCsv(file)));

  return intermediates.map(({ safeName, file, type, lotNo }, i) => ({
    id: `${safeName}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    file,
    name: safeName,
    size: file.size,
    type,
    lotNo,
    status: "uploaded",
    jobBackend: "import_v2",
    uploadProgress: 100,
    validateProgress: 0,
    importProgress: 0,
    expanded: false,
    csvData: csvDatas[i],
    hasUnsavedChanges: false,
    processId: undefined,
    isValidated: false,
    validationErrors: undefined,
    pdfConvertStatus: undefined,
    pdfConvertJobId: undefined,
    pdfConvertProgress: undefined,
    pdfConvertError: undefined,
  }));
}
