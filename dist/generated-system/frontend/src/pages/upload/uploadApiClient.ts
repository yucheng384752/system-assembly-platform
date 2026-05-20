type TranslationFn = (key: string) => string;

interface UploadApiClientOptions {
  t: TranslationFn;
  getTenantHeaders: () => HeadersInit;
}

interface CreateImportJobInput {
  tableCode: string;
  allowDuplicate: boolean;
  file: File;
  filename: string;
}

interface UploadApiError extends Error {
  detail?: unknown;
  response?: unknown;
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const errorData = await response.json().catch(() => ({ detail: fallback }));
  if (typeof errorData.detail === "string") return errorData.detail;
  return errorData.detail?.detail || errorData.message || fallback;
}

async function throwApiError(response: Response, fallback: string): Promise<never> {
  const errorData = await response.json().catch(() => ({ detail: fallback }));
  const message =
    typeof errorData.detail === "string"
      ? errorData.detail
      : errorData.detail?.detail || errorData.message || fallback;
  const error = new Error(message) as UploadApiError;
  error.detail = errorData.detail;
  error.response = errorData;
  throw error;
}

export function createUploadApiClient({ t, getTenantHeaders }: UploadApiClientOptions) {
  return {
    async uploadPdf(file: File, filename: string) {
      const formData = new FormData();
      formData.append("file", file, filename);
      const response = await fetch("/api/upload/pdf", {
        method: "POST",
        headers: getTenantHeaders(),
        body: formData,
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.pdfUploadFailed"));
      }
      return response.json();
    },

    async createImportJob({ tableCode, allowDuplicate, file, filename }: CreateImportJobInput) {
      const formData = new FormData();
      formData.append("table_code", tableCode);
      formData.append("allow_duplicate", allowDuplicate ? "true" : "false");
      formData.append("files", file, filename);
      const response = await fetch("/api/v2/import/jobs", {
        method: "POST",
        headers: getTenantHeaders(),
        body: formData,
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.uploadFailed"));
      }
      return response.json();
    },

    async fetchPdfConvertStatus(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert/status`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchPdfConvertStatusFailed")));
      }
      return response.json();
    },

    async fetchPdfConvertedCsvOutputs(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert/outputs?include_csv_text=1`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchCsvOutputsFailed")));
      }
      return response.json();
    },

    async fetchImportJob(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}`, {
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, t("upload.errors.fetchImportStatusFailed")));
      }
      return response.json();
    },

    async fetchImportErrors(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}/errors?page=1&page_size=200`, {
        headers: getTenantHeaders(),
      });
      return response.ok ? response.json() : [];
    },

    async triggerPdfConvert(processId: string) {
      const response = await fetch(`/api/upload/pdf/${processId}/convert`, {
        method: "POST",
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.triggerPdfConvertFailed"));
      }
      return response.json();
    },

    async commitImportJob(jobId: string) {
      const response = await fetch(`/api/v2/import/jobs/${jobId}/commit`, {
        method: "POST",
        headers: getTenantHeaders(),
      });
      if (!response.ok) {
        await throwApiError(response, t("upload.errors.importFailed"));
      }
      return response.json();
    },
  };
}
