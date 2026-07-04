import { api } from '../api.js';

import { formatDate, showToast } from '../components/ui.js';

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

export async function loadDuplicates() {

  try {

    const data = await api.getDuplicates();

    const el = document.getElementById('duplicates-list');

    const summary = document.getElementById('duplicates-summary');

    if (!el) return;

    const groups = data.groups || [];

    if (summary) summary.textContent = `${groups.length.toLocaleString()} duplicate group(s) found`;

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



export async function loadScans() {

  try {

    const data = await api.getScans();

    const tbody = document.getElementById('recent-scans-tbody');

    if (!tbody) return;

    const scans = data.scans || [];

    let scansHtml = '';

    if (scans.length) {
      scansHtml = scans.map(s => `
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
        </tr>`
      ).join('');
    } else {
      scansHtml = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted)">No scans yet</td></tr>';
    }
    tbody.innerHTML = scansHtml;

  } catch (e) {

    showToast(e.message, 'error');

  }

}
