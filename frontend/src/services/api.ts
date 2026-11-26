const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "/api/v1";

const SESSION_KEY = "td_tab_session";
export const AUTH_SESSION_CLEARED = "ticketdesk:session-cleared";

export interface AuthSession {
  id: string;
  subject: string;
  role: string;
  accountIdentity: string;
  accessToken: string;
  refreshToken: string;
}

export function tokenIdentity(token: string): { subject: string; role: string; accountIdentity: string } {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(part));
    if (!payload.sub || !payload.role || !payload.sid) throw new Error("Missing identity");
    return { subject: String(payload.sub), role: String(payload.role), accountIdentity: String(payload.sid) };
  } catch {
    throw new ApiError("Invalid session identity. Please sign in again.", 401, "INVALID_SESSION");
  }
}

export function getAuthSession(): AuthSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) as AuthSession : null;
  } catch { return null; }
}

export function getAccessToken(): string | null { return getAuthSession()?.accessToken || null; }
export function getRefreshToken(): string | null { return getAuthSession()?.refreshToken || null; }

function createSessionId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, b =>
    b.toString(16).padStart(2, "0")
  ).join("");

  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20)
  ].join("-");
}

export function setAuthTokens(accessToken: string, refreshToken: string): void {
  const identity = tokenIdentity(accessToken);
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    id: createSessionId(),
    ...identity,
    accessToken,
    refreshToken
  }));
  localStorage.removeItem("td_access_token");
  localStorage.removeItem("td_refresh_token");
}

export function clearAuthTokens(expectedId?: string): void {
  if (expectedId && getAuthSession()?.id !== expectedId) return;
  sessionStorage.removeItem(SESSION_KEY);
  localStorage.removeItem("td_access_token");
  localStorage.removeItem("td_refresh_token");
  window.dispatchEvent(new Event(AUTH_SESSION_CLEARED));
}

const refreshes = new Map<string, Promise<boolean>>();
const sameSession = (session: AuthSession) => getAuthSession()?.id === session.id;

async function tryRefreshTokens(session: AuthSession): Promise<boolean> {
  const running = refreshes.get(session.id);
  if (running) return running;
  const work = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: session.refreshToken }),
      });
      if (!sameSession(session)) return false;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) clearAuthTokens(session.id);
        return false;
      }
      const data = await response.json();
      if (!sameSession(session)) return false;
      const identity = tokenIdentity(data.access_token);
      if (identity.subject !== session.subject || identity.role !== session.role || identity.accountIdentity !== session.accountIdentity || String(data.user?.id) !== session.subject) {
        clearAuthTokens(session.id);
        throw new ApiError("Session identity changed. Please sign in explicitly.", 401, "SESSION_IDENTITY_MISMATCH");
      }
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...session, accessToken: data.access_token, refreshToken: data.refresh_token }));
      return true;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      return false; // A transient network failure must not overwrite/logout another session.
    }
  })();
  refreshes.set(session.id, work);
  try { return await work; } finally { refreshes.delete(session.id); }
}

export async function revokeAuthSession(session: AuthSession): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });
}

async function authorizedFetch(endpoint: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const session = getAuthSession();
  const isLogin = endpoint === "/auth/login";
  const headers = new Headers(options.headers || {});
  if (session && !isLogin) headers.set("Authorization", `Bearer ${session.accessToken}`);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, headers });
  if (!isLogin && session && !sameSession(session)) throw new ApiError("The session changed while this request was running.", 409, "SESSION_CHANGED");
  if (response.status === 401 && retry && session && !isLogin) {
    // A parallel request may already have refreshed the same session.
    const refreshed = getAccessToken() !== session.accessToken || await tryRefreshTokens(session);
    if (refreshed && sameSession(session)) return authorizedFetch(endpoint, options, false);
  }
  return response;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(message: string, status: number, code = "API_ERROR", details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const sessionId = getAuthSession()?.id;
  const response = await authorizedFetch(endpoint, options, retry);

  if (!response.ok) {
    let errMsg = `Request failed (${response.status})`;
    let errCode = `HTTP_${response.status}`;
    let errDetails: unknown = null;

    try {
      const errBody = await response.json();
      if (errBody?.error) {
        errMsg = errBody.error.message || errMsg;
        errCode = errBody.error.code || errCode;
        errDetails = errBody.error.details;
      } else if (errBody?.detail) {
        errMsg = typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail);
      }
    } catch {
      // Non-JSON error response
    }
    throw new ApiError(errMsg, response.status, errCode, errDetails);
  }

  const data = await response.json() as T;
  if (endpoint !== "/auth/login" && sessionId && getAuthSession()?.id !== sessionId) {
    throw new ApiError("The session changed while this response was being read.", 409, "SESSION_CHANGED");
  }
  return data;
}

export async function downloadAuthorizedBlob(endpoint: string, filename: string): Promise<void> {
  const response = await authorizedFetch(endpoint);
  if (!response.ok) {
    throw new ApiError("Failed to download file", response.status);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
