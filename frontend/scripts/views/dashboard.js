import { api } from '../api.js';
import { renderDonut, timeAgo, formatDate } from '../components/ui.js';
import { escapeAttr, escapeHtml } from './file-actions.js';

const COLORS = ['#6366f1', '#3b82f6', '#22c55e', '#f97316', '#eab308', '#ec4899', '#a855f7'];

export async function refreshDashboard() {
  try {
    const [dash, cats, activity, recs, scans] = await Promise.all([
      api.getDashboard(),
      api.getCategories(),
      api.getActivity(),
      api.getRecommendations(),
      api.getScans(),
    ]);
    renderStats(dash);
    renderStorageChart(dash);
    renderCategories(cats);
    renderActivity(activity.activity || []);
    renderRecommendations(recs.recommendations || []);
    renderRecentScans(scans.scans || []);
  } catch (e) {    console.error('Dashboard refresh failed:', e);
  }
}

function renderStats(d) {
  const grid = document.getElementById('stat-grid');
  if (!grid) return;
  if (d.empty) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <h3>No files scanned yet</h3>
        <p>Click <strong>+ New Scan</strong> to analyze a folder on your computer.</p>
      </div>`;
    return;
  }
  grid.innerHTML = `
    <div class="stat-card"><div class="stat-icon purple"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg></div>
      <div><div class="stat-value">${d.files_analyzed.toLocaleString()}</div><div class="stat-label">Files Analyzed</div><div class="stat-sub">${d.files_delta >= 0 ? '+' : ''}${d.files_delta} since last scan</div></div></div>
    <div class="stat-card"><div class="stat-icon blue"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg></div>
      <div><div class="stat-value">${d.rename_suggestions || 0}</div><div class="stat-label">Rename Suggestions</div><div class="stat-sub">from AI scans</div></div></div>
    <div class="stat-card"><div class="stat-icon orange"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V4a2 2 0 0 1 2-2h12"/></svg></div>
      <div><div class="stat-value">${d.duplicate_files}</div><div class="stat-label">Duplicate Files</div><div class="stat-sub">${d.duplicate_human || '0 B'}</div></div></div>
    <div class="stat-card"><div class="stat-icon green"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></div>
      <div><div class="stat-value">${d.trash_candidates}</div><div class="stat-label">Trash Candidates</div><div class="stat-sub">${d.trash_human || '0 B'}</div></div></div>
    <div class="stat-card"><div class="stat-icon pink"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
      <div><div class="stat-value">${d.avg_importance}/10</div><div class="stat-label">Average Importance</div><div class="stat-sub">${d.importance_label}</div></div></div>`;
}

function renderStorageChart(d) {
  const s = d.storage || {};
  renderDonut('sidebar-donut', [
    { value: s.used_bytes || 1, color: '#3b82f6' },
    { value: s.recommended_delete_bytes || 0, color: '#22c55e' },
    { value: s.duplicate_bytes || 0, color: '#f97316' },
    { value: s.other_bytes || 0, color: '#eab308' },
  ], { line1: 'Total', line2: s.total_human || '0 B' });

  const legend = document.getElementById('storage-legend');
  if (!legend) return;
  const total = s.total_bytes || 1;
  const pct = (v) => Math.round((v / total) * 100);
  legend.innerHTML = `
    <div class="legend-item"><span class="legend-dot" style="background:#3b82f6"></span>Used: ${s.used_human} (${pct(s.used_bytes)}%)</div>
    <div class="legend-item"><span class="legend-dot" style="background:#22c55e"></span>Recommended to Delete: ${s.recommended_delete_human} (${pct(s.recommended_delete_bytes)}%)</div>
    <div class="legend-item"><span class="legend-dot" style="background:#f97316"></span>Duplicates: ${s.duplicate_human} (${pct(s.duplicate_bytes)}%)</div>
    <div class="legend-item"><span class="legend-dot" style="background:#eab308"></span>Other: ${s.other_human} (${pct(s.other_bytes)}%)</div>`;
}

function renderCategories(data) {
  const cats = data.categories || [];
  renderDonut('category-donut', cats.map((c, i) => ({
    value: c.size_bytes || 1, color: COLORS[i % COLORS.length],
  })), { line1: 'By size', line2: `${cats.length} types` });

  const tbody = document.getElementById('category-tbody');
  if (!tbody) return;
  if (!cats.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Scan a folder to see categories</td></tr>';
    return;
  }
  tbody.innerHTML = cats.map((c, i) => `
    <tr>
      <td><span class="legend-dot" style="background:${COLORS[i % COLORS.length]};display:inline-block"></span> ${escapeHtml(c.category)}</td>
      <td>${c.files.toLocaleString()}</td>
      <td>${escapeHtml(c.size_human)}</td>
      <td>${c.percent_size}%<div class="cat-bar"><div class="cat-bar-fill" style="width:${c.percent_size}%"></div></div></td>
    </tr>`).join('');
}

function renderActivity(items) {
  const el = document.getElementById('activity-list');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<li class="empty-state" style="padding:24px">No activity yet</li>';
    return;
  }
  el.innerHTML = items.map(a => `
    <li class="activity-item">
      <span class="activity-dot"></span>
      <div style="flex:1"><div>${escapeHtml(a.description)}</div></div>
      <span class="activity-time">${escapeHtml(timeAgo(a.created_at))}</span>
    </li>`).join('');
}

function renderRecommendations(recs) {
  const el = document.getElementById('recommendations-list');
  if (!el) return;
  if (!recs.length) {
    el.innerHTML = '<div class="empty-state" style="padding:24px">Scan files to get recommendations</div>';
    return;
  }
  el.innerHTML = recs.map(r => `
    <div class="rec-card">
      <h4>${escapeHtml(r.title)}</h4>
      <p>${escapeHtml(r.description)}</p>
    </div>`).join('');
}

function renderRecentScans(scans) {
  const tbody = document.getElementById('scans-tbody');
  if (!tbody) return;
  const top = scans.slice(0, 4);
  if (!top.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">No scans yet</td></tr>';
    return;
  }
  tbody.innerHTML = top.map(s => `
    <tr>
      <td>${escapeHtml(s.name)}</td>
      <td class="mono">${escapeHtml(s.root_path)}</td>
      <td>${(s.files_found || 0).toLocaleString()}</td>
      <td>${escapeHtml(s.size_human || '—')}</td>
      <td>${escapeHtml(formatDate(s.completed_at || s.started_at))}</td>
      <td>
        <button class="btn-icon btn-sm" title="Browse analyzed files" data-view="files" aria-label="Browse analyzed files">View</button>
        <button class="btn btn-sm btn-secondary" type="button" data-scan-path="${escapeAttr(s.root_path)}">Scan Again</button>
      </td>
    </tr>`).join('');
}
