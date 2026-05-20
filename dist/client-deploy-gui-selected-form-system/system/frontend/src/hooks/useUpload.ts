import { useCallback, useMemo, useState } from 'react';
import { FilePreview, FileValidationError, UploadStatus } from '../types/api';

export interface UseUploadOptions {
  maxFileSize?: number; // in bytes
  allowedTypes?: string[];
  onSuccess?: (preview: FilePreview) => void;
  onError?: (error: string) => void;
}

export function useUpload(options: UseUploadOptions = {}) {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [errors, setErrors] = useState<FileValidationError[]>([]);

  const legacyRemovedMessage = useMemo(
    () => 'Legacy upload flow has been removed. Please use the v2 import-jobs workflow (UploadPage).',
    []
  );

  const fail = useCallback(async () => {
    setStatus('error');
    setErrors([
      {
        row: 0,
        column: 'file',
        message: legacyRemovedMessage,
        severity: 'error',
      },
    ]);
    options.onError?.(legacyRemovedMessage);
  }, [legacyRemovedMessage, options]);

  const reset = useCallback(() => {
    setStatus('idle');
    setErrors([]);
  }, []);

  return {
    status,
    progress: 0,
    preview: null as FilePreview | null,
    errors,
    processId: null as string | null,
    uploadFile: fail,
    uploadFiles: fail,
    confirmUpload: fail,
    reset,
  };
}