import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ProgressBar } from "../../components/common/ProgressBar";
import type { CsvData, UploadedFile } from "./uploadTypes";

const EDIT_ENABLED =
  String((import.meta as any).env?.VITE_ENABLE_CSV_EDIT ?? "true").toLowerCase() === "true";
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

export function UploadedFileCard({
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

