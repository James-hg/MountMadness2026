export const API_BASE = process.env.REACT_APP_API_BASE_URL || '';
let refreshInFlight = null;

function getToken() {
  return localStorage.getItem('access_token');
}

function getRefreshToken() {
  return localStorage.getItem('refresh_token');
}

function saveSession(data) {
  if (data.access_token) localStorage.setItem('access_token', data.access_token);
  if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
  if (data.user) localStorage.setItem('user', JSON.stringify(data.user));
}

function clearSession() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
}

function redirectToLogin() {
  if (typeof window === 'undefined') return;
  if (window.location.pathname !== '/auth/login') {
    window.location.assign('/auth/login');
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function shouldSkipRefresh(path) {
  return path === '/auth/login' || path === '/auth/register' || path === '/auth/refresh';
}

async function parseErrorResponse(res) {
  const err = await res.json().catch(() => ({}));
  return err.detail || `Request failed (${res.status})`;
}

async function doRefresh() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }

  const data = await res.json();
  saveSession(data);
  return data;
}

async function ensureRefreshed() {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }

  return refreshInFlight;
}

async function request(path, options = {}, allowRefresh = true) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...authHeaders(),
    },
  });

  if (res.status === 401 && allowRefresh && !shouldSkipRefresh(path) && getRefreshToken()) {
    try {
      await ensureRefreshed();
    } catch {
      clearSession();
      redirectToLogin();
      throw new Error('Session expired. Please log in again.');
    }

    return request(path, options, false);
  }

  return res;
}

export async function apiPost(path, body) {
  const res = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json();
}

export async function apiUpload(path, formData) {
  const res = await request(path, {
    method: 'POST',
    // Do NOT set Content-Type — browser sets it automatically with multipart boundary
    body: formData,
  });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json();
}

export async function apiPatch(path, body) {
  const res = await request(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json();
}

export async function apiPut(path, body) {
  const res = await request(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json();
}

export async function apiGet(path) {
  const res = await request(path);
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  return res.json();
}

export async function apiDelete(path) {
  const res = await request(path, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error(await parseErrorResponse(res));
  }
  if (res.status === 204) return null;
  return res.json();
}
