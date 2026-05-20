// src/pages/UploadPage.tsx
import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/common/ToastContext";
import { ProgressBar } from "../components/common/ProgressBar";
import { Modal } from "../components/common/Modal";
import { TENANT_STORAGE_KEY } from "../services/tenant";
import "./../styles/upload-page.css";

const EDIT_ENABLED =
  String((import.meta as any).env?.VITE_ENABLE_CSV_EDIT ?? "true").toLowerCase() === "true";

type FileType = "P1" | "P2" | "P3" | "PDF";

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
  processId: string | undefined;  // 後端返回的 process_id
  isValidated: boolean; // 是否已驗證過
  validationErrors: any[] | undefined; // 驗證錯誤

  // PDF 轉檔狀態（PDF 專用）
  pdfConvertStatus: "not_started" | "queued" | "uploading" | "processing" | "completed" | "failed" | undefined;
  pdfConvertJobId: string | undefined;
  pdfConvertProgress: number | undefined;
  pdfConvertError: string | undefined;
}

const MAX_SIZE_BYTES = 10 * 1024 * 1024;

function detectFileType(name: string): FileType {
  if (name.toLowerCase().endsWith(".pdf")) return "PDF";
  if (name.startsWith("P1_")) return "P1";
  if (name.startsWith("P2_")) return "P2";
  return "P3";
}

// P1 / P2: 由檔名取 lot_no，例如 P1_2503033_02.csv -> 2503033_02
function deriveLotNoFromFilename(name: string): string {
  const base = name.replace(/\.csv$/i, "");
  const parts = base.split("_");
  // 移除 P1 / P2 / P3 前綴
  const meaningful = parts.slice(1); // [2503033, 02] or [2503033, 2]
  if (meaningful.length === 0) return "";
  if (meaningful.length === 1) return normalizeLotNo(meaningful[0]);
  const head = normalize7Digits(meaningful[0]);
  const tailDigits = meaningful[1].replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

// P3: 由 P3_No. 欄位取 lot_no：2411012_03_05_301 -> 2411012_03
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
  // 用於一般情況：把"2503033_3" -> 2503033_03
  const [a, b] = raw.split("_");
  const head = normalize7Digits(a ?? raw);
  if (!b) return head;
  const tailDigits = b.replace(/\D/g, "");
  const tail = tailDigits.padStart(2, "0").slice(-2);
  return `${head}_${tail}`;
}

// 簡單 CSV parser（未處理引號逗號，之後可換成 PapaParse）
async function parseCsv(file: File): Promise<CsvData> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (!lines.length) {
    return { headers: [], rows: [], colWidths: [], starCells: new Set(), emptyCells: new Set() };
  }
  const rows = lines.map((line) => line.split(","));
  const headers = rows[0];
  const dataRows = rows.slice(1);

  // 偵測帶 * 或前後空格的儲存格，標記為顯著值
  const starCells = new Set<string>();
  // 偵測空白儲存格
  const emptyCells = new Set<string>();
  for (let r = 0; r < dataRows.length; r++) {
    for (let c = 0; c < dataRows[r].length; c++) {
      const raw = dataRows[r][c];
      if (raw == null || raw.trim() === '') {
        emptyCells.add(`${r}_${c}`);
        continue;
      }
      let marked = false;
      let cleaned = raw;
      // 偵測 *
      if (cleaned.includes('*')) {
        marked = true;
        cleaned = cleaned.replace(/\*/g, '');
      }
      // 偵測前後空格（不含中間正常空格）
      if (cleaned !== cleaned.trim()) {
        marked = true;
      }
      if (marked) {
        starCells.add(`${r}_${c}`);
        dataRows[r][c] = cleaned;
      }
    }
  }

  const colCount = headers.length;
  const colWidths = new Array(colCount).fill(0);

  const updateWidth = (col: number, value: string) => {
    const length = value.length;
    colWidths[col] = Math.max(colWidths[col], length);
  };

  headers.forEach((h, i) => updateWidth(i, h));
  dataRows.forEach((row) =>
    row.forEach((cell, i) => updateWidth(i, cell ?? ""))
  );

  const pixelWidths = colWidths.map((len) =>
    Math.max(80, Math.min(len * 10, 260))
  );

  return { headers, rows: dataRows, colWidths: pixelWidths, starCells, emptyCells };
}

