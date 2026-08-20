import { apiGet, apiPost } from './api';

export type KitCapability = {
  capability: string;
  kind: 'api' | 'db';
  kit?: string;
  method?: string;
  path?: string;
};

export type KitContractsResponse = {
  contracts: unknown[];
  capabilities: KitCapability[];
};

export async function listKitCapabilities(): Promise<KitContractsResponse> {
  return apiGet<KitContractsResponse>('/api/kit/contracts');
}

export async function callKitCapability<T = unknown>(
  capability: string,
  payload?: Record<string, unknown>,
): Promise<T> {
  const result = await apiPost<{ data?: T } | T>(`/api/kit/call/${encodeURIComponent(capability)}`, {
    payload: payload ?? {},
  });
  if (result && typeof result === 'object' && 'data' in result) {
    return result.data as T;
  }
  return result as T;
}
