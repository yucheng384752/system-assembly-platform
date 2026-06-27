import { useMemo } from "react";
import { TENANT_STORAGE_KEY } from "../../services/tenant";
import { getApiKeyValue, getApiKeyHeaderName } from "../../services/auth";
import { createUploadApiClient } from "./uploadApiClient";

type TranslationFn = (key: string) => string;

function buildTenantHeaders(): HeadersInit {
  const tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  const apiKey = getApiKeyValue();
  const headers: Record<string, string> = {};
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  if (apiKey) headers[getApiKeyHeaderName()] = apiKey;
  return headers;
}

export function useUploadApi(t: TranslationFn) {
  return useMemo(
    () => createUploadApiClient({ t, getTenantHeaders: buildTenantHeaders }),
    [t]
  );
}
