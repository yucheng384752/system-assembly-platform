/**
 * API 請求工具函數
 */

import { TENANT_STORAGE_KEY } from './tenant';
import { getApiKeyHeaderName, getApiKeyValue } from './auth'
import i18n from '../i18n'

interface RequestOptions {
  url: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  data?: any;
  headers?: Record<string, string>;
}

interface ApiError extends Error {
  status?: number;
  response?: any;
}

const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:8000';

/**
 * 通用 API 請求函數
 */
export async function apiRequest<T = any>(options: RequestOptions): Promise<T> {
  const { url, method, data, headers = {} } = options;
  
  const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
  
  const requestOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    requestOptions.body = JSON.stringify(data);
  }

  try {
    const response = await fetch(fullUrl, requestOptions);
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const error: ApiError = new Error(
        errorData.message || errorData.detail || `HTTP ${response.status}: ${response.statusText}`
      );
      error.status = response.status;
      error.response = errorData;
      throw error;
    }

    // 檢查回應是否為 JSON
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }
    
    // 如果不是 JSON，返回文字內容
    return await response.text() as any;
  } catch (error) {
    if (error instanceof TypeError && error.message.includes('fetch')) {
      // 網路錯誤
      throw new Error(i18n.t('errors.networkConnectionFailed'));
    }
    throw error;
  }
}

/**
 * GET 請求簡化函數
 */
export async function apiGet<T = any>(url: string, headers?: Record<string, string>): Promise<T> {
  const options: RequestOptions = { url, method: 'GET' };
  if (headers) options.headers = headers;
  return apiRequest<T>(options);
}

/**
 * POST 請求簡化函數
 */
export async function apiPost<T = any>(
  url: string, 
  data?: any, 
  headers?: Record<string, string>
): Promise<T> {
  const options: RequestOptions = { url, method: 'POST' };
  if (data !== undefined) options.data = data;
  if (headers) options.headers = headers;
  return apiRequest<T>(options);
}

/**
 * PUT 請求簡化函數
 */
export async function apiPut<T = any>(
  url: string, 
  data?: any, 
  headers?: Record<string, string>
): Promise<T> {
  const options: RequestOptions = { url, method: 'PUT' };
  if (data !== undefined) options.data = data;
  if (headers) options.headers = headers;
  return apiRequest<T>(options);
}

/**
 * DELETE 請求簡化函數
 */
export async function apiDelete<T = any>(url: string, headers?: Record<string, string>): Promise<T> {
  const options: RequestOptions = { url, method: 'DELETE' };
  if (headers) options.headers = headers;
  return apiRequest<T>(options);
}

/**
 * 檔案上傳專用函數
 */
export async function uploadFile<T = any>(
  url: string,
  formData: FormData,
  onProgress?: (progress: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        const progress = Math.round((event.loaded * 100) / event.total);
        onProgress(progress);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          resolve(response);
        } catch (error) {
          resolve(xhr.responseText as any);
        }
      } else {
        try {
          const errorData = JSON.parse(xhr.responseText);
          reject(new Error(errorData.message || errorData.detail || `HTTP ${xhr.status}`));
        } catch (error) {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      }
    });

    xhr.addEventListener('error', () => {
      reject(new Error(i18n.t('errors.uploadNetworkFailed')));
    });

    xhr.addEventListener('abort', () => {
      reject(new Error(i18n.t('errors.uploadCanceled')));
    });

    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    xhr.open('POST', fullUrl);

    // Keep tenant header consistent even for XHR uploads
    try {
      const u = new URL(fullUrl, window.location.href);
      const tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || '';
      if (u.pathname.startsWith('/api') && !u.pathname.startsWith('/api/tenants') && !tenantId) {
        reject(new Error(i18n.t('errors.noTenantSelected')));
        xhr.abort();
        return;
      }
      if (tenantId && u.pathname.startsWith('/api') && !u.pathname.startsWith('/api/tenants')) {
        xhr.setRequestHeader('X-Tenant-Id', tenantId);
      }

      const apiKey = getApiKeyValue()
      if (apiKey && u.pathname.startsWith('/api')) {
        xhr.setRequestHeader(getApiKeyHeaderName(), apiKey)
      }
    } catch {
      // ignore
    }

    xhr.send(formData);
  });
}

export { API_BASE_URL };