export function UploadPage() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [confirmTargetId, setConfirmTargetId] = useState<string | null>(null);
  const [showBatchImportConfirm, setShowBatchImportConfirm] = useState(false);
  const [isValidatingAll, setIsValidatingAll] = useState(false);
  const [isConvertingAll, setIsConvertingAll] = useState(false);
  const { t } = useTranslation();
  const { showToast } = useToast();

  // 使用 ref 追蹤最新的 files 狀態，以解決在非同步操作（如 setTimeout）中存取過時狀態的問題
  // 同時避免在 setFiles 的 updater function 中執行副作用（如 showToast）
  const filesRef = useRef(files);
  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const buildTenantHeaders = (): HeadersInit => {
    const id = window.localStorage.getItem(TENANT_STORAGE_KEY) || '';
    return id ? { 'X-Tenant-Id': id } : {};
  };

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const fileHasValidationErrors = (f: UploadedFile): boolean => {
    return Array.isArray(f.validationErrors) && f.validationErrors.length > 0;
  };

  const fileEligibleForValidate = (f: UploadedFile): boolean => {
    if (f.status === 'validating' || f.status === 'importing') return false;
    if (f.type === 'PDF') {
      // PDF：驗證=上傳一次即可；已驗證過就不重複上傳
      return !f.isValidated;
    }
    // CSV：未驗證過或有錯誤可重驗
    if (f.status === 'uploaded') return true;
    if (f.status === 'validated' && fileHasValidationErrors(f)) return true;
    return false;
  };

  const toValidateProgress = (jobStatus: string): number => {
    switch (jobStatus) {
      case 'UPLOADED':
        return 25;
      case 'PARSING':
        return 45;
      case 'VALIDATING':
        return 75;
      case 'READY':
        return 100;
      case 'FAILED':
        return 100;
      default:
        return 30;
    }
  };

  const toImportProgress = (jobStatus: string): number => {
    switch (jobStatus) {
      case 'COMMITTING':
        return 60;
      case 'COMPLETED':
        return 100;
      case 'FAILED':
        return 100;
      default:
        return 30;
    }
  };

  const toPdfConvertProgress = (convertStatus: string): number => {
    switch (convertStatus) {
      case 'NOT_STARTED':
        return 0;
      case 'QUEUED':
        return 10;
      case 'UPLOADING':
        return 25;
      case 'PROCESSING':
        return 65;
      case 'COMPLETED':
        return 100;
      case 'FAILED':
        return 100;
      default:
        return 30;
    }
  };

  const fetchPdfConvertStatus = async (processId: string) => {
    const res = await fetch(`/api/upload/pdf/${processId}/convert/status`, {
      headers: buildTenantHeaders(),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: t('upload.errors.fetchPdfConvertStatusFailed') }));
      const message =
        typeof errorData.detail === 'string'
          ? errorData.detail
          : (errorData.detail?.detail || t('upload.errors.fetchPdfConvertStatusFailed'));
      throw new Error(message);
    }
    return res.json();
  };

  const fetchPdfConvertedCsvOutputs = async (processId: string) => {
    const res = await fetch(`/api/upload/pdf/${processId}/convert/outputs?include_csv_text=1`, {
      headers: buildTenantHeaders(),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: t('upload.errors.fetchCsvOutputsFailed') }));
      const message =
        typeof errorData.detail === 'string'
          ? errorData.detail
          : (errorData.detail?.detail || t('upload.errors.fetchCsvOutputsFailed'));
      throw new Error(message);
    }
    return res.json();
  };

  const fetchImportJob = async (jobId: string) => {
    const res = await fetch(`/api/v2/import/jobs/${jobId}`, {
      headers: buildTenantHeaders(),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: t('upload.errors.fetchImportStatusFailed') }));
      const message =
        typeof errorData.detail === 'string'
          ? errorData.detail
          : (errorData.detail?.detail || t('upload.errors.fetchImportStatusFailed'));
      throw new Error(message);
    }
    return res.json();
  };

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;

    const newFiles: UploadedFile[] = [];
    Array.from(fileList).forEach((file) => {
      const lowerName = file.name.toLowerCase();
      if (!lowerName.endsWith(".csv") && !lowerName.endsWith(".pdf")) {
        showToast('error', t('upload.toast.onlyCsvOrPdf'));
        return;
      }
      
      // 本機快篩：疑似重複（同檔名+同大小+同最後修改時間）
      const isLikelyDuplicate = [...files, ...newFiles].some(
        (f) =>
          f.name === file.name &&
          f.size === file.size &&
          f.file.lastModified === file.lastModified
      );
      if (isLikelyDuplicate) {
        const proceed = window.confirm(
          `偵測到疑似重複檔案：${file.name}\n是否仍要加入上傳清單？`
        );
        if (!proceed) {
          showToast('info', `已略過疑似重複檔案：${file.name}`);
          return;
        }
      } else if (files.some((f) => f.name === file.name) || newFiles.some((f) => f.name === file.name)) {
        // 同名但內容可能不同，提醒後仍允許加入
        showToast('info', t('upload.toast.fileAlreadyExists', { fileName: file.name }));
      }

      if (file.size > MAX_SIZE_BYTES) {
        showToast('error', t('upload.toast.fileTooLarge', { maxSizeMb: (MAX_SIZE_BYTES / 1024 / 1024).toFixed(0) }));
        return;
      }
      const type = detectFileType(file.name);
      const lotNo =
        type === "P1" || type === "P2" ? deriveLotNoFromFilename(file.name) : "";

      const id = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      newFiles.push({
        id,
        file,
        name: file.name,
        size: file.size,
        type,
        lotNo,
        status: "uploaded",
        jobBackend: type === "PDF" ? "pdf" : "import_v2",
        uploadProgress: 100, // 本地成功就視為100%
        validateProgress: 0,
        importProgress: 0,
        expanded: type === "PDF" ? false : true, // PDF 不展開（沒有 CSV 內容）
        csvData: undefined,
        hasUnsavedChanges: false,
        processId: undefined,
        isValidated: false,
        validationErrors: undefined,

        pdfConvertStatus: type === "PDF" ? "not_started" : undefined,
        pdfConvertJobId: undefined,
        pdfConvertProgress: type === "PDF" ? 0 : undefined,
        pdfConvertError: undefined,
      });
    });

    if (newFiles.length) {
      setFiles((prev) => [...prev, ...newFiles]);
      showToast('success', t('upload.toast.filesAdded', { count: newFiles.length }));
    }
  };

  const buildCsvText = (csv: CsvData): string => {
    const escapeCell = (cell: string) => {
      const value = cell ?? "";
      if (/[\r\n,"]/.test(value)) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };

    const lines: string[] = [];
    lines.push(csv.headers.map((c) => escapeCell(c ?? "")).join(","));
    csv.rows.forEach((row) => {
      lines.push(row.map((c) => escapeCell(c ?? "")).join(","));
    });
    return lines.join("\n");
  };

  type ValidateOutcome =
    | { outcome: 'passed'; totalRows: number }
    | { outcome: 'errors'; totalRows: number; errorCount: number }
    | { outcome: 'failed'; message: string };

  const handleValidate = async (fileId: string, options?: { silentToast?: boolean }): Promise<ValidateOutcome> => {
    const target = filesRef.current.find((f) => f.id === fileId);
    if (!target) return { outcome: 'failed', message: t('upload.errors.fileNotFound') };

    if (target.type === 'PDF') {
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId ? { ...f, status: 'validating', validateProgress: 10 } : f
        )
      );

      try {
        const formData = new FormData();
        formData.append('file', target.file, target.name);

        const res = await fetch('/api/upload/pdf', {
          method: 'POST',
          headers: buildTenantHeaders(),
          body: formData,
        });

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({ detail: t('upload.errors.pdfUploadFailed') }));
          const message = typeof errorData.detail === 'string' ? errorData.detail : (errorData.detail?.detail || t('upload.errors.pdfUploadFailed'));
          throw new Error(message);
        }

        const data = await res.json();
        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'uploaded',
                  validateProgress: 100,
                  processId: data.process_id,
                  isValidated: true,
                  validationErrors: undefined,
                  hasUnsavedChanges: false,
                  expanded: false,

                  pdfConvertStatus: 'not_started',
                  pdfConvertJobId: undefined,
                  pdfConvertProgress: 0,
                  pdfConvertError: undefined,
                }
              : f
          )
        );

        if (!options?.silentToast) showToast('success', t('upload.toast.pdfUploadedReadyToConvert'));
        return { outcome: 'passed', totalRows: 0 };
      } catch (e: any) {
        setFiles((prev) =>
          prev.map((f) => (f.id === fileId ? { ...f, status: 'uploaded', validateProgress: 0 } : f))
        );
        const msg = e?.message || t('upload.errors.pdfUploadFailed');
        if (!options?.silentToast) showToast('error', msg);
        return { outcome: 'failed', message: msg };
      }
    }

    if (!EDIT_ENABLED && target.hasUnsavedChanges) {
      if (!options?.silentToast) showToast("info", t('upload.editDisabledNotice'));
      return { outcome: 'failed', message: t('upload.editDisabledNotice') };
    }
    
    // 允許重複驗證，特別是有錯誤的檔案
    // 不再阻止重複驗證，讓用戶可以修改後重新驗證

    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId
          ? { ...f, status: "validating", validateProgress: 10 }
          : f
      )
    );

    try {
      // v2：建立 import job，後端背景進行 parse + validate
      // 注意：若使用者已編輯 CSV（csvData），必須用目前畫面內容重建檔案上傳，否則會一直驗證舊檔。
      const fileToUpload = target.csvData
        ? new File([buildCsvText(target.csvData)], target.name, { type: 'text/csv' })
        : target.file;

      const createImportJob = async (allowDuplicate: boolean) => {
        const formData = new FormData();
        formData.append('table_code', target.type);
        formData.append('allow_duplicate', allowDuplicate ? 'true' : 'false');
        formData.append('files', fileToUpload, target.name);
        return fetch('/api/v2/import/jobs', {
          method: 'POST',
          headers: buildTenantHeaders(),
          body: formData,
        });
      };

      // 讓後續流程（解析/重驗證）以最新內容為準
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? { ...f, file: fileToUpload, size: fileToUpload.size }
            : f
        )
      );

      setFiles((prev) => prev.map((f) => (f.id === fileId ? { ...f, validateProgress: 25 } : f)));

      let createJobResponse = await createImportJob(false);

      if (!createJobResponse.ok) {
        const errorData = await createJobResponse
          .json()
          .catch(() => ({ detail: t('upload.errors.uploadFailed') }));
        const detailObj =
          typeof errorData?.detail === 'object' && errorData?.detail
            ? errorData.detail
            : null;
        const duplicateDetected =
          detailObj?.error_code === 'DUPLICATE_FILE_CONTENT';

        if (duplicateDetected) {
          const duplicateOf = detailObj?.duplicate_of?.uploaded_filename || '未知檔案';
          const proceed = window.confirm(
            `此檔案內容與既有資料重複（${duplicateOf}）。\n是否仍要建立新匯入工作並覆蓋匯入？`
          );
          if (!proceed) {
            throw new Error('使用者取消重複檔案匯入');
          }
          createJobResponse = await createImportJob(true);
        }
      }

      if (!createJobResponse.ok) {
        const errorData = await createJobResponse
          .json()
          .catch(() => ({ detail: t('upload.errors.uploadFailed') }));
        const message =
          typeof errorData.detail === 'string'
            ? errorData.detail
            : (errorData.detail?.detail || t('upload.errors.uploadFailed'));
        throw new Error(message);
      }

      const createdJob = await createJobResponse.json();
      
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId ? { ...f, validateProgress: 40 } : f
        )
      );

      // 2. 解析CSV內容以供編輯（若本來就有 csvData，代表使用者已在畫面編輯過，直接沿用）
      const csvData = target.csvData ?? await parseCsv(fileToUpload);

      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId ? { ...f, validateProgress: 90 } : f
        )
      );

      // 3. 更新檔案狀態
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? {
                ...f,
                status: "validating",
                validateProgress: 50,
                csvData,
                expanded: true,
                // 沿用原欄位：把 v2 job_id 存到 processId（避免大改）
                processId: createdJob.id,
                isValidated: false,
                validationErrors: undefined,
                hasUnsavedChanges: false,
              }
            : f
        )
      );

      // 4. 輪詢 job 狀態直到 READY / FAILED
      const jobId = createdJob.id as string;
      let lastJob: any = createdJob;
      for (let i = 0; i < 120; i++) {
        await sleep(1000);
        lastJob = await fetchImportJob(jobId);

        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: lastJob.status === 'READY' || lastJob.status === 'FAILED' ? 'validated' : 'validating',
                  validateProgress: toValidateProgress(lastJob.status),
                }
              : f
          )
        );

        if (lastJob.status === 'READY' || lastJob.status === 'FAILED') break;
      }

      if (!lastJob || (lastJob.status !== 'READY' && lastJob.status !== 'FAILED')) {
        throw new Error(t('upload.errors.validationTimeout'));
      }

      if (lastJob.status === 'FAILED') {
        const message = lastJob.error_summary?.error || t('upload.errors.validateFailed');
        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'validated',
                  isValidated: true,
                  validationErrors: [{ row_index: 0, field: 'system', error_code: 'FAILED', message }],
                }
              : f
          )
        );
        if (!options?.silentToast) showToast('error', t('upload.toast.validationFailedWithMessage', { fileName: target.name, message }));
        return { outcome: 'failed', message };
      }

      const totalRows = Number(lastJob.total_rows || 0);
      const errorCount = Number(lastJob.error_count || 0);

      if (errorCount > 0) {
        // 只在有錯誤時抓 errors（避免大量資料傳輸）
        const errorsRes = await fetch(`/api/v2/import/jobs/${jobId}/errors?page=1&page_size=200`, {
          headers: buildTenantHeaders(),
        });
        const errorRows = errorsRes.ok ? await errorsRes.json() : [];

        const flattenedErrors = (Array.isArray(errorRows) ? errorRows : []).flatMap((row: any) => {
          const rowIndex0 = Math.max(0, Number(row.row_index || 1) - 1); // v2 staging row_index 是 1-based
          const errs = Array.isArray(row.errors) ? row.errors : [];
          if (errs.length === 0) {
            return [{ row_index: rowIndex0, field: 'row', error_code: 'INVALID', message: 'Row is invalid' }];
          }
          return errs.map((e: any) => ({
            row_index: rowIndex0,
            field: String(e.field ?? e.column ?? 'row'),
            error_code: String(e.error_code ?? 'INVALID'),
            message: String(e.message ?? JSON.stringify(e)),
          }));
        });

        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'validated',
                  validateProgress: 100,
                  isValidated: true,
                  validationErrors: flattenedErrors,
                  hasUnsavedChanges: false,
                }
              : f
          )
        );

        if (!options?.silentToast) {
          showToast('error', t('upload.toast.validationDoneWithInvalidRowsNoEdit', { fileName: target.name, totalRows, errorCount }));
        }

        return { outcome: 'errors', totalRows, errorCount };
      } else {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'validated',
                  validateProgress: 100,
                  isValidated: true,
                  validationErrors: [],
                  hasUnsavedChanges: false,
                }
              : f
          )
        );

        if (!options?.silentToast) showToast('success', t('upload.toast.validationPassedAllRows', { fileName: target.name, totalRows }));

        return { outcome: 'passed', totalRows };
      }
      
    } catch (err) {
      console.error('Validation error:', err);
      const errorMessage = err instanceof Error ? err.message : t('upload.errors.validationProcessError');
      if (!options?.silentToast) showToast("error", errorMessage);
      
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId 
            ? { ...f, status: "uploaded", validateProgress: 0 } 
            : f
        )
      );

      return { outcome: 'failed', message: errorMessage };
    }
  };

  const handleValidateAll = async () => {
    const currentFiles = filesRef.current;
    const targets = currentFiles.filter(fileEligibleForValidate);
    if (targets.length === 0) {
      showToast('info', t('upload.batchValidate.toast.noEligible'));
      return;
    }

    setIsValidatingAll(true);
    showToast('info', t('upload.batchValidate.toast.start', { count: targets.length }), { key: 'validateAll', durationMs: null });

    let okCount = 0;
    let errorCount = 0;
    let failCount = 0;

    for (let i = 0; i < targets.length; i++) {
      const f = targets[i];
      showToast('info', t('upload.batchValidate.toast.progress', { current: i + 1, total: targets.length, fileName: f.name }), { key: 'validateAll', durationMs: null });
      const result = await handleValidate(f.id, { silentToast: true });
      if (result.outcome === 'passed') okCount += 1;
      else if (result.outcome === 'errors') errorCount += 1;
      else failCount += 1;
    }

    setIsValidatingAll(false);
    if (failCount > 0) {
      showToast('error', t('upload.batchValidate.toast.doneWithFailures', { ok: okCount, errors: errorCount, failed: failCount }), { key: 'validateAll', durationMs: 2500 });
    } else if (errorCount > 0) {
      showToast('error', t('upload.batchValidate.toast.doneWithErrors', { ok: okCount, errors: errorCount }), { key: 'validateAll', durationMs: 2500 });
    } else {
      showToast('success', t('upload.batchValidate.toast.doneAllPassed', { ok: okCount }), { key: 'validateAll', durationMs: 2500 });
    }
  };

  const fileEligibleForConvert = (f: UploadedFile): boolean => {
    if (f.type !== 'PDF') return false;
    if (!f.isValidated) return false;
    if (f.pdfConvertStatus === 'queued' || f.pdfConvertStatus === 'uploading' || f.pdfConvertStatus === 'processing' || f.pdfConvertStatus === 'completed') return false;
    return true;
  };

  const handleConvertAll = async () => {
    const currentFiles = filesRef.current;
    const targets = currentFiles.filter(fileEligibleForConvert);
    if (targets.length === 0) {
      showToast('info', t('upload.batchConvert.toast.noEligible'));
      return;
    }

    setIsConvertingAll(true);
    showToast('info', t('upload.batchConvert.toast.start', { count: targets.length }), { key: 'convertAll', durationMs: null });

    let okCount = 0;
    let failCount = 0;

    for (let i = 0; i < targets.length; i++) {
      const f = targets[i];
      showToast('info', t('upload.batchConvert.toast.progress', { current: i + 1, total: targets.length, fileName: f.name }), { key: 'convertAll', durationMs: null });
      try {
        await handlePdfConvert(f.id);
        okCount += 1;
      } catch {
        failCount += 1;
      }
    }

    setIsConvertingAll(false);
    if (failCount > 0) {
      showToast('error', t('upload.batchConvert.toast.doneWithFailures', { ok: okCount, failed: failCount }), { key: 'convertAll', durationMs: 2500 });
    } else {
      showToast('success', t('upload.batchConvert.toast.doneAllPassed', { ok: okCount }), { key: 'convertAll', durationMs: 2500 });
    }
  };

  const handlePdfConvert = async (fileId: string) => {
    const target = files.find((f) => f.id === fileId);
    if (!target) return;
    if (target.type !== 'PDF') return;
    if (!target.processId) {
      showToast('error', t('upload.toast.missingProcessIdUploadPdf'));
      return;
    }

    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId
          ? {
              ...f,
              pdfConvertStatus: 'queued',
              pdfConvertProgress: 10,
              pdfConvertError: undefined,
            }
          : f
      )
    );

    try {
      const res = await fetch(`/api/upload/pdf/${target.processId}/convert`, {
        method: 'POST',
        headers: buildTenantHeaders(),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: t('upload.errors.triggerPdfConvertFailed') }));
        const message =
          typeof errorData.detail === 'string'
            ? errorData.detail
            : (errorData.detail?.detail || t('upload.errors.triggerPdfConvertFailed'));
        throw new Error(message);
      }

      const trigger = await res.json();
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? {
                ...f,
                pdfConvertJobId: trigger.job_id,
              }
            : f
        )
      );

      // Poll status until completed/failed.
      // Backend job will eventually resolve; 1800 iterations ≈ 30 min safety net.
      // Individual poll failures are tolerated (transient network / proxy errors)
      // to avoid aborting while the backend is still working.
      const maxTries = 1800;
      const maxConsecutiveErrors = 10;
      let consecutiveErrors = 0;
      for (let i = 0; i < maxTries; i++) {
        let s: any;
        try {
          s = await fetchPdfConvertStatus(target.processId);
          consecutiveErrors = 0; // reset on success
        } catch {
          consecutiveErrors++;
          if (consecutiveErrors >= maxConsecutiveErrors) {
            showToast('error', t('upload.toast.pdfConvertFailed'));
            return;
          }
          // Transient error — wait longer before retrying
          await new Promise((r) => setTimeout(r, 3000));
          continue;
        }

        const status = String(s.status || '');
        const progress = typeof s.progress === 'number' ? s.progress : toPdfConvertProgress(status);
        const errorSummary = s.error_summary;
        const errorText = errorSummary?.error ? String(errorSummary.error) : undefined;

        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  pdfConvertStatus:
                    status === 'COMPLETED'
                      ? 'completed'
                      : status === 'FAILED'
                      ? 'failed'
                      : status === 'UPLOADING'
                      ? 'uploading'
                      : status === 'PROCESSING'
                      ? 'processing'
                      : status === 'QUEUED'
                      ? 'queued'
                      : 'not_started',
                  pdfConvertProgress: progress,
                  pdfConvertError:
                    status === 'FAILED' ? (errorText || t('upload.toast.pdfConvertFailed')) : undefined,
                }
              : f
          )
        );

        if (status === 'COMPLETED') {
          try {
            showToast('info', t('upload.toast.pdfConvertFetchingCsv'), { key: `pdfIngest:${target.processId}`, durationMs: null });
            const outputsResp = await fetchPdfConvertedCsvOutputs(target.processId);
            const outputs = Array.isArray(outputsResp) ? outputsResp : (outputsResp?.outputs || []);

            const newCsvFiles: UploadedFile[] = [];
            for (const u of outputs) {
              const filename = String(u.filename || 'output.csv');
              const csvText = typeof u.csv_text === 'string' ? u.csv_text : '';

              // 若同名已存在，避免覆蓋（仍可用 process_id 區分）
              const safeName = filesRef.current.some((f) => f.name === filename) || newCsvFiles.some((f) => f.name === filename)
                ? `${filename.replace(/\.csv$/i, '')}__${Date.now().toString().slice(-6)}.csv`
                : filename;

              const file = new File([csvText], safeName, { type: 'text/csv' });
              const type = detectFileType(safeName);
              const lotNo = type === 'P1' || type === 'P2' ? deriveLotNoFromFilename(safeName) : '';
              const csvData = await parseCsv(file);

              const id = `${safeName}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
              newCsvFiles.push({
                id,
                file,
                name: safeName,
                size: file.size,
                type,
                lotNo,
                status: 'uploaded',
                jobBackend: 'import_v2',
                uploadProgress: 100,
                validateProgress: 0,
                importProgress: 0,
                expanded: false,
                csvData,
                hasUnsavedChanges: false,
                processId: undefined,
                isValidated: false,
                validationErrors: undefined,

                pdfConvertStatus: undefined,
                pdfConvertJobId: undefined,
                pdfConvertProgress: undefined,
                pdfConvertError: undefined,
              });
            }

            if (newCsvFiles.length) {
              setFiles((prev) => {
                const withoutPdf = prev.filter((f) => f.id !== fileId);
                return [...withoutPdf, ...newCsvFiles];
              });
              showToast(
                'success',
                t('upload.toast.pdfConvertGotCsv', { count: newCsvFiles.length }),
                { key: `pdfIngest:${target.processId}`, durationMs: 2500 }
              );
            } else {
              showToast('info', t('upload.toast.pdfConvertNoCsv'), { key: `pdfIngest:${target.processId}`, durationMs: 2500 });
            }
          } catch (e: any) {
            showToast(
              'error',
              e?.message || t('upload.toast.pdfConvertCreateCsvJobFailed'),
              { key: `pdfIngest:${target.processId}`, durationMs: 3000 }
            );
          }
          return;
        }
        if (status === 'FAILED') {
          showToast('error', errorText || t('upload.toast.pdfConvertFailed'));
          return;
        }

        await new Promise((r) => setTimeout(r, 1000));
      }

      showToast('info', t('upload.toast.pdfConvertStillProcessing'));
    } catch (e: any) {
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? {
                ...f,
                pdfConvertStatus: 'failed',
                pdfConvertProgress: 100,
                pdfConvertError: e?.message || t('upload.toast.pdfConvertFailed'),
              }
            : f
        )
      );
      showToast('error', e?.message || t('upload.toast.pdfConvertFailed'));
    }
  };

  const updateCell = (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => {
    if (!EDIT_ENABLED) return;
    setFiles((prev) =>
      prev.map((f) => {
        if (f.id !== fileId || !f.csvData) return f;
        const rows = f.csvData.rows.map((row, rIdx) =>
          rIdx === rowIndex
            ? row.map((cell, cIdx) => (cIdx === colIndex ? value : cell))
            : row
        );

        const shouldResetV2Job = f.jobBackend === 'import_v2';
        return {
          ...f,
          csvData: { ...f.csvData, rows },
          hasUnsavedChanges: true,
          // 編輯後，避免沿用舊的驗證/匯入結果（特別是 v2 job_id）
          status: 'uploaded',
          validateProgress: 0,
          importProgress: 0,
          isValidated: false,
          validationErrors: undefined,
          processId: shouldResetV2Job ? undefined : f.processId,
        };
      })
    );
  };

  const handleSaveChanges = async (fileId: string) => {
    if (!EDIT_ENABLED) {
      showToast("info", t('upload.editDisabledNotice'));
      return;
    }
    const target = files.find((f) => f.id === fileId);
    if (!target || !target.csvData || !target.hasUnsavedChanges) return;

    if (target.jobBackend !== 'import_v2') {
      showToast('error', t('upload.errors.saveError'));
      return;
    }

    // v2：目前沒有「更新既有 job 檔案內容」的後端 API。
    // 這裡把修改套用到前端 File（作為下一次驗證上傳的來源），並重置 jobId。
    const csv_text = buildCsvText(target.csvData);
    const updatedFile = new File([csv_text], target.name, { type: 'text/csv' });

    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId
          ? {
              ...f,
              file: updatedFile,
              size: updatedFile.size,
              hasUnsavedChanges: false,
              status: 'uploaded',
              validateProgress: 0,
              importProgress: 0,
              processId: undefined,
              isValidated: false,
              validationErrors: undefined,
            }
          : f
      )
    );

    showToast('success', t('upload.toast.changesAppliedRevalidate'));
  };

  const handleToggleExpand = (fileId: string) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, expanded: !f.expanded } : f
      )
    );
  };

  // 批次匯入所有已驗證的檔案
  const handleBatchImportClick = () => {
    const validatedFiles = files.filter(f => 
      f.status === "validated" && 
      f.processId && 
      !f.hasUnsavedChanges &&
      (!f.validationErrors || f.validationErrors.length === 0)
    );
    
    if (validatedFiles.length === 0) {
      const filesWithErrors = files.filter(f => 
        f.status === "validated" && 
        f.validationErrors && 
        f.validationErrors.length > 0
      );
      const unvalidatedFiles = files.filter(f => f.status === "uploaded");
      
      if (filesWithErrors.length > 0) {
        showToast("error", t('upload.batchImport.title.hasErrors', { count: filesWithErrors.length }));
      } else if (unvalidatedFiles.length > 0) {
        showToast("error", t('upload.batchImport.title.notValidated', { count: unvalidatedFiles.length }));
      } else {
        showToast("error", t('upload.batchImport.title.noValidated'));
      }
      return;
    }
    
    // 顯示確認彈窗
    setShowBatchImportConfirm(true);
  };

  const performBatchImport = async () => {
    setShowBatchImportConfirm(false);
    
    const totalFiles = files.length;
    
    // 只允許匯入沒有驗證錯誤的檔案
    const validatedFiles = files.filter(f => 
      f.status === "validated" && 
      f.processId && 
      !f.hasUnsavedChanges &&
      (!f.validationErrors || f.validationErrors.length === 0)
    );
    
    const filesWithErrors = files.filter(f => 
      f.status === "validated" && 
      f.validationErrors && 
      f.validationErrors.length > 0
    );
    
    const unvalidatedFiles = files.filter(f => f.status === "uploaded");
    
    if (validatedFiles.length === 0) {
      if (filesWithErrors.length > 0) {
        showToast("error", t('upload.batchImport.title.hasErrors', { count: filesWithErrors.length }));
      } else if (unvalidatedFiles.length > 0) {
        showToast("error", t('upload.batchImport.title.notValidated', { count: unvalidatedFiles.length }));
      } else {
        showToast("error", t('upload.batchImport.title.noValidated'));
      }
      return;
    }
    
    // 區分單檔和多檔情況
    const isSingleFile = totalFiles === 1;
    
    if (!isSingleFile && filesWithErrors.length > 0) {
      showToast("info", t('upload.batchImport.info.multiUploadSkipErrors', { errorCount: filesWithErrors.length, validCount: validatedFiles.length }));
    }

    showToast(
      "info",
      isSingleFile
        ? t('upload.batchImport.toast.startSingle')
        : t('upload.batchImport.toast.startBatch', { count: validatedFiles.length }),
      { key: 'import', durationMs: null }
    );

    // 設置所有檔案為匯入中狀態
    setFiles(prev => 
      prev.map(f => 
        validatedFiles.some(vf => vf.id === f.id)
          ? { ...f, status: "importing", importProgress: 10 }
          : f
      )
    );

    try {
      let totalImported = 0;
      
      for (const [index, file] of validatedFiles.entries()) {
        showToast('info', t('upload.batchImport.toast.progress', { current: index + 1, total: validatedFiles.length, fileName: file.name }), { key: 'import', durationMs: null });
        const progress = Math.round((index / validatedFiles.length) * 80) + 10;
        
        setFiles(prev => 
          prev.map(f => 
            f.id === file.id 
              ? { ...f, importProgress: progress }
              : f
          )
        );

        const jobId = file.processId as string;
        const commitResponse = await fetch(`/api/v2/import/jobs/${jobId}/commit`, {
          method: 'POST',
          headers: buildTenantHeaders(),
        });

        if (!commitResponse.ok) {
          const errorData = await commitResponse.json().catch(() => ({ detail: t('upload.errors.importFailed') }));
          const errorMessage = typeof errorData.detail === 'string'
            ? errorData.detail
            : errorData.detail?.detail || t('upload.errors.importFailed');
          throw new Error(t('upload.batchImport.error.fileImportFailed', { fileName: file.name, errorMessage }));
        }

        // 輪詢到 COMPLETED / FAILED
        let committedJob = await commitResponse.json();
        for (let i = 0; i < 300; i++) {
          await sleep(1000);
          committedJob = await fetchImportJob(jobId);
          setFiles(prev => prev.map(f => f.id === file.id ? { ...f, importProgress: toImportProgress(committedJob.status) } : f));
          if (committedJob.status === 'COMPLETED' || committedJob.status === 'FAILED') break;
        }

        if (committedJob.status !== 'COMPLETED') {
          const message = committedJob.error_summary?.error || t('upload.errors.importFailed');
          throw new Error(t('upload.batchImport.error.fileImportFailed', { fileName: file.name, errorMessage: message }));
        }

        totalImported += Number(committedJob.total_rows || 0);

        setFiles(prev => 
          prev.map(f => 
            f.id === file.id 
              ? { ...f, status: "imported", importProgress: 100 }
              : f
          )
        );
      }
      
      showToast(
        "success",
        isSingleFile
          ? t('upload.batchImport.toast.completedSingle', { fileCount: validatedFiles.length, rowCount: totalImported })
          : t('upload.batchImport.toast.completedBatch', { fileCount: validatedFiles.length, rowCount: totalImported }),
        { key: 'import', durationMs: 2500 }
      );
      
      // 處理匯入後的檔案清理 - 統一只移除已匯入的檔案，不區分單檔或多檔
      setTimeout(() => {
        // 使用 ref 獲取最新狀態
        const currentFiles = filesRef.current;
        const remainingFiles = currentFiles.filter(f => 
          !validatedFiles.some(vf => vf.id === f.id)
        );

        // 移除已匯入的檔案，保留其他檔案（包括有錯誤的或待驗證的）
        setFiles(remainingFiles);
        
        if (remainingFiles.length > 0) {
          showToast("info", t('upload.batchImport.toast.remainingFiles', { count: remainingFiles.length }));
        } else {
          showToast("info", t('upload.batchImport.toast.allDone'));
        }
      }, 2000);
      
    } catch (err) {
      console.error('Batch import error:', err);
      const errorMessage = err instanceof Error ? err.message : t('upload.batchImport.error.generic');
      showToast("error", errorMessage, { key: 'import', durationMs: 4000 });
      
      // 重置匯入狀態
      setFiles(prev => 
        prev.map(f => 
          validatedFiles.some(vf => vf.id === f.id)
            ? { ...f, status: "validated", importProgress: 0 }
            : f
        )
      );
    }
  };

  const performImport = async () => {
    if (!confirmTargetId) return;
    const id = confirmTargetId;
    setConfirmTargetId(null);

    const target = files.find((f) => f.id === id);
    if (!target || !target.processId) {
      showToast('error', t('upload.toast.missingFileOrJobId'));
      return;
    }

    showToast('info', t('upload.toast.importStarting', { fileName: target.name }), { key: 'import', durationMs: null });

    setFiles((prev) =>
      prev.map((f) =>
        f.id === id
          ? { ...f, status: "importing", importProgress: 20 }
          : f
      )
    );

    try {
      const jobId = target.processId as string;
      const commitResponse = await fetch(`/api/v2/import/jobs/${jobId}/commit`, {
        method: 'POST',
        headers: buildTenantHeaders(),
      });

        setFiles((prev) =>
          prev.map((f) =>
            f.id === id ? { ...f, importProgress: 60 } : f
          )
        );

      if (!commitResponse.ok) {
        const errorData = await commitResponse.json().catch(() => ({ detail: t('upload.errors.importFailed') }));
        const errorMessage = typeof errorData.detail === 'string' 
          ? errorData.detail 
          : errorData.detail?.detail || t('upload.errors.importFailed');
        throw new Error(errorMessage);
      }

      // 輪詢到 COMPLETED / FAILED
      let committedJob = await commitResponse.json();
      for (let i = 0; i < 300; i++) {
        await sleep(1000);
        committedJob = await fetchImportJob(jobId);
        setFiles((prev) =>
          prev.map((f) => (f.id === id ? { ...f, importProgress: toImportProgress(committedJob.status) } : f))
        );
        if (committedJob.status === 'COMPLETED' || committedJob.status === 'FAILED') break;
      }

      if (committedJob.status !== 'COMPLETED') {
        const message = committedJob.error_summary?.error || t('upload.errors.importFailed');
        throw new Error(message);
      }

      setFiles((prev) =>
        prev.map((f) =>
          f.id === id
            ? { ...f, status: "imported", importProgress: 100 }
            : f
        )
      );

      showToast('success', t('upload.toast.importCompleted', { fileName: target.name }), { key: 'import', durationMs: 2500 });
      
      // 延遲後根據檔案數量決定行為
      setTimeout(() => {
        // 使用 ref 獲取最新狀態，避免在 updater 中執行副作用
        const currentFiles = filesRef.current;
        const remainingFiles = currentFiles.filter(f => f.id !== id);
        
        // 如果原本只有一個檔案，重置整個頁面
        if (currentFiles.length === 1) {
          showToast('info', t('upload.toast.pageResetContinueUpload'));
          setFiles([]);
        } 
        // 如果有多個檔案，只移除已匯入的檔案
        else {
          showToast('info', t('upload.batchImport.toast.remainingFiles', { count: remainingFiles.length }));
          setFiles(remainingFiles);
        }
      }, 2000);
      
    } catch (err) {
      console.error('Import error:', err);
      const errorMessage = err instanceof Error ? err.message : t('upload.errors.importError');
      showToast("error", errorMessage, { key: 'import', durationMs: 4000 });
      
      setFiles((prev) =>
        prev.map((f) =>
          f.id === id ? { ...f, status: "validated", importProgress: 0 } : f
        )
      );
    }
  };

  const handleRemoveFile = (fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  return (
    <div className="upload-page">
      {/* 拖曳/選擇檔案區 */}
      <section className="upload-drop-section">
        <FileDropArea onFiles={handleFiles} />
      </section>

      {/* 已上傳檔案列表 */}
      <section className="uploaded-list-section">
        {!EDIT_ENABLED && (
          <div style={{
            margin: '8px 0 12px 0',
            padding: '10px 12px',
            border: '1px solid #fde68a',
            backgroundColor: '#fffbeb',
            borderRadius: '6px',
            color: '#92400e',
            fontSize: '14px'
          }}>
            {t('upload.editDisabledNotice')}
          </div>
        )}
        <div className="section-header">
          <h2 className="section-title">{t('upload.uploadedFiles')}</h2>
          {files.length > 0 && (
            <div className="batch-actions">
              {(() => {
                const eligibleCount = files.filter(fileEligibleForValidate).length;
                const anyBusy = files.some((f) => f.status === 'validating' || f.status === 'importing');
                const disabled = isValidatingAll || anyBusy || eligibleCount === 0;

                let title = '';
                if (disabled) {
                  if (eligibleCount === 0) title = t('upload.batchValidate.title.noEligible');
                  else title = t('upload.batchValidate.title.busy');
                } else {
                  title = t('upload.batchValidate.title.ready', { count: eligibleCount });
                }

                return (
                  <button
                    className={`btn-secondary ${disabled ? 'btn-secondary--disabled' : ''}`}
                    onClick={handleValidateAll}
                    disabled={disabled}
                    title={title}
                    style={{ marginRight: '10px' }}
                  >
                    {isValidatingAll
                      ? t('upload.batchValidate.buttonLabelBusy')
                      : t('upload.batchValidate.buttonLabel', { count: eligibleCount })}
                  </button>
                );
              })()}
              {(() => {
                const convertEligibleCount = files.filter(fileEligibleForConvert).length;
                if (convertEligibleCount === 0 && !isConvertingAll) return null;
                const anyConverting = files.some((f) => f.pdfConvertStatus === 'queued' || f.pdfConvertStatus === 'uploading' || f.pdfConvertStatus === 'processing');
                const disabled = isConvertingAll || anyConverting || convertEligibleCount === 0;

                return (
                  <button
                    className={`btn-secondary ${disabled ? 'btn-secondary--disabled' : ''}`}
                    onClick={handleConvertAll}
                    disabled={disabled}
                    title={disabled ? t('upload.batchConvert.title.busy') : t('upload.batchConvert.title.ready', { count: convertEligibleCount })}
                    style={{ marginRight: '10px' }}
                  >
                    {isConvertingAll
                      ? t('upload.batchConvert.buttonLabelBusy')
                      : t('upload.batchConvert.buttonLabel', { count: convertEligibleCount })}
                  </button>
                );
              })()}
              {(() => {
                const validatedFiles = files.filter(f => f.status === "validated" && f.processId);
                const validFilesWithoutErrors = validatedFiles.filter(f => !f.validationErrors || f.validationErrors.length === 0);
                const filesWithErrors = validatedFiles.filter(f => f.validationErrors && f.validationErrors.length > 0);
                const isDisabled = validFilesWithoutErrors.length === 0;
                
                let buttonText = t('upload.batchImport.buttonLabel', { count: validFilesWithoutErrors.length });
                let buttonTitle = "";
                
                if (isDisabled) {
                  if (filesWithErrors.length > 0) {
                    buttonTitle = t('upload.batchImport.title.hasErrors', { count: filesWithErrors.length });
                  } else {
                    buttonTitle = t('upload.batchImport.title.noValidated');
                  }
                } else {
                  buttonTitle = t('upload.batchImport.title.ready', { validCount: validFilesWithoutErrors.length });
                  if (filesWithErrors.length > 0) {
                    buttonTitle += ` ${t('upload.batchImport.title.skipErrorsSuffix', { errorCount: filesWithErrors.length })}`;
                  }
                }
                
                return (
                  <button
                    className={`btn-primary batch-import-btn ${isDisabled ? "btn-primary--disabled" : ""}`}
                    onClick={handleBatchImportClick}
                    disabled={isDisabled}
                    title={buttonTitle}
                  >
                    {buttonText}
                    {filesWithErrors.length > 0 && (
                      <span style={{ color: '#f59e0b', marginLeft: '8px' }}>
                         {t('upload.batchImport.errorBadge', { count: filesWithErrors.length })}
                      </span>
                    )}
                  </button>
                );
              })()}
            </div>
          )}
        </div>
        
        {files.length === 0 && (
          <p className="section-empty">{t('upload.empty')}</p>
        )}

        <div className="uploaded-list">
          {[...files]
            .map((f, idx) => ({ f, idx }))
            .sort((a, b) => {
              const ae = fileHasValidationErrors(a.f) ? 1 : 0;
              const be = fileHasValidationErrors(b.f) ? 1 : 0;
              if (be !== ae) return be - ae;
              return a.idx - b.idx;
            })
            .map(({ f }) => (
            <UploadedFileCard
              key={f.id}
              file={f}
              onValidate={() => handleValidate(f.id)}
              onConvertPdf={() => handlePdfConvert(f.id)}
              onSaveChanges={() => handleSaveChanges(f.id)}
              onToggleExpand={() => handleToggleExpand(f.id)}
              onRemove={() => handleRemoveFile(f.id)}
              onImport={(fileId) => setConfirmTargetId(fileId)}
              onCellChange={updateCell}
            />
          ))}
        </div>
      </section>

      <Modal
        open={confirmTargetId !== null}
        title={t('upload.importConfirm.title')}
        onClose={() => setConfirmTargetId(null)}
        onConfirm={performImport}
        confirmText={t('upload.importConfirm.confirmText')}
      >
        <p>{t('upload.importConfirm.body')}</p>
      </Modal>

      <Modal
        open={showBatchImportConfirm}
        title={t('upload.batchImport.confirm.title')}
        onClose={() => setShowBatchImportConfirm(false)}
        onConfirm={performBatchImport}
        confirmText={t('upload.batchImport.confirm.confirmText')}
        maxWidth="min(720px, 92vw)"
      >
        {(() => {
          const validFilesWithoutErrors = files.filter(f => 
            f.status === "validated" && 
            f.processId && 
            (!f.validationErrors || f.validationErrors.length === 0)
          );
          const filesWithErrors = files.filter(f => 
            f.status === "validated" && 
            f.validationErrors && 
            f.validationErrors.length > 0
          );
          
          return (
            <div className="batch-import-confirm">
              <p style={{ marginBottom: '12px' }}>
                {t('upload.batchImport.confirm.summary', { count: validFilesWithoutErrors.length })}
              </p>
              <p style={{ marginBottom: '12px', color: '#dc2626', fontWeight: 'bold' }}>
                {t('upload.batchImport.confirm.warning')}
              </p>
              {filesWithErrors.length > 0 && (
                <p style={{ 
                  padding: '8px 12px', 
                  backgroundColor: '#fef2f2', 
                  border: '1px solid #fecaca',
                  borderRadius: '4px',
                  color: '#7f1d1d',
                  fontSize: '14px'
                }}>
                   {t('upload.batchImport.confirm.skipNotice', { count: filesWithErrors.length })}
                </p>
              )}
              {validFilesWithoutErrors.length > 0 && (
                <div className="batch-import-confirm__list-wrap">
                  <p style={{ fontWeight: 'bold', marginBottom: '8px' }}>{t('upload.batchImport.confirm.pendingListTitle')}</p>
                  <ul className="batch-import-confirm__list">
                    {validFilesWithoutErrors.map(f => (
                      <li key={f.id} className="batch-import-confirm__item">
                        <div className="batch-import-confirm__row">
                          <span className="batch-import-confirm__type">{f.type}</span>
                          <span className="batch-import-confirm__name" title={f.name}>{f.name}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}

/* ------------ 子元件：拖曳上傳區 ------------ */

interface FileDropAreaProps {
  onFiles: (files: FileList | null) => void;
}

function FileDropArea({ onFiles }: FileDropAreaProps) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  };

  const handleDragOver: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    setDragging(false);
  };

  const handleChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    onFiles(e.target.files);
    e.target.value = "";
  };

  return (
    <div className="upload-drop-wrapper">
      <div
        className={`upload-drop-area ${
          dragging ? "upload-drop-area--dragging" : ""
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <div className="upload-drop-icon">⬆</div>
        <p className="upload-drop-main-text">{t('upload.dropMain')}</p>
        <p className="upload-drop-sub-text">{t('upload.dropSub')}</p>
        <label className="upload-drop-button">
          {t('upload.chooseFile')}
          <input type="file" accept=".csv,.pdf" multiple onChange={handleChange} />
        </label>
      </div>
    </div>
  );
}

/* ------------ 子元件：已上傳檔案卡片 + CSV 編輯 ------------ */

interface UploadedFileCardProps {
  file: UploadedFile;
  onValidate: () => void;
  onConvertPdf: () => void;
  onSaveChanges: () => void;
  onToggleExpand: () => void;
  onRemove: () => void;
  onImport: (fileId: string) => void;
  onCellChange: (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => void;
}

function UploadedFileCard({
  file,
  onValidate,
  onConvertPdf,
  onSaveChanges,
  onToggleExpand,
  onRemove,
  onImport,
  onCellChange,
}: UploadedFileCardProps) {
  const { t } = useTranslation();
  
  // 驗證按鈕是否可用：未驗證過且不在驗證中
  const disabledValidate = 
    file.status === "validating" || file.status === "importing";
  
  // 檢查檔案是否有驗證錯誤
  const hasValidationErrors = file.validationErrors && file.validationErrors.length > 0;
    
  // 儲存按鈕是否可用：必須有CSV資料且有未儲存變更
  const disabledSave =
    !EDIT_ENABLED || !file.csvData || !file.hasUnsavedChanges;

  const isPdf = file.type === 'PDF';

  const pdfStatusText = () => {
    if (!isPdf || !file.isValidated) return '';
    switch (file.pdfConvertStatus) {
      case 'queued':
      case 'uploading':
      case 'processing':
        return t('upload.pdf.status.converting');
      case 'completed':
        return t('upload.pdf.status.converted');
      case 'failed':
        return t('upload.pdf.status.convertFailed');
      case 'not_started':
      default:
        return t('upload.pdf.status.uploadedPendingConvert');
    }
  };

  return (
    <div className="uploaded-card">
      <div className="uploaded-card__header">
        <div className="uploaded-card__info">
          <div className="uploaded-card__filename">
            <span className="filetype-tag">{file.type}</span>
            {file.name}
            {hasValidationErrors && file.validationErrors && (
              <span 
                className="error-indicator" 
                style={{
                  marginLeft: '8px',
                  color: '#dc2626',
                  fontWeight: 'bold',
                  fontSize: '14px',
                  cursor: 'pointer',
                  textDecoration: 'underline'
                }}
                title={t('upload.tooltips.validationErrorsExpand', { count: file.validationErrors.length })}
                onClick={() => {
                  if (!file.expanded) {
                    onToggleExpand();
                  }
                  // 添加視覺提示，滾動到錯誤區域
                  setTimeout(() => {
                    const errorSection = document.querySelector('.validation-errors-section');
                    if (errorSection) {
                      errorSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                  }, 100);
                }}
              >
                 {t('upload.validationErrors.count', { count: file.validationErrors.length })}
              </span>
            )}
            {file.isValidated && !hasValidationErrors && (
              <span 
                className="success-indicator"
                style={{
                  marginLeft: '8px',
                  color: '#059669',
                  fontWeight: 'bold',
                  fontSize: '14px'
                }}
                title={t('upload.status.validationPassed')}
              >
                 {t('upload.status.validationPassed')}
              </span>
            )}
          </div>
          <div className="uploaded-card__meta">
            <span>{(file.size / 1024).toFixed(1)} KB</span>
            {file.lotNo && <span>{t('upload.lotNoLabel')}: {file.lotNo}</span>}
          </div>
        </div>
        <div className="uploaded-card__actions">
          <button className="icon-button" onClick={onRemove} title={t('upload.actions.remove')}>
            ✕
          </button>
        </div>
      </div>

      <div className="uploaded-card__body">
        <div className="uploaded-card__status">
          {file.status === "uploaded" && (
            <span>{isPdf && file.isValidated ? pdfStatusText() : t('upload.status.pendingValidation')}</span>
          )}
          {file.status === "validating" && (
            <span>{t('upload.status.validating')}</span>
          )}
          {file.status === "validated" && <span>{t('upload.status.validated')}</span>}
          {file.status === "importing" && (
            <span>{t('upload.status.importing')}</span>
          )}
          {file.status === "imported" && <span>{t('upload.status.imported')}</span>}
        </div>

        {file.status === "validating" && (
          <ProgressBar value={file.validateProgress} label={t('upload.progress.validation')} />
        )}
        {file.status === "importing" && (
          <ProgressBar value={file.importProgress} label={t('upload.progress.import')} />
        )}

        {isPdf && file.isValidated && (file.pdfConvertStatus === 'queued' || file.pdfConvertStatus === 'uploading' || file.pdfConvertStatus === 'processing') && (
          <ProgressBar value={file.pdfConvertProgress ?? 0} label={t('upload.progress.pdfConvert')} />
        )}

        <div className="uploaded-card__buttons">
          <button
            className={`btn-secondary ${
              disabledValidate ? "btn-secondary--disabled" : ""
            }`}
            onClick={onValidate}
            disabled={disabledValidate}
            title={
              file.status === "validating" 
                ? t('upload.tooltips.validating')
                : file.status === "importing"
                ? t('upload.tooltips.importing')
                : isPdf
                ? t('upload.tooltips.pdfUploadOnly')
                : hasValidationErrors
                ? t('upload.tooltips.revalidateHasErrors')
                : file.isValidated && !hasValidationErrors
                ? t('upload.tooltips.revalidatePassed')
                : t('upload.tooltips.validate')
            }
          >
            {file.status === "validating" 
              ? t('upload.actions.validating')
              : isPdf
              ? (file.isValidated ? t('upload.pdf.upload.uploaded') : t('upload.pdf.upload.upload'))
              : hasValidationErrors 
              ? t('upload.actions.revalidate')
              : file.isValidated 
              ? t('upload.actions.validated')
              : t('upload.actions.validate')
            }
          </button>

          {isPdf && file.isValidated && (
            <button
              className={`btn-primary ${
                file.pdfConvertStatus === 'queued' || file.pdfConvertStatus === 'uploading' || file.pdfConvertStatus === 'processing'
                  ? 'btn-primary--disabled'
                  : ''
              }`}
              onClick={onConvertPdf}
              disabled={
                file.pdfConvertStatus === 'queued' ||
                file.pdfConvertStatus === 'uploading' ||
                file.pdfConvertStatus === 'processing'
              }
              title={
                file.pdfConvertStatus === 'completed'
                  ? t('upload.tooltips.pdfConvertDone')
                  : t('upload.tooltips.pdfConvertStartAsync')
              }
            >
              {file.pdfConvertStatus === 'completed'
                ? t('upload.pdf.convert.done')
                : file.pdfConvertStatus === 'failed'
                ? t('upload.pdf.convert.retry')
                : t('upload.pdf.convert.start')}
            </button>
          )}

          {!isPdf && (
            <button
              className={`btn-secondary ${
                disabledSave ? "btn-secondary--disabled" : ""
              }`}
              onClick={onSaveChanges}
              disabled={disabledSave}
              title={
                !EDIT_ENABLED
                  ? t('upload.editDisabledNotice')
                  : !file.csvData
                  ? t('upload.tooltips.validateBeforeEdit')
                  : !file.hasUnsavedChanges
                  ? t('upload.tooltips.noUnsavedChanges')
                  : t('upload.tooltips.saveChanges')
              }
            >
              {t('upload.actions.saveChanges')}
            </button>
          )}

          {/* 個別檔案匯入按鈕 */}
          {!isPdf && file.status === "validated" && !hasValidationErrors && !file.hasUnsavedChanges && (
            <button
              className="btn-primary"
              onClick={() => onImport(file.id)}
              title={t('upload.tooltips.importToDb')}
            >
              {t('upload.actions.importFile')}
            </button>
          )}

          {/* 已驗證檔案顯示準備好的狀態 */}
          {!isPdf && file.status === "validated" && !hasValidationErrors && !file.hasUnsavedChanges && (
            <span className="status-badge status-badge--ready">
              {t('upload.badges.readyToImport')}
            </span>
          )}
          
          {/* 有驗證錯誤時顯示錯誤狀態 */}
          {!isPdf && file.status === "validated" && hasValidationErrors && (
            <span className="status-badge" style={{
              backgroundColor: '#fef2f2',
              color: '#dc2626',
              border: '1px solid #fecaca'
            }}>
               {t('upload.badges.needsFix')}
            </span>
          )}

          {!isPdf && (
            <button className="btn-text" onClick={onToggleExpand}>
              {file.expanded ? t('upload.actions.collapse') : t('upload.actions.expand')} CSV 內容
            </button>
          )}
        </div>

        {isPdf && file.isValidated && file.pdfConvertStatus === 'failed' && file.pdfConvertError && (
          <div style={{ marginTop: '8px', color: '#dc2626', fontSize: '14px' }}>
            轉檔失敗原因：{file.pdfConvertError}
          </div>
        )}
      </div>

      {file.expanded && file.csvData && (
        <CsvEditor
          file={file}
          csv={file.csvData}
          onCellChange={onCellChange}
        />
      )}
    </div>
  );
}

/* ------------ 子元件：CSV 編輯器 ------------ */

interface ValidationError {
  row_index: number;
  field: string;
  error_code: string;
  message: string;
}

interface CsvEditorProps {
  file: UploadedFile;
  csv: CsvData;
  onCellChange: (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => void;
}

function CsvEditor({ file, csv, onCellChange }: CsvEditorProps) {
  const { t } = useTranslation();
  const termMap = useMemo(() => {
    const raw = t('專有名詞對照表', { returnObjects: true }) as Record<string, string> | string;
    if (!raw || typeof raw !== 'object') return {} as Record<string, string>;
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(raw)) {
      out[String(key)] = String(value);
    }
    return out;
  }, [t]);
  const termMapLower = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(termMap)) {
      out[key.trim().toLowerCase()] = value;
    }
    return out;
  }, [termMap]);
  const getHeaderLabel = useCallback((header: string) => {
    const raw = String(header ?? '');
    if (!raw) return '';
    if (raw.trim().toLowerCase() === 'specification') {
      if (file.type === 'P1') return termMap['P1.Specification'] || 'P1.Specification';
      if (file.type === 'P2') return termMap['P2.Specification'] || 'Specification';
      if (file.type === 'P3') return termMap['P3.Specification'] || 'P3.Specification';
    }
    const direct = termMap[raw];
    if (direct) return direct;
    const normalized = raw.trim().toLowerCase();
    return termMapLower[normalized] || raw;
  }, [file.type, termMap, termMapLower]);

  // 創建錯誤映射表，以便快速查找特定行/列的錯誤
  const errorMap = new Map<string, ValidationError>();
  if (file.validationErrors) {
    file.validationErrors.forEach((error: any) => {
      const key = `${error.row_index}_${error.field}`;
      errorMap.set(key, error);
    });
  }

  const errorRowIndexSet = new Set<number>();
  if (Array.isArray(file.validationErrors)) {
    file.validationErrors.forEach((error: any) => {
      const idx = Number(error?.row_index);
      if (!Number.isNaN(idx)) errorRowIndexSet.add(idx);
    });
  }

  const displayRows = csv.rows
    .map((row, originalRowIndex) => ({ row, originalRowIndex }))
    .sort((a, b) => {
      // 有錯誤的資料列自動置頂；同一群組維持原始順序
      const ae = errorRowIndexSet.has(a.originalRowIndex) ? 1 : 0;
      const be = errorRowIndexSet.has(b.originalRowIndex) ? 1 : 0;
      if (be !== ae) return be - ae;
      return a.originalRowIndex - b.originalRowIndex;
    });

  // 檢查特定單元格是否有錯誤
  const getCellError = (rowIndex: number, colIndex: number): ValidationError | undefined => {
    const fieldName = csv.headers[colIndex];
    if (!fieldName) return undefined;
    const key = `${rowIndex}_${fieldName}`;
    return errorMap.get(key) || errorMap.get(`${rowIndex}_${fieldName.toLowerCase()}`);
  };

  return (
    <div className="csv-editor">
      <div className="csv-editor__header">
        <span>
          {t('upload.csvEditor.header', {
            title: EDIT_ENABLED ? t('upload.csvEditor.titleEdit') : t('upload.csvEditor.titlePreview'),
            fileName: file.name,
            rowCount: csv.rows.length,
            colCount: csv.headers.length,
          })}
        </span>
        {file.validationErrors && file.validationErrors.length > 0 && (
          <div className="csv-editor__error-summary">
            <span style={{ color: '#dc2626', fontWeight: 'bold' }}>
              {t('upload.csvEditor.errorSummary', { count: file.validationErrors.length })}
            </span>
          </div>
        )}
      </div>

      <div className="csv-editor__table-wrapper">
        <table className="csv-editor__table">
          <thead>
            <tr>
              {csv.headers.map((h, idx) => (
                <th
                  key={idx}
                  style={{ width: `${csv.colWidths[idx]}px` }}
                >
                  {getHeaderLabel(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map(({ row, originalRowIndex }) => {
              const hasRowError = errorRowIndexSet.has(originalRowIndex);
              
              return (
                <tr 
                  key={originalRowIndex}
                  style={hasRowError ? { backgroundColor: '#fef2f2' } : {}}
                >
                  {row.map((cell, cIdx) => {
                    const cellError = getCellError(originalRowIndex, cIdx);
                    const hasError = !!cellError;
                    const isStar = csv.starCells?.has(`${originalRowIndex}_${cIdx}`);
                    const isEmpty = csv.emptyCells?.has(`${originalRowIndex}_${cIdx}`);
                    const isWarning = isStar || isEmpty;

                    return (
                      <td
                        key={cIdx}
                        style={{
                          width: `${csv.colWidths[cIdx] ?? 160}px`,
                          position: 'relative'
                        }}
                        title={hasError ? t('upload.csvEditor.cellErrorTitle', { message: cellError.message }) : isEmpty ? t('upload.csvEditor.emptyCellTitle', { defaultValue: '此欄位為空白' }) : isStar ? t('upload.csvEditor.starCellTitle', { defaultValue: '此欄位為顯著值 (原始資料含 * 或前後空格)' }) : ''}
                      >
                        <input
                          className={`csv-editor__cell-input ${hasError ? 'csv-editor__cell-input--error' : isWarning ? 'csv-editor__cell-input--star' : ''}`}
                          value={cell ?? ''}
                          readOnly={!EDIT_ENABLED}
                          onChange={(e) => {
                            if (!EDIT_ENABLED) return;
                            onCellChange(file.id, originalRowIndex, cIdx, e.target.value);
                          }}
                          style={hasError ? {
                            backgroundColor: '#fecaca',
                            borderColor: '#dc2626',
                            color: '#dc2626'
                          } : isWarning ? {
                            backgroundColor: '#fefce8',
                            borderColor: '#eab308',
                          } : {}}
                        />
                        {hasError && (
                          <div
                            className="csv-editor__error-indicator"
                            style={{
                              position: 'absolute',
                              top: '2px',
                              right: '2px',
                              width: '8px',
                              height: '8px',
                              backgroundColor: '#dc2626',
                              borderRadius: '50%',
                              fontSize: '10px',
                              color: 'white',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: 'help'
                            }}
                              title={`${t('upload.csvEditor.errorCodeLabel', { code: cellError.error_code })}\n${cellError.message}`}
                          >
                            !
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="csv-editor__hint">
        <p style={{ margin: '0 0 4px 0', fontSize: '0.75rem', color: '#6b7280' }}>
          {EDIT_ENABLED
            ? t('upload.csvEditor.hintEdit')
            : t('upload.csvEditor.hintPreview')}
        </p>
        {file.validationErrors && file.validationErrors.length > 0 ? (
          <p style={{ margin: '0', fontSize: '0.75rem', color: '#dc2626', fontWeight: 'bold' }}>
            {t('upload.csvEditor.hintHasErrors')}
          </p>
        ) : (
          <p style={{ margin: '0', fontSize: '0.75rem', color: '#059669', fontWeight: 'bold' }}>
            {t('upload.csvEditor.hintAllValid')}
          </p>
        )}
      </div>

      {/* 顯示驗證錯誤詳情 - 在CSV表格下方顯示 */}
      {file.validationErrors && file.validationErrors.length > 0 && (
        <div className="validation-errors-section" style={{
          backgroundColor: '#fef2f2',
          border: '2px solid #f87171',
          borderRadius: '8px',
          padding: '16px',
          margin: '12px 0 0 0',
          boxShadow: '0 2px 4px rgba(220, 38, 38, 0.1)'
        }}>
          <h4 style={{ color: '#dc2626', marginBottom: '12px', fontSize: '16px', fontWeight: 'bold' }}>
            {t('upload.csvEditor.errorDetailsTitle', { count: file.validationErrors.length })}
          </h4>
          <div className="error-list" style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {[...file.validationErrors]
              .sort((a: any, b: any) => {
                const ar = Number(a?.row_index ?? 0);
                const br = Number(b?.row_index ?? 0);
                if (ar !== br) return ar - br;
                const af = String(a?.field ?? '');
                const bf = String(b?.field ?? '');
                return af.localeCompare(bf);
              })
              .slice(0, 10)
              .map((error: any, index: number) => (
              <div 
                key={index} 
                className="error-item" 
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #f87171',
                  borderRadius: '4px',
                  padding: '8px 12px',
                  marginBottom: '8px',
                  fontSize: '14px'
                }}
              >
                <div style={{ color: '#dc2626', fontWeight: 'bold' }}>
                  {t('upload.csvEditor.errorRowField', { row: error.row_index + 1, field: error.field })}
                </div>
                <div style={{ color: '#7f1d1d', marginTop: '4px' }}>
                  {t('upload.csvEditor.errorCodeLabel', { code: error.error_code })}
                </div>
                <div style={{ color: '#374151', marginTop: '4px' }}>
                  {error.message}
                </div>
              </div>
            ))}
            {file.validationErrors.length > 10 && (
              <div style={{ color: '#6b7280', fontStyle: 'italic', textAlign: 'center', padding: '8px' }}>
                {t('upload.csvEditor.moreErrorsHint', { count: file.validationErrors.length - 10 })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
