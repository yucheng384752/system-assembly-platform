import { useMemo } from "react";
import { TENANT_STORAGE_KEY } from "../../services/tenant";
import { createUploadApiClient } from "./uploadApiClient";

type TranslationFn = (key: string) => string;

function buildTenantHeaders(): HeadersInit {
  const id = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  return id ? { "X-Tenant-Id": id } : {};
}

export function useUploadApi(t: TranslationFn) {
  return useMemo(
    () => createUploadApiClient({ t, getTenantHeaders: buildTenantHeaders }),
    [t]
  );
}
