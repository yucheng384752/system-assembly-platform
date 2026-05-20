import { useTranslation } from "react-i18next";
import { Modal } from "../../components/common/Modal";
import type { UploadedFile } from "./uploadTypes";
import {
  fileEligibleForBatchImport,
  fileHasBlockingImportErrors,
} from "./uploadEligibility";

interface BatchImportConfirmModalProps {
  open: boolean;
  files: UploadedFile[];
  onClose: () => void;
  onConfirm: () => void;
}

export function BatchImportConfirmModal({
  open,
  files,
  onClose,
  onConfirm,
}: BatchImportConfirmModalProps) {
  const { t } = useTranslation();
  const validFilesWithoutErrors = files.filter(fileEligibleForBatchImport);
  const filesWithErrors = files.filter(fileHasBlockingImportErrors);

  return (
    <Modal
      open={open}
      title={t("upload.batchImport.confirm.title")}
      onClose={onClose}
      onConfirm={onConfirm}
      confirmText={t("upload.batchImport.confirm.confirmText")}
      maxWidth="min(720px, 92vw)"
    >
      <div className="batch-import-confirm">
        <p style={{ marginBottom: "12px" }}>
          {t("upload.batchImport.confirm.summary", { count: validFilesWithoutErrors.length })}
        </p>
        <p style={{ marginBottom: "12px", color: "#dc2626", fontWeight: "bold" }}>
          {t("upload.batchImport.confirm.warning")}
        </p>
        {filesWithErrors.length > 0 && (
          <p
            style={{
              padding: "8px 12px",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "4px",
              color: "#7f1d1d",
              fontSize: "14px",
            }}
          >
            {t("upload.batchImport.confirm.skipNotice", { count: filesWithErrors.length })}
          </p>
        )}
        {validFilesWithoutErrors.length > 0 && (
          <div className="batch-import-confirm__list-wrap">
            <p style={{ fontWeight: "bold", marginBottom: "8px" }}>
              {t("upload.batchImport.confirm.pendingListTitle")}
            </p>
            <ul className="batch-import-confirm__list">
              {validFilesWithoutErrors.map((file) => (
                <li key={file.id} className="batch-import-confirm__item">
                  <div className="batch-import-confirm__row">
                    <span className="batch-import-confirm__type">{file.type}</span>
                    <span className="batch-import-confirm__name" title={file.name}>
                      {file.name}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  );
}
