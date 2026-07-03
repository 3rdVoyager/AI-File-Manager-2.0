const API_BASE = '/api';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };
  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body);
  }
  const res = await fetch(url, config);
  let data;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg).join(', ')
      : data?.message || (res.status === 404 ? 'Not Found' : res.status === 500 ? 'Server error — check the terminal for details' : 'Something went wrong. Please try again.');
    throw new Error(msg);
  }
  return data;
}

export const api = {
  getStatus: () => request('/status'),
  getDashboard: () => request('/dashboard'),
  getCategories: () => request('/dashboard/categories'),
  getActivity: () => request('/dashboard/activity'),
  getRecommendations: () => request('/dashboard/recommendations'),
  getScans: () => request('/scans'),
  getSettings: () => request('/settings'),
  saveSettings: (body) => request('/settings', { method: 'POST', body }),
  testSettings: (body) => request('/settings/test', { method: 'POST', body }),
  browse: (path = '') => request(`/browse?path=${encodeURIComponent(path)}`),
  quickPicks: () => request('/browse/quick-picks'),
  scanEstimate: (path) => request(`/scan/estimate?path=${encodeURIComponent(path)}`),
  startScan: (path, name) => request('/scan', { method: 'POST', body: { path, name } }),
  getScanStatus: (id) => request(`/scan/${id}`),
  cancelScan: (id) => request(`/scan/${id}/cancel`, { method: 'POST' }),
  getFiles: (params) => {
    const q = new URLSearchParams(params).toString();
    return request(`/files?${q}`);
  },
  getProjects: () => request('/projects'),
  getDuplicates: () => request('/duplicates'),
  open: (path) => request('/open', { method: 'POST', body: { path } }),
  query: (q) => request('/query', { method: 'POST', body: { query: q } }),
  deletePreview: (paths) => request('/delete-preview', { method: 'POST', body: { paths } }),
  delete: (paths, dryRun = false) => request('/delete', { method: 'POST', body: { paths, dry_run: dryRun } }),
  getReports: () => request('/reports'),
  saveReport: (name) => request('/reports', { method: 'POST', body: { name } }),
  getHistory: () => request('/history'),
  shutdown: () => request('/shutdown', { method: 'POST' }),
  resetAll: (confirm) => request('/reset', { method: 'POST', body: { confirm } }),
};
