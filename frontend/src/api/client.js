import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, { status, data, cause } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.cause = cause;
  }
}

// Fired when any authenticated request comes back 401 so the AuthProvider
// can clear React state and let <PublicRoute>/<RequireAuth> navigate to
// /login through React Router instead of hard reloading the page.
export const AUTH_FAILED_EVENT = 'auth:unauthorized';

// Defensively read the token: localStorage round-trips through strings,
// so a previous bug or third-party code may have written the literal
// "null"/"undefined" which would otherwise be sent as
// "Authorization: Bearer null" and trigger an infinite 401 loop.
export function readToken() {
  const raw = localStorage.getItem('token');
  if (!raw) return null;
  const trimmed = String(raw).trim();
  if (!trimmed || trimmed === 'null' || trimmed === 'undefined') {
    localStorage.removeItem('token');
    return null;
  }
  return trimmed;
}

export function clearAuthStorage() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = readToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  } else if (config.headers && config.headers.Authorization) {
    // Never send a stale Authorization header.
    delete config.headers.Authorization;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const data = err.response?.data;
    const message =
      data?.detail ||
      data?.message ||
      err.message ||
      'Request failed';

    if (status === 401) {
      // Always clear stale credentials so retries don't reuse them.
      clearAuthStorage();
      // Notify the AuthProvider; it owns React-side navigation. We do NOT
      // call window.location.href here — a hard reload races with the
      // AuthContext restore effect and produces visible auth loops.
      try {
        window.dispatchEvent(
          new CustomEvent(AUTH_FAILED_EVENT, {
            detail: { url: err.config?.url, status },
          })
        );
      } catch (_) {
        /* no-op: older browsers without CustomEvent */
      }
    }

    return Promise.reject(new ApiError(message, { status, data, cause: err }));
  }
);

export function getApiBaseUrl() {
  return BASE_URL;
}

