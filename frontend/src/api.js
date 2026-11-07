// All calls to the PathoSearch backend.
// In development, Vite forwards /api to http://127.0.0.1:8000 (see vite.config.js).
// If the backend lives somewhere else, set VITE_API_URL in frontend/.env.
const BASE = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');

export const apiUrl = (path) => `${BASE}${path}`;

// Admin key for uploading, re-indexing and deleting on a public deployment.
const KEY_NAME = 'pathosearch_admin_key';
export const getAdminKey = () => {
  try {
    return localStorage.getItem(KEY_NAME) || '';
  } catch {
    return '';
  }
};
export const setAdminKey = (key) => {
  try {
    if (key) localStorage.setItem(KEY_NAME, key);
    else localStorage.removeItem(KEY_NAME);
  } catch {
    /* storage unavailable: key lives only in memory for this page */
  }
};
const adminHeaders = () => (getAdminKey() ? { 'X-Admin-Token': getAdminKey() } : {});

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(apiUrl(path), options);
  } catch {
    throw new Error("Can't reach the backend. It may be starting up; try again in a minute.");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && data.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join(', ')
      : detail || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

export const api = {
  health: () => request('/api/health'),

  listSlides: () => request('/api/slides'),
  getSlide: (id) => request(`/api/slides/${id}`),
  slidePatches: (id) => request(`/api/slides/${id}/patches`),
  deleteSlide: (id) => request(`/api/slides/${id}`, { method: 'DELETE', headers: adminHeaders() }),
  reindexSlide: (id) =>
    request(`/api/slides/${id}/reindex`, { method: 'POST', body: new FormData(), headers: adminHeaders() }),

  searchText: (q, topK = 12) =>
    request(`/api/search/text?q=${encodeURIComponent(q)}&top_k=${topK}`),

  searchImage: (file, topK = 12) => {
    const form = new FormData();
    form.append('file', file);
    form.append('top_k', String(topK));
    return request('/api/search/image', { method: 'POST', body: form });
  },

  searchSimilar: (slideId, x, y, topK = 12) =>
    request(`/api/search/similar?slide_id=${slideId}&x=${x}&y=${y}&top_k=${topK}`),

  patchUrl: (slideId, x, y, size) =>
    apiUrl(`/api/slides/${slideId}/patch?x=${x}&y=${y}${size ? `&size=${size}` : ''}`),

  // Uses XMLHttpRequest because fetch can't report upload progress.
  uploadSlide: (file, maxPatches, onProgress) =>
    new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      form.append('max_patches', String(maxPatches));
      const xhr = new XMLHttpRequest();
      xhr.open('POST', apiUrl('/api/slides'));
      const key = getAdminKey();
      if (key) xhr.setRequestHeader('X-Admin-Token', key);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = null;
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error((data && data.detail) || `Upload failed (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error("Can't reach the backend. It may be starting up; try again in a minute."));
      xhr.send(form);
    }),
};

// ---------- formatting helpers ----------
export const fmtInt = (n) => (n == null ? '–' : Number(n).toLocaleString());

export const fmtBytes = (n) => {
  if (!n) return '–';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
};

export const fmtDate = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : '–');

// Physical size of one patch, e.g. "128 µm"
export const patchMicrons = (slide) =>
  slide && slide.mpp && slide.patch_size0 ? `${Math.round(slide.mpp * slide.patch_size0)} µm` : null;
