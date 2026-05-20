import { useTranslation } from "react-i18next";
import type { UploadedFile } from "./uploadTypes";
import {
  fileEligibleForConvert,
  fileEligibleForValidate,
  fileHasImportJob,
  fileHasValidationErrors,
} from "./uploadEligibility";

interface BatchActionBarProps {
  files: UploadedFile[];
  isValidatingAll: boolean;
  isConvertingAll: boolean;
  onValidateAll: () => void;
  onConvertAll: () => void;
  onBatchImport: () => void;
}

export function BatchActionBar({
  files,
  isValidatingAll,
  isConvertingAll,
  onValidateAll,
  onConvertAll,
  onBatchImport,
}: BatchActionBarProps) {
  const { t } = useTranslation();
  const eligibleCount = files.filter(fileEligibleForValidate).length;
  const anyBusy = files.some((file) => file.status === "validating" || file.status === "importing");
  const validateDisabled = isValidatingAll || anyBusy || eligibleCount === 0;

  let validateTitle = "";
  if (validateDisabled) {
    validateTitle = eligibleCount === 0
      ? t("upload.batchValidate.title.noEligible")
      : t("upload.batchValidate.title.busy");
  } else {
    validateTitle = t("upload.batchValidate.title.ready", { count: eligibleCount });
  }

  const convertEligibleCount = files.filter(fileEligibleForConvert).length;
  const anyConverting = files.some(
    (file) =>
      file.pdfConvertStatus === "queued" ||
      file.pdfConvertStatus === "uploading" ||
      file.pdfConvertStatus === "processing"
  );
  const convertDisabled = isConvertingAll || anyConverting || convertEligibleCount === 0;

  const validatedFiles = files.filter(fileHasImportJob);
  const validFilesWithoutErrors = validatedFiles.filter((file) => !fileHasValidationErrors(file));
  const filesWithErrors = validatedFiles.filter(fileHasValidationErrors);
  const importDisabled = validFilesWithoutErrors.length === 0;

  let importTitle = "";
  if (importDisabled) {
    importTitle = filesWithErrors.length > 0
      ? t("upload.batchImport.title.hasErrors", { count: filesWithErrors.length })
      : t("upload.batchImport.title.noValidated");
  } else {
    importTitle = t("upload.batchImport.title.ready", { validCount: validFilesWithoutErrors.length });
    if (filesWithErrors.length > 0) {
      importTitle += ` ${t("upload.batchImport.title.skipErrorsSuffix", { errorCount: filesWithErrors.length })}`;
    }
  }

  return (
    <div className="batch-actions">
      <button
        className={`btn-secondary ${validateDisabled ? "btn-secondary--disabled" : ""}`}
        onClick={onValidateAll}
        disabled={validateDisabled}
        title={validateTitle}
        style={{ marginRight: "10px" }}
      >
        {isValidatingAll
          ? t("upload.batchValidate.buttonLabelBusy")
          : t("upload.batchValidate.buttonLabel", { count: eligibleCount })}
      </button>

      {(convertEligibleCount > 0 || isConvertingAll) && (
        <button
          className={`btn-secondary ${convertDisabled ? "btn-secondary--disabled" : ""}`}
          onClick={onConvertAll}
          disabled={convertDisabled}
          title={
            convertDisabled
              ? t("upload.batchConvert.title.busy")
              : t("upload.batchConvert.title.ready", { count: convertEligibleCount })
          }
          style={{ marginRight: "10px" }}
        >
          {isConvertingAll
            ? t("upload.batchConvert.buttonLabelBusy")
            : t("upload.batchConvert.buttonLabel", { count: convertEligibleCount })}
        </button>
      )}

      <button
        className={`btn-primary batch-import-btn ${importDisabled ? "btn-primary--disabled" : ""}`}
        onClick={onBatchImport}
        disabled={importDisabled}
        title={importTitle}
      >
        {t("upload.batchImport.buttonLabel", { count: validFilesWithoutErrors.length })}
        {filesWithErrors.length > 0 && (
          <span style={{ color: "#f59e0b", marginLeft: "8px" }}>
            {t("upload.batchImport.errorBadge", { count: filesWithErrors.length })}
          </span>
        )}
      </button>
    </div>
  );
}
