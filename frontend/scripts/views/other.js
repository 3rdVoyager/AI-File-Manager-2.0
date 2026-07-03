import { api } from '../api.js';

import { showToast, timeAgo } from '../components/ui.js';

import { escapeAttr, escapeHtml, fileNameCell, truncatePath, promptDelete } from './file-actions.js';



function formatBytes(n) {

  let value = Number(n) || 0;

  for (const unit of ['B', 'KB', 'MB', 'GB', 'TB']) {

    if (value < 1024) return unit === 'B' ? `${value} B` : `${value.toFixed(1)} ${unit}`;

    value /= 1024;

  }

  return `${value.toFixed(1)} PB`;

}



function formatModified(ts) {

  return ts ? new Date(ts * 1000).toLocaleDateString() : 'Unknown date';

}



export async function loadProjects() {

  try {

    const data = await api.getProjects();

    const grid = document.getElementById('projects-grid');

    if (!grid) return;

    const projects = data.projects || [];

    if (!projects.length) {

      grid.innerHTML = '<div class="empty-state"><h3>No projects detected</h3><p>Scan folders with code or documents to detect projects.</p></div>';

      return;

    }

    grid.innerHTML = projects.map(p => `

      <div class="project-card">

        <h3>${escapeHtml(p.name)}</h3>

        <p>${escapeHtml(p.file_count)} files · ${escapeHtml(p.size_human)}</p>

      </div>`).join('');

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function loadDuplicates() {

  try {

    const data = await api.getDuplicates();

    const el = document.getElementById('duplicates-list');

    if (!el) return;

    const groups = data.groups || [];

    if (!groups.length) {

      el.innerHTML = '<div class="empty-state"><h3>No duplicates found</h3><p>Scan your files to find duplicate content.</p></div>';

      return;

    }

    el.innerHTML = groups.map((g, idx) => {

      const files = g.files || [];

      const keeper = files[0];

      const wastedBytes = Math.max(0, (g.total_bytes || 0) - (keeper?.size_bytes || 0));

      const hash = (g.content_hash || keeper?.content_hash || '').slice(0, 12);

      return `

      <div class="card duplicate-group" data-group="${idx}">

        <div class="card-header duplicate-header">

          <div>

            <span class="card-title">${escapeHtml(g.file_count)} duplicate files · ${escapeHtml(g.size_human)}</span>

            <div class="text-muted">Potential savings: ${escapeHtml(formatBytes(wastedBytes))} · hash ${escapeHtml(hash || 'unknown')}</div>

          </div>

          <button class="btn btn-sm btn-danger dup-delete-rest" data-group="${idx}">Delete selected in group</button>

        </div>

        <div class="dup-compare-grid">

          ${files.map((f, fi) => `

            <div class="dup-file-card ${fi === 0 ? 'keeper' : ''}">

              <div class="dup-file-top">

                <span class="badge ${fi === 0 ? 'badge-keep' : 'badge-delete'}">${fi === 0 ? 'Keeper' : `Duplicate ${fi + 1}`}</span>

                <label class="dup-delete-check">

                  <input type="checkbox" data-path="${escapeAttr(f.path)}" data-group="${idx}" ${fi === 0 ? '' : 'checked'} aria-label="Select ${escapeAttr(f.filename)}">

                  Delete

                </label>

              </div>

              <div class="dup-file-name">${fileNameCell(f.filename, f.path)}</div>

              <div class="mono dup-file-path" title="${escapeAttr(f.path)}">${escapeHtml(truncatePath(f.path, 72))}</div>

              <div class="dup-file-meta">${escapeHtml(f.size_human)} · ${escapeHtml(formatModified(f.modified_at))}</div>

              <button type="button" class="btn btn-sm btn-secondary" data-open-path="${escapeAttr(f.path)}">Open</button>

            </div>`).join('')}

        </div>

      </div>`;

    }).join('');



    el.querySelectorAll('.dup-delete-rest').forEach(btn => {

      btn.addEventListener('click', () => {

        const idx = btn.dataset.group;

        const paths = [...el.querySelectorAll(`input[data-group="${idx}"][data-path]:checked`)]

          .map(cb => cb.dataset.path);

        promptDelete(paths, () => loadDuplicates());

      });

    });

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function loadReports() {

  try {

    const data = await api.getReports();

    const tbody = document.getElementById('reports-tbody');

    if (!tbody) return;

    const reports = data.reports || [];

    tbody.innerHTML = reports.map(r => `

      <tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.file_count)} files</td><td>${r.saved_at ? new Date(r.saved_at).toLocaleString() : '—'}</td></tr>`

    ).join('') || '<tr><td colspan="3" style="text-align:center;padding:32px;color:var(--text-muted)">No saved reports</td></tr>';

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function saveReport() {

  const name = prompt('Report name:', `report_${Date.now()}`);

  if (!name) return;

  try {

    await api.saveReport(name);

    showToast('Report saved', 'success');

    await loadReports();

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function loadQueries() {

  const el = document.getElementById('queries-list');

  if (!el) return;

  try {

    const data = await api.getHistory();

    const queries = (data.history || []).filter(h => h.event_type === 'query_executed');

    if (!queries.length) {

      el.innerHTML = '<div class="empty-state"><p>Use the AI toggle in All Files search to ask questions about your files.</p></div>';

      return;

    }

    el.innerHTML = `<ul class="activity-list">${queries.map(q => `

      <li class="activity-item">

        <span class="activity-dot"></span>

        <div style="flex:1"><div>${escapeHtml(q.description)}</div></div>

        <span class="activity-time">${escapeHtml(timeAgo(q.created_at))}</span>

      </li>`).join('')}</ul>`;

  } catch (e) {

    showToast(e.message, 'error');

  }

}

