import { useState } from "react";
import { useTranslation } from "react-i18next";

interface FileDropAreaProps {
  onFiles: (files: FileList | null) => void;
}

export function FileDropArea({ onFiles }: FileDropAreaProps) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(false);
    onFiles(event.dataTransfer.files);
  };

  const handleDragOver: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(true);
  };

  const handleDragLeave: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setDragging(false);
  };

  const handleChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    onFiles(event.target.files);
    event.target.value = "";
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
        <div className="upload-drop-icon">漎?/div>
        <p className="upload-drop-main-text">{t("upload.dropMain")}</p>
        <p className="upload-drop-sub-text">{t("upload.dropSub")}</p>
        <label className="upload-drop-button">
          {t("upload.chooseFile")}
          <input type="file" accept=".csv,.pdf" multiple onChange={handleChange} />
        </label>
      </div>
    </div>
  );
}
