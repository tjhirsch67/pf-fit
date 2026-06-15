// API + token layer. Bearer token lives in localStorage (no cookies → no cross-site issues).
(function () {
  const BASE = window.PF_CONFIG.API_BASE;
  const TOKEN_KEY = "pf_token";

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
  function clearToken() { localStorage.removeItem(TOKEN_KEY); }
  function isAuthed() { return !!getToken(); }

  async function api(path, { method = "GET", body = null, auth = true } = {}) {
    const headers = {};
    if (body !== null) headers["Content-Type"] = "application/json";
    if (auth && getToken()) headers["Authorization"] = "Bearer " + getToken();

    let resp;
    try {
      resp = await fetch(BASE + path, {
        method,
        headers,
        body: body !== null ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new ApiError(0, "Network error — check your connection and try again.");
    }

    if (resp.status === 401) {
      clearToken();
      if (location.hash !== "#/login") location.hash = "#/login";
      throw new ApiError(401, "Please sign in again.");
    }

    let data = null;
    const text = await resp.text();
    if (text) { try { data = JSON.parse(text); } catch { data = text; } }

    if (!resp.ok) {
      const detail = data && data.detail ? data.detail : "Something went wrong.";
      throw new ApiError(resp.status, typeof detail === "string" ? detail : "Validation error.", data);
    }
    return data;
  }

  class ApiError extends Error {
    constructor(status, message, data) { super(message); this.status = status; this.data = data; }
  }

  window.API = { api, getToken, setToken, clearToken, isAuthed, ApiError, BASE };
})();
