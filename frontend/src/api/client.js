const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getTokens() {
  return {
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  };
}

function setTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  if (refresh) localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

let refreshPromise = null;

async function tryRefresh() {
  const { refresh } = getTokens();
  if (!refresh) throw new Error("No refresh token");

  // Prevent multiple concurrent refresh calls from stacking.
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("Refresh failed");
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        return data.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

/**
 * Core request helper. Automatically attaches the bearer token, retries once
 * after a silent token refresh on 401, and throws a normalized ApiError with
 * the backend's error code/message on failure so UI code can show it directly.
 */
export async function apiRequest(path, { method = "GET", body, headers = {}, idempotencyKey, skipAuth } = {}) {
  const { access } = getTokens();
  const doFetch = async (token) => {
    const finalHeaders = { "Content-Type": "application/json", ...headers };
    if (token && !skipAuth) finalHeaders["Authorization"] = `Bearer ${token}`;
    if (idempotencyKey) finalHeaders["Idempotency-Key"] = idempotencyKey;

    return fetch(`${API_URL}${path}`, {
      method,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch(access);

  if (res.status === 401 && !skipAuth && getTokens().refresh) {
    try {
      const newAccess = await tryRefresh();
      res = await doFetch(newAccess);
    } catch {
      clearTokens();
      window.location.href = "/login";
      throw new ApiError("Session expired. Please log in again.", 401, "SESSION_EXPIRED");
    }
  }

  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    // no body
  }

  if (!res.ok) {
    const message = data?.error?.message || data?.detail || "Something went wrong.";
    const code = data?.error?.code || "UNKNOWN_ERROR";
    throw new ApiError(message, res.status, code, data?.error?.details);
  }

  return data;
}

export class ApiError extends Error {
  constructor(message, status, code, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const api = {
  register: (payload) => apiRequest("/api/auth/register", { method: "POST", body: payload, skipAuth: true }),
  login: (payload) => apiRequest("/api/auth/login", { method: "POST", body: payload, skipAuth: true }),
  logout: () => {
    const { refresh } = getTokens();
    return apiRequest("/api/auth/logout", { method: "POST", body: { refresh_token: refresh } }).catch(() => {});
  },
  me: () => apiRequest("/api/auth/me"),

  listWallets: () => apiRequest("/api/wallet/"),
  createWallet: (currency) => apiRequest("/api/wallet/", { method: "POST", body: { currency } }),
  getWallet: (id) => apiRequest(`/api/wallet/${id}`),
  deposit: (wallet_id, amount, idempotencyKey) =>
    apiRequest("/api/wallet/deposit/", { method: "POST", body: { wallet_id, amount }, idempotencyKey }),
  withdraw: (wallet_id, amount, idempotencyKey) =>
    apiRequest("/api/wallet/withdraw/", { method: "POST", body: { wallet_id, amount }, idempotencyKey }),
  transfer: (sender_wallet_id, recipient_wallet_id, amount, description, idempotencyKey) =>
    apiRequest("/api/wallet/transfer/", {
      method: "POST",
      body: { sender_wallet_id, recipient_wallet_id, amount, description },
      idempotencyKey,
    }),

  listTransactions: (params = {}) => {
    const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v != null)));
    return apiRequest(`/api/wallet/transactions/?${qs.toString()}`);
  },

  // Admin
  adminListUsers: (page = 1) => apiRequest(`/api/admin/users?page=${page}&page_size=50`),
  adminListWallets: (page = 1) => apiRequest(`/api/admin/wallets?page=${page}&page_size=50`),
  adminFreezeWallet: (id, reason) =>
    apiRequest(`/api/admin/wallets/${id}/freeze/`, { method: "POST", body: { reason } }),
  adminUnfreezeWallet: (id, reason) =>
    apiRequest(`/api/admin/wallets/${id}/unfreeze/`, { method: "POST", body: { reason } }),
  adminAdjustBalance: (id, amount, reason) =>
    apiRequest(`/api/admin/wallets/${id}/adjust-balance/`, { method: "POST", body: { amount, reason } }),
  adminListTransactions: (params = {}) => {
    const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v != null)));
    return apiRequest(`/api/admin/transactions?${qs.toString()}`);
  },
};

export { getTokens, setTokens, clearTokens };
