export const API_BASE_URL = "http://127.0.0.1:8000";
export const API_V1 = `${API_BASE_URL}/api/v1`;

const TOKEN_KEY = "app_access_token";
const USER_KEY = "app_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getCurrentUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function loginRequest(username, password) {
  const res = await fetch(`${API_V1}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Login gagal");
  }
  return data;
}

export async function apiFetch(path, options = {}, onUnauthorized = null) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_V1}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearSession();
    if (typeof onUnauthorized === "function") {
      onUnauthorized();
    }
    throw new Error("Sesi berakhir, silakan login ulang.");
  }
  return res;
}
