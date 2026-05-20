// src/pages/UploadPage.tsx
import { useState, useCallback } from "react";
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
import { buildUploadedCsvFilesFromPdfOutputs, parseCsv } from "./upload/uploadFileUtils";
import { fileEligibleForBatchImport, fileEligibleForConvert, fileEligibleForValidate, fileHasBlockingImportErrors, fileHasImportJob, fileHasValidationErrors, fileIsUploadedButUnvalidated } from "./upload/uploadEligibility";
import { runBatchConversion, runBatchImportWorkflow, runBatchImport, runBatchValidation, runSingleImport, type ValidateOutcome } from "./upload/uploadBatchOrchestrator";
import { runPdfConversion } from "./upload/uploadPdfConversionOrchestrator";
import { showMissingPdfConvertProcessToast, showPdfConvertFailedToast, showPdfConvertFetchingCsvToast, showPdfConvertGotCsvToast, showPdfConvertNoCsvToast, showPdfConvertOutputErrorToast, showPdfConvertStillProcessingToast } from "./upload/uploadPdfConvertToastUtils";
import { commitCsvValidationResult, runCsvValidationJob, runPdfValidation } from "./upload/uploadValidationOrchestrator";
import { showValidationResultToast } from "./upload/uploadValidationToastUtils";
import { showBatchImportUnavailableToast, showImportErrorToast, showMissingImportTargetToast, showSingleImportCompletedToast, showSingleImportStartToast } from "./upload/uploadImportToastUtils";
import { scheduleBatchPostImportCleanup, scheduleSinglePostImportCleanup } from "./upload/uploadImportCleanupUtils";
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


  const handleValidate = async (fileId: string, options?: { silentToast?: boolean }): Promise<ValidateOutcome> => {
    const target = filesRef.current.find((f) => f.id === fileId);
    if (!target) return { outcome: 'failed', message: t('upload.errors.fileNotFound') };

    if (target.type === 'PDF') {
      const result = await runPdfValidation({
        file: target,
        uploadPdf: uploadApi.uploadPdf,
        beginPdfValidation,
        completePdfUpload,
        failPdfValidation,
        fallbackErrorText: t('upload.errors.pdfUploadFailed'),
      });
      showValidationResultToast({
        kind: "pdf",
        silent: options?.silentToast,
        result,
        showToast,
        t,
      });
      return result;
    }

    if (!EDIT_ENABLED && target.hasUnsavedChanges) {
      showValidationResultToast({ kind: "edit-disabled", silent: options?.silentToast, showToast, t });
      return { outcome: 'failed', message: t('upload.editDisabledNotice') };
    }
    
    // 允許重複驗證，特別是有錯誤的檔案
    // 不再阻止重複驗證，讓用戶可以修改後重新驗證

    try {
      const { jobId, lastJob } = await runCsvValidationJob({
        file: target,
        createImportJob: uploadApi.createImportJob,
        parseCsv,
        confirmDuplicate: (duplicateOf) =>
          window.confirm(
            t('upload.confirm.duplicateFile')
              .replace('{{filename}}', target.name)
              .replace('{{duplicateOf}}', duplicateOf)
          ),
        sleep: delay,
        beginCsvValidation,
        setValidationUploadSource,
        setValidationProgress,
        prepareCsvValidationJob,
        updateValidationPoll,
        fetchImportJob: uploadApi.fetchImportJob,
        toValidateProgress,
        validationTimeoutText: t('upload.errors.validationTimeout'),
      });

      return await commitCsvValidationResult({
        fileId,
        target,
        lastJob,
        fetchImportErrors: uploadApi.fetchImportErrors,
        completeValidationFailure,
        completeValidationWithErrors,
        completeValidationPassed,
        showValidationResultToast,
        showToast,
        t,
        silent: options?.silentToast,
      });
      
    } catch (err) {
      console.error('Validation error:', err);
      const errorMessage = err instanceof Error ? err.message : t('upload.errors.validationProcessError');
      showValidationResultToast({ kind: "csv-exception", silent: options?.silentToast, message: errorMessage, showToast, t });
      
      failCsvValidation(fileId);

      return { outcome: 'failed', message: errorMessage };
    }
  };

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

    beginPdfConvert(fileId);

    try {
      const conversionResult = await runPdfConversion({
        processId: target.processId,
        triggerPdfConvert: uploadApi.triggerPdfConvert,
        fetchPdfConvertStatus: uploadApi.fetchPdfConvertStatus,
        sleep: delay,
        attachPdfConvertJob: (jobId) => attachPdfConvertJob(fileId, jobId),
        updatePdfConvertProgress: (status, progress, errorText) =>
          updatePdfConvertProgress(fileId, status, progress, errorText),
        toPdfConvertProgress,
        fallbackErrorText: t('upload.toast.pdfConvertFailed'),
      });

      if (conversionResult.outcome === 'completed') {
        try {
          showPdfConvertFetchingCsvToast({ processId: target.processId, showToast, t });
          const outputsResp = await uploadApi.fetchPdfConvertedCsvOutputs(target.processId);
          const outputs = Array.isArray(outputsResp) ? outputsResp : (outputsResp?.outputs || []);

          const newCsvFiles = await buildUploadedCsvFilesFromPdfOutputs(
            outputs,
            filesRef.current.map((file) => file.name)
          );

          if (newCsvFiles.length) {
            replacePdfWithCsvFiles(fileId, newCsvFiles);
            showPdfConvertGotCsvToast({ processId: target.processId, count: newCsvFiles.length, showToast, t });
          } else {
            showPdfConvertNoCsvToast({ processId: target.processId, showToast, t });
          }
        } catch (e: any) {
          showPdfConvertOutputErrorToast({
            processId: target.processId,
            message: e?.message || t('upload.toast.pdfConvertCreateCsvJobFailed'),
            showToast,
            t,
          });
        }
        return true;
      }

      if (conversionResult.outcome === 'failed') {
        failPdfConvert(fileId, conversionResult.message || t('upload.toast.pdfConvertFailed'));
        showPdfConvertFailedToast({ message: conversionResult.message || t('upload.toast.pdfConvertFailed'), showToast, t });
        return false;
      }

      showPdfConvertStillProcessingToast({ showToast, t });
      return false;
    } catch (e: any) {
      failPdfConvert(fileId, e?.message || t('upload.toast.pdfConvertFailed'));
      showPdfConvertFailedToast({ message: e?.message || t('upload.toast.pdfConvertFailed'), showToast, t });
      return false;
    }
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

    showSingleImportStartToast({ fileName: target.name, showToast, t });

    beginImport([id], 20);

    try {
      await runSingleImport({
        file: target,
        commitImportJob: uploadApi.commitImportJob,
        fetchImportJob: uploadApi.fetchImportJob,
        sleep: delay,
        setImportProgress,
        completeImport,
        toImportProgress,
        t,
      });

      showSingleImportCompletedToast({ fileName: target.name, showToast, t });
      
      // 延遲後根據檔案數量決定行為
      scheduleSinglePostImportCleanup({
        id,
        filesRef,
        removeImportedFiles,
        showToast,
        t,
      });
      
    } catch (err) {
      console.error('Import error:', err);
      const errorMessage = err instanceof Error ? err.message : t('upload.errors.importError');
      showImportErrorToast({ message: errorMessage, showToast, t });
      
      resetImport([id]);
    }
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


