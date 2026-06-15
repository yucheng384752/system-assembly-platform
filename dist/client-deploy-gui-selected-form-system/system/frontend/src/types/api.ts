export interface FilePreview {
  id: string
  name: string
  size: number
  type: string
  status: string
}
export interface FileValidationError {
  row?: number
  column?: string
  message: string
}
export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'