import { api } from '../api.js';

import { showToast, openModal, closeModal } from '../components/ui.js';

import { state } from '../state.js';

import { refreshDashboard } from './dashboard.js';

import {
  escapeAttr, escapeHtml, fileNameCell, getSelectedPaths, promptDelete, updateDeleteButton, wireRowCheckboxes,
} from './file-actions.js';



let browsePath = '';
let browseValid = false;
let selectionContext = 'scan'; // 'scan' or 'empty-folders'

function updateSelectButton() {
  const btn = document.getElementById('select-folder-btn');
  if (btn) {
    btn.disabled = !browseValid;
    btn.title = browseValid ? '' : 'Navigate to a folder first';
    if (selectionContext === 'empty-folders') {
      btn.textContent = 'Scan This Folder for Empty Folders';
    } else {
      btn.textContent = 'Select This Folder';
    }
  }
}



function updateEstimate(text) {

  const el = document.getElementById('folder-estimate');

  if (el) el.textContent = text || '';

}

function scanTierLabel(tier) {
  const labels = {
    full: 'Detailed analysis',
    standard: 'Balanced analysis',
    light: 'Fast scan',
    minimal: 'Fast scan with limited AI',
  };
  return labels[tier] || 'Standard analysis';
}

function formatWait(seconds) {
  const value = Math.max(1, Number(seconds) || 1);
  return value >= 60 ? 'about 1 minute' : `about ${value}s`;
}



export async function openFolderPicker(context = 'scan') {

  browsePath = '';

  browseValid = false;

  selectionContext = context;

  updateSelectButton();

  updateEstimate('');

  openModal('folder-modal');

  await loadQuickPicks();

  await loadBrowse();

}



async function loadQuickPicks() {

  const el = document.getElementById('folder-quick-picks');

  if (!el) return;

  try {

    const data = await api.quickPicks();

    const picks = data.picks || [];

    if (!picks.length) {

      el.innerHTML = '';

      return;

    }

    el.innerHTML = picks.map(p =>

      `<button type="button" class="btn btn-sm btn-secondary quick-pick" data-path="${escapeAttr(p.path)}">${escapeHtml(p.label)}</button>`

    ).join('');

    el.querySelectorAll('.quick-pick').forEach(btn => {

      btn.addEventListener('click', () => loadBrowse(btn.dataset.path));

    });

  } catch {

    el.innerHTML = '';

  }

}



