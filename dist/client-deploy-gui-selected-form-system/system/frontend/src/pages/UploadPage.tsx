// src/pages/UploadPage.tsx
import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/common/ToastContext";
import { Modal } from "../components/common/Modal";
import { useUploadApi } from "./upload/useUploadApi";
import { delay } from "./upload/uploadAsyncUtils";
import type { CsvData } from "./upload/uploadTypes";
import { runSaveCsvChangesWorkflow, runUpdateCsvCellWorkflow } from "./upload/uploadCsvEditWorkflow";
import { runAddUploadFilesWorkflow } from "./upload/uploadFileAddWorkflow";
import { parseCsv } from "./upload/uploadFileUtils";
import { fileHasValidationErrors } from "./upload/uploadEligibility";
import { requestBatchImportConfirmation, runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runConfirmedSingleImportWorkflow, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";
import { runPdfConvertWorkflow } from "./upload/uploadPdfConversionOrchestrator";
import { runValidateWorkflow } from "./upload/uploadValidationOrchestrator";
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
  const [availableForms, setAvailableForms] = useState<{ code: string; name: string }[]>([]);
  const { t } = useTranslation();
  const { showToast } = useToast();


  const uploadApi = useUploadApi(t);

  useEffect(() => {
    uploadApi.fetchAvailableForms().then(setAvailableForms).catch(() => {});
  }, [uploadApi]);

  const handleSetFileTableCode = (fileId: string, code: string) => {
    setFiles((prev) => prev.map((f) => f.id === fileId ? { ...f, type: code } : f));
  };





  const handleFiles = (fileList: FileList | null) => {
    runAddUploadFilesWorkflow({
      fileList,
      existingFiles: files,
      setFiles,
      confirmLikelyDuplicate: (file) =>
        window.confirm(t('upload.confirm.likelyDuplicate').replace('{{fileName}}', file.name)),
      showToast,
      t,
      availableCodes: availableForms.map((f) => f.code),
    });
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
  const handlePdfConvert = (fileId: string): Promise<boolean> =>
    runPdfConvertWorkflow({
      fileId,
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
  const updateCell = (
    fileId: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => {
    runUpdateCsvCellWorkflow({
      editEnabled: EDIT_ENABLED,
      fileId,
      rowIndex,
      colIndex,
      value,
      setFiles,
    });
  };


  const handleSaveChanges = async (fileId: string) => {
    runSaveCsvChangesWorkflow({
      editEnabled: EDIT_ENABLED,
      files,
      fileId,
      setFiles,
      showToast,
      t,
    });
  };
  const handleToggleExpand = toggleFileExpanded;

  // 批次匯入所有已驗證的檔案
  const handleBatchImportClick = () => {
    if (requestBatchImportConfirmation({ files, showToast, t })) {
      setShowBatchImportConfirm(true);
    }
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
    const id = confirmTargetId;
    setConfirmTargetId(null);

    await runConfirmedSingleImportWorkflow({
      id,
      files,
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
            <div key={f.id}>
              {f.type === "UNKNOWN" && availableForms.length > 0 && (
                <div style={{ padding: "6px 12px", background: "#fffbeb", border: "1px solid #fbbf24", borderRadius: "6px", marginBottom: "4px", display: "flex", alignItems: "center", gap: "8px", fontSize: "13px" }}>
                  <span style={{ color: "#92400e" }}>未識別表單類型，請選擇：</span>
                  <select
                    value=""
                    onChange={(e) => { if (e.target.value) handleSetFileTableCode(f.id, e.target.value); }}
                    style={{ fontSize: "13px", padding: "2px 6px" }}
                  >
                    <option value="" disabled>請選擇目標表單...</option>
                    {availableForms.map((form) => (
                      <option key={form.code} value={form.code}>{form.name || form.code}</option>
                    ))}
                  </select>
                </div>
              )}
              <UploadedFileCard
                file={f}
                onValidate={() => handleValidate(f.id)}
                onConvertPdf={() => handlePdfConvert(f.id)}
                onSaveChanges={() => handleSaveChanges(f.id)}
                onToggleExpand={() => handleToggleExpand(f.id)}
                onRemove={() => handleRemoveFile(f.id)}
                onImport={(fileId) => setConfirmTargetId(fileId)}
                onCellChange={updateCell}
              />
            </div>
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


