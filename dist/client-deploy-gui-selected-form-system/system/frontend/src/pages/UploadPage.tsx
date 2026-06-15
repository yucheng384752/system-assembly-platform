// src/pages/UploadPage.tsx
import { useState, useCallback, useEffect } from "react";
import { getApiKeyHeaderName, getApiKeyValue } from "../services/auth";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/common/ToastContext";
import { Modal } from "../components/common/Modal";
import { useUploadApi } from "./upload/useUploadApi";
import { delay } from "./upload/uploadAsyncUtils";
import type { CsvData } from "./upload/uploadTypes";
import { saveCsvChangesInFiles, updateCsvCellInFiles } from "./upload/uploadCsvEditUtils";
import { buildUploadFilesToAdd } from "./upload/uploadFileAddUtils";
import { showFileAddResultToasts } from "./upload/uploadFileAddToastUtils";
import { showCsvChangesAppliedToast, showCsvEditDisabledToast, showCsvSaveErrorToast } from "./upload/uploadCsvEditToastUtils";
import { parseCsv } from "./upload/uploadFileUtils";
import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from "./upload/uploadEligibility";
import { runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runSingleImportWorkflow, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";
import { runPdfConvertWorkflow } from "./upload/uploadPdfConversionOrchestrator";
import { showMissingPdfConvertProcessToast } from "./upload/uploadPdfConvertToastUtils";
import { runValidateWorkflow } from "./upload/uploadValidationOrchestrator";
import { showBatchImportUnavailableToast, showMissingImportTargetToast } from "./upload/uploadImportToastUtils";
import { scheduleBatchPostImportCleanup } from "./upload/uploadImportCleanupUtils";
import { toImportProgress, toPdfConvertProgress, toValidateProgress } from "./upload/uploadProgress";
import { BatchActionBar } from "./upload/BatchActionBar";
import { BatchImportConfirmModal } from "./upload/BatchImportConfirmModal";
import { FileDropArea } from "./upload/FileDropArea";
import { UploadedFileCard } from "./upload/UploadedFileCard";
import { useUploadWorkflow } from "./upload/useUploadWorkflow";
import "./../styles/upload-page.css";

const EDIT_ENABLED =
  String((import.meta as any).env?.VITE_ENABLE_CSV_EDIT ?? "true").toLowerCase() === "true";

export function UploadPage() {
  const { files, setFiles, filesRef, removeFile, toggleFileExpanded, beginPdfValidation, completePdfUpload, failPdfValidation, beginCsvValidation, setValidationUploadSource, setValidationProgress, prepareCsvValidationJob, updateValidationPoll, completeValidationFailure, completeValidationWithErrors, completeValidationPassed, failCsvValidation, beginPdfConvert, attachPdfConvertJob, updatePdfConvertProgress, replacePdfWithCsvFiles, failPdfConvert, beginImport, setImportProgress, completeImport, resetImport, removeImportedFiles } = useUploadWorkflow();
  const [confirmTargetId, setConfirmTargetId] = useState<string | null>(null);
  const [showBatchImportConfirm, setShowBatchImportConfirm] = useState(false);
  const [isValidatingAll, setIsValidatingAll] = useState(false);
  const [isConvertingAll, setIsConvertingAll] = useState(false);
  const { t } = useTranslation();
  const { showToast } = useToast();


  const uploadApi = useUploadApi(t);

  // ── 通用表單上傳 ──────────────────────────────────────────────────────────
  const [gStations, setGStations] = useState<{code:string;name:string}[]>([])
  const [gStation, setGStation] = useState('')
  const [gUploading, setGUploading] = useState(false)
  const [gResult, setGResult] = useState<{total:number;imported:number;skipped:number;errors:{row:number;errors:string[]}[]}|null>(null)

  useEffect(() => {
    fetch('/api/forms', { headers: { [getApiKeyHeaderName()]: getApiKeyValue() } })
      .then(r => r.ok ? r.json() : [])
      .then((d: {code:string;name:string}[]) => setGStations(d))
      .catch(() => {})
  }, [])

  const handleGenericUpload = async (file: File) => {
    if (!file || !gStation) return
    setGUploading(true); setGResult(null)
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('allow_duplicate', 'false')
      const r = await fetch(`/api/forms/${gStation}/upload`, {
        method: 'POST',
        headers: { [getApiKeyHeaderName()]: getApiKeyValue() },
        body: fd,
      })
      setGResult(await r.json())
    } catch { /* ignore */ } finally { setGUploading(false) }
  }


  const handleFiles = (fileList: FileList | null) => {
    const result = buildUploadFilesToAdd({
      fileList,
      existingFiles: files,
      confirmLikelyDuplicate: (file) =>
        window.confirm("\u5075\u6e2c\u5230\u7591\u4f3c\u91cd\u8907\u6a94\u6848\uff1a" + file.name + "\n\u662f\u5426\u4ecd\u8981\u52a0\u5165\u4e0a\u50b3\u6e05\u55ae\uff1f"),
    });

    showFileAddResultToasts({
      notices: result.notices,
      addedCount: result.files.length,
      showToast,
      t,
    });

    if (result.files.length) {
      setFiles((prev) => [...prev, ...result.files]);
    }
  };


  const handleValidate = (fileId: string, options?: { silentToast?: boolean }): Promise<ValidateOutcome> =>
    runValidateWorkflow({
      fileId,
      filesRef,
      silentToast: options?.silentToast,
      editEnabled: EDIT_ENABLED,
      uploadPdf: uploadApi.uploadPdf,
      createImportJob: uploadApi.createImportJob,
      fetchImportJob: uploadApi.fetchImportJob,
      fetchImportErrors: uploadApi.fetchImportErrors,
      parseCsv,
      toValidateProgress,
      sleep: delay,
      confirmDuplicate: (filename, duplicateOf) =>
        window.confirm(
          t('upload.confirm.duplicateFile')
            .replace('{{filename}}', filename)
            .replace('{{duplicateOf}}', duplicateOf)
        ),
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
      showToast,
      t,
    });

  const handleValidateAll = () =>
    runBatchValidation({
      filesRef,
      setIsValidatingAll,
      handleValidate,
      showToast,
      t,
    });

  const handleConvertAll = () =>
    runBatchConversion({
      filesRef,
      setIsConvertingAll,
      handlePdfConvert,
      showToast,
      t,
    });
  const handlePdfConvert = async (fileId: string): Promise<boolean> => {
    const target = files.find((f) => f.id === fileId);
    if (!target) return false;
    if (target.type !== 'PDF') return false;
    if (!target.processId) {
      showMissingPdfConvertProcessToast({ showToast, t });
      return false;
    }

    return await runPdfConvertWorkflow({
      fileId,
      processId: target.processId,
      filesRef,
      triggerPdfConvert: uploadApi.triggerPdfConvert,
      fetchPdfConvertStatus: uploadApi.fetchPdfConvertStatus,
      fetchPdfConvertedCsvOutputs: uploadApi.fetchPdfConvertedCsvOutputs,
      sleep: delay,
      attachPdfConvertJob,
      updatePdfConvertProgress,
      replacePdfWithCsvFiles,
      failPdfConvert,
      beginPdfConvert,
      toPdfConvertProgress,
      showToast,
      t,
    });
  };

  const updateCell = (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => {
    if (!EDIT_ENABLED) return;
    setFiles((prev) => updateCsvCellInFiles(prev, fileId, rowIndex, colIndex, value));
  };

  const handleSaveChanges = async (fileId: string) => {
    if (!EDIT_ENABLED) {
      showCsvEditDisabledToast({ showToast, t });
      return;
    }

    const result = saveCsvChangesInFiles(files, fileId);
    if (result.outcome === "not-found-or-clean") return;
    if (result.outcome === "unsupported-backend") {
      showCsvSaveErrorToast({ showToast, t });
      return;
    }

    setFiles(result.files);
    showCsvChangesAppliedToast({ showToast, t });
  };

  const handleToggleExpand = toggleFileExpanded;

  // 批次匯入所有已驗證的檔案
  const handleBatchImportClick = () => {
    const validatedFiles = files.filter(fileEligibleForBatchImport);
    
    if (validatedFiles.length === 0) {
      const filesWithErrors = files.filter(fileHasBlockingImportErrors);
      const unvalidatedFiles = files.filter(fileIsUploadedButUnvalidated);
      
      showBatchImportUnavailableToast({
        filesWithErrorsCount: filesWithErrors.length,
        unvalidatedFilesCount: unvalidatedFiles.length,
        showToast,
        t,
      });
      return;
    }
    
    // 顯示確認彈窗
    setShowBatchImportConfirm(true);
  };

  const performBatchImport = async () => {
    setShowBatchImportConfirm(false);

    await runBatchImportWorkflow({
      files,
      commitImportJob: uploadApi.commitImportJob,
      fetchImportJob: uploadApi.fetchImportJob,
      sleep: delay,
      beginImport,
      setImportProgress,
      completeImport,
      resetImport,
      toImportProgress,
      schedulePostImportCleanup: (ids) =>
        scheduleBatchPostImportCleanup({
          ids,
          removeImportedFiles,
          showToast,
          t,
        }),
      logError: console.error,
      showToast,
      t,
    });
  };
  const performImport = async () => {
    if (!confirmTargetId) return;
    const id = confirmTargetId;
    setConfirmTargetId(null);

    const target = files.find((f) => f.id === id);
    if (!target || !target.processId) {
      showMissingImportTargetToast({ showToast, t });
      return;
    }


    await runSingleImportWorkflow({
      id,
      target,
      commitImportJob: uploadApi.commitImportJob,
      fetchImportJob: uploadApi.fetchImportJob,
      sleep: delay,
      filesRef,
      beginImport,
      setImportProgress,
      completeImport,
      resetImport,
      removeImportedFiles,
      toImportProgress,
      showToast,
      t,
    });
  };

  const handleRemoveFile = removeFile;

  return (
    <div className="upload-page">
      {/* 通用表單上傳 */}
      {gStations.length > 0 && (
        <div style={{margin:'0 0 16px 0',padding:'12px 16px',background:'#f0f4ff',borderRadius:8,border:'1px solid #c5d3f0',display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <label style={{fontSize:13,fontWeight:500,whiteSpace:'nowrap'}}>通用表單上傳：</label>
          <select value={gStation} onChange={e=>{setGStation(e.target.value);setGResult(null)}}
            style={{fontSize:13,padding:'4px 8px',border:'1px solid #ccc',borderRadius:4}}>
            <option value="">— 使用舊流程 —</option>
            {gStations.map(s=><option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select>
          {gStation && (
            <>
              <input type="file" accept=".csv" style={{fontSize:13}}
                onChange={e=>{ const f=e.target.files?.[0]; if(f) void handleGenericUpload(f); e.target.value='' }} />
              {gUploading && <span style={{fontSize:12,color:'#555'}}>上傳中…</span>}
              {gResult && (
                <span style={{fontSize:12}}>
                  ✓ 匯入 {gResult.imported}/{gResult.total}，略過 {gResult.skipped}
                  {gResult.errors.length>0 && <span style={{color:'#c00'}}> 錯誤 {gResult.errors.length} 筆</span>}
                </span>
              )}
            </>
          )}
        </div>
      )}

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
            <BatchActionBar
              files={files}
              isValidatingAll={isValidatingAll}
              isConvertingAll={isConvertingAll}
              onValidateAll={handleValidateAll}
              onConvertAll={handleConvertAll}
              onBatchImport={handleBatchImportClick}
            />
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
      <BatchImportConfirmModal
        open={showBatchImportConfirm}
        files={files}
        onClose={() => setShowBatchImportConfirm(false)}
        onConfirm={performBatchImport}
      />
    </div>
  );
}