export async function loadBrowse(path = '') {

  browsePath = path;

  browseValid = Boolean(path);

  updateSelectButton();

  updateEstimate('');

  try {

    const data = await api.browse(path);

    const el = document.getElementById('folder-list');

    const breadcrumb = document.getElementById('folder-breadcrumb');

    if (breadcrumb) breadcrumb.textContent = data.current || 'Select a drive or folder';

    if (!el) return;

    let html = '';

    if (data.parent) {

      html += `<div class="folder-item" data-path="${escapeAttr(data.parent)}"><span aria-hidden="true">↑</span> Parent folder</div>`;

    }

    for (const entry of data.entries) {

      if (entry.is_dir) {

        html += `<div class="folder-item" data-path="${escapeAttr(entry.path)}"><span aria-hidden="true">▸</span> ${escapeHtml(entry.name)}</div>`;

      }

    }

    el.innerHTML = html || '<div style="padding:16px;color:var(--text-muted)">No subfolders</div>';

    el.querySelectorAll('.folder-item').forEach(item => {

      item.addEventListener('click', () => loadBrowse(item.dataset.path));

    });



    if (browseValid) {

      try {

        const est = await api.scanEstimate(path);

        updateEstimate(

          `~${est.file_count.toLocaleString()} files · ~${est.estimated_ai_calls.toLocaleString()} AI calls · ${scanTierLabel(est.tier)}`

        );

      } catch {

        /* estimate optional */

      }

    }

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function selectFolder() {

  if (!browseValid || !browsePath) {

    showToast('Navigate to a folder first', 'error');

    return;

  }

  closeModal('folder-modal');

  if (selectionContext === 'empty-folders') {
    const { loadEmptyFolders } = await import('./files.js');
    await loadEmptyFolders(browsePath);
  } else {
    await startScan(browsePath, false);
  }

}



export async function startScan(path, runInBackground = false) {

  try {

    state.scanInBackground = runInBackground;
    const { scan_id } = await api.startScan(path);

    state.scanId = scan_id;

    // Open modal if not running in background, or if it's already open (re-scan case)
    if (!state.scanInBackground || document.getElementById('progress-modal')?.classList.contains('open')) {
      openModal('progress-modal');
    }

    pollScan(scan_id);

  } catch (e) {

    showToast(e.message, 'error');

  }

}



function pollScan(id) {

  if (state.scanPoll) clearInterval(state.scanPoll);

  state.scanPoll = setInterval(async () => {

    try {

      const s = await api.getScanStatus(id);

      const fill = document.getElementById('progress-fill');
      const sideFill = document.getElementById('sidebar-progress-fill');
      const sidePct = document.getElementById('sidebar-progress-pct');
      const sideWrap = document.getElementById('sidebar-scan-progress');

      const text = document.getElementById('progress-text');

      const file = document.getElementById('progress-file');

      const notice = document.getElementById('progress-notice');

      const pct = s.files_found
        ? Math.min(99, (s.files_processed / s.files_found) * 100)
        : (s.progress || 0);

      const pctText = `${Math.round(pct)}%`;

      if (fill) {
        fill.style.width = `${pct}%`;
        fill.parentElement?.setAttribute('aria-valuenow', String(Math.round(pct)));
      }

      if (sideFill) sideFill.style.width = `${pct}%`;
      if (sidePct) sidePct.textContent = pctText;
      if (sideWrap) sideWrap.style.display = 'block';

      if (s.ai_status === 'paused') {
        if (text) text.textContent = `Groq rate limit reached. Resuming in ${formatWait(s.ai_wait_seconds)}.`;
        if (notice) {
          notice.textContent = 'Requests are paused automatically so the app does not keep hitting the API limit. Feel free to leave this process working in the background.';
          notice.style.display = 'block';
        }
      } else {
        if (text) text.textContent = `Analyzing file ${s.files_processed || 0} of ${s.files_found || 0}...`;
        if (notice) {
          notice.textContent = '';
          notice.style.display = 'none';
        }
      }

      if (file) file.textContent = s.current_file ? s.current_file.split(/[/\\]/).pop() : '';

      if (s.status === 'completed' || s.status === 'failed' || s.status === 'cancelled') {

        clearInterval(state.scanPoll);

        state.scanPoll = null;

        closeModal('progress-modal');
        const sideWrap = document.getElementById('sidebar-scan-progress');
        if (sideWrap) sideWrap.style.display = 'none';

        if (s.status === 'completed') {

          showToast(`Scan complete! ${s.files_found} files analyzed.`, 'success');

          // Always close modal when scan finishes, regardless of background status
        closeModal('progress-modal');

        // If the scan was running in the background, refresh the dashboard only if the dashboard is currently visible
        if (state.scanInBackground && state.currentView !== 'dashboard') {
          // Do nothing, the user is browsing elsewhere, dashboard will refresh on view change
        } else {
          await refreshDashboard(); // Refresh dashboard if current view or if scan was foregrounded
        }

        state.scanInBackground = false; // Reset background status

        } else if (s.status === 'failed') {

          showToast(s.error || 'Scan failed', 'error');

        } else if (s.status === 'cancelled') {

          showToast('Scan cancelled.');

        }

      }

    } catch (e) {

      clearInterval(state.scanPoll);
      state.scanPoll = null;
      closeModal('progress-modal');
      const sideWrap = document.getElementById('sidebar-scan-progress');
      if (sideWrap) sideWrap.style.display = 'none';
      state.scanInBackground = false; // Reset background status

      showToast(e.message, 'error');

    }

  }, 500);

}



export async function cancelScan() {

  if (state.scanId) {

    await api.cancelScan(state.scanId);
    closeModal('progress-modal'); // Close modal immediately on cancel

    showToast('Cancelling scan…');

  }

}



export async function runQuery(inputEl = document.getElementById('files-search'), options = {}) {

  const input = typeof inputEl === 'string' ? document.querySelector(inputEl) : inputEl;

  const q = input?.value?.trim();

  if (!q) return;

  try {

    const result = await api.query(q);

    const el = document.getElementById('query-results');

    if (el) {

      openModal('query-results');

      const rows = (result.results || []).slice(0, 50);
      const explanation = result.message || result.explanation || `Found ${result.count} results`;

      document.getElementById('query-results-body').innerHTML = `

        <p style="margin-bottom:12px">${escapeHtml(explanation)}</p>

        <div class="view-toolbar">
          <button class="btn btn-danger" id="query-delete-btn" data-delete-for="#query-results" disabled>Delete Selected</button>
        </div>

        <table class="data-table"><thead><tr><th><input type="checkbox" id="query-select-all" aria-label="Select all"></th><th>File</th><th>Category</th><th>Action</th></tr></thead>

        <tbody>${rows.map(r =>

          `<tr>
            <td><input type="checkbox" data-path="${escapeAttr(r.path)}" aria-label="Select ${escapeAttr(r.filename)}"></td>
            <td>${fileNameCell(r.filename, r.path)}</td>
            <td>${escapeHtml(r.category || '—')}</td>
            <td>${escapeHtml(r.action || '—')}</td>
          </tr>`

        ).join('')}</tbody></table>`;

      document.getElementById('query-select-all')?.addEventListener('change', (e) => {
        document.querySelectorAll('#query-results input[type=checkbox][data-path]').forEach(cb => {
          cb.checked = e.target.checked;
        });
        updateDeleteButton('#query-results');
      });

      wireRowCheckboxes('#query-results');

      document.getElementById('query-delete-btn')?.addEventListener('click', () => {
        promptDelete(getSelectedPaths('#query-results'));
      });

    }

    if (options.clear !== false) input.value = '';
    if (result.rate_limited && result.message) showToast(result.message);

  } catch (e) {

    showToast(e.message, 'error');

  }

}

