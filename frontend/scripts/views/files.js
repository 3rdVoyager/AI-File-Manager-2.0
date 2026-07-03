import { api } from '../api.js';

import { actionBadge, showToast } from '../components/ui.js';

import {

  escapeAttr, escapeHtml, fileNameCell, truncatePath, promptDelete, wireRowCheckboxes, bindSelectAll, getSelectedPaths,

} from './file-actions.js';



let sortCol = 'filename', sortOrder = 'asc', page = 1;

const TRASH_TIERS = { high: 70, medium: 50, low: 30 };



function trashTier(confidence) {

  const score = Number(confidence) || 0;

  if (score >= TRASH_TIERS.high) return 'high';

  if (score >= TRASH_TIERS.medium) return 'medium';

  return 'low';

}



function confidenceCell(confidence) {

  const score = Math.max(0, Math.min(100, Number(confidence) || 0));

  const tier = trashTier(score);

  const label = tier.charAt(0).toUpperCase() + tier.slice(1);

  return `

    <div class="confidence-cell">

      <span class="confidence-badge confidence-${tier}">${label}</span>

      <div class="confidence-meter" aria-label="${score}% confidence">

        <span class="confidence-fill confidence-${tier}" style="width:${score}%"></span>

      </div>

      <span class="confidence-score">${score}%</span>

    </div>`;

}



function updateTrashSummary(files) {

  const summary = document.getElementById('trash-confidence-summary');

  if (!summary) return;

  const counts = { high: 0, medium: 0, low: 0 };

  files.forEach(f => { counts[trashTier(f.confidence)] += 1; });

  summary.textContent = `${counts.high} high · ${counts.medium} medium · ${counts.low} low`;

}



export async function loadFiles(opts = {}) {

  if (opts.sort) sortCol = opts.sort;

  if (opts.order) sortOrder = opts.order;

  if (opts.page) page = opts.page;

  const search = document.getElementById('files-search')?.value || '';

  try {

    const data = await api.getFiles({ page, per_page: 50, sort: sortCol, order: sortOrder, search });

    renderFilesTable(data);

  } catch (e) {

    showToast(e.message, 'error');

  }

}



function renderFilesTable(data) {

  const tbody = document.getElementById('files-tbody');

  if (!tbody) return;

  if (!data.files?.length) {

    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:32px;color:var(--text-muted)">No files yet. Run a scan first.</td></tr>';

    return;

  }

  tbody.innerHTML = data.files.map(f => `

    <tr>

      <td><input type="checkbox" data-path="${escapeAttr(f.path)}" aria-label="Select ${escapeAttr(f.filename)}"></td>

      <td>${fileNameCell(f.filename, f.path)}</td>

      <td class="mono path-cell" title="${escapeAttr(f.path)}">${escapeHtml(truncatePath(f.path))}</td>

      <td>${escapeHtml(f.category || '—')}</td>

      <td>${escapeHtml(f.size_human)}</td>

      <td>${escapeHtml(f.importance ?? '—')}</td>

      <td>${actionBadge(f.action)}</td>

      <td>${escapeHtml(f.project || '—')}</td>

    </tr>`).join('');



  wireRowCheckboxes('#view-files');



  const pag = document.getElementById('files-pagination');

  if (pag) {

    const pages = Math.ceil(data.total / data.per_page);

    pag.innerHTML = `Page ${data.page} of ${pages} (${data.total} files)

      ${data.page > 1 ? `<button class="btn btn-sm btn-secondary" onclick="window.loadFilesPage(${data.page - 1})">Prev</button>` : ''}

      ${data.page < pages ? `<button class="btn btn-sm btn-secondary" onclick="window.loadFilesPage(${data.page + 1})">Next</button>` : ''}`;

  }

}



export async function loadLargeFiles() {

  try {

    const data = await api.getFiles({ sort: 'size_bytes', order: 'desc', per_page: 50 });

    const tbody = document.getElementById('large-tbody');

    if (!tbody) return;

    tbody.innerHTML = (data.files || []).map(f => `

      <tr>
        <td><input type="checkbox" data-path="${escapeAttr(f.path)}" aria-label="Select ${escapeAttr(f.filename)}"></td>
        <td>${fileNameCell(f.filename, f.path)}</td>
        <td class="mono path-cell" title="${escapeAttr(f.path)}">${escapeHtml(truncatePath(f.path))}</td>
        <td>${escapeHtml(f.size_human)}</td>
        <td>${escapeHtml(f.category || '—')}</td>
      </tr>`

    ).join('') || '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted)">No files</td></tr>';

    wireRowCheckboxes('#view-large');

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function loadRecentFiles() {

  try {

    const data = await api.getFiles({ sort: 'modified_at', order: 'desc', per_page: 50 });

    const tbody = document.getElementById('recent-tbody');

    if (!tbody) return;

    tbody.innerHTML = (data.files || []).map(f => `

      <tr>
        <td><input type="checkbox" data-path="${escapeAttr(f.path)}" aria-label="Select ${escapeAttr(f.filename)}"></td>
        <td>${fileNameCell(f.filename, f.path)}</td>
        <td class="mono path-cell" title="${escapeAttr(f.path)}">${escapeHtml(truncatePath(f.path))}</td>
        <td>${new Date(f.modified_at * 1000).toLocaleDateString()}</td>
        <td>${escapeHtml(f.category || '—')}</td>
      </tr>`

    ).join('') || '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted)">No files</td></tr>';

    wireRowCheckboxes('#view-recent');

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function loadTrashCandidates() {

  try {

    const minConfidence = Number(document.getElementById('trash-confidence-filter')?.value || TRASH_TIERS.medium);

    const data = await api.getFiles({
      action: 'Delete',
      min_confidence: minConfidence,
      sort: 'confidence',
      order: 'desc',
      per_page: 200,
    });

    const tbody = document.getElementById('trash-tbody');

    if (!tbody) return;

    const files = data.files || [];

    updateTrashSummary(files);

    const selectAll = document.getElementById('trash-select-all');

    if (selectAll) selectAll.checked = false;

    tbody.innerHTML = files.map(f => `

      <tr>

        <td><input type="checkbox" data-path="${escapeAttr(f.path)}" aria-label="Select ${escapeAttr(f.filename)}"></td>

        <td>${fileNameCell(f.filename, f.path)}</td>

        <td class="mono path-cell" title="${escapeAttr(f.path)}">${escapeHtml(truncatePath(f.path))}</td>

        <td>${escapeHtml(f.size_human)}</td>

        <td>${escapeHtml(f.category || '—')}</td>

        <td>${actionBadge(f.action)}</td>

        <td>${confidenceCell(f.confidence)}</td>

        <td>${escapeHtml(f.reasoning || '—')}</td>

      </tr>`

    ).join('') || '<tr><td colspan="8" style="text-align:center;padding:32px;color:var(--text-muted)">No trash candidates at this confidence level</td></tr>';

    wireRowCheckboxes('#view-trash');

  } catch (e) {

    showToast(e.message, 'error');

  }

}



function createDeleteSelectedHandler(viewSelector, reload) {
  return () => promptDelete(getSelectedPaths(viewSelector), reload);
}

export const deleteSelectedFiles = createDeleteSelectedHandler('#view-files', () => loadFiles());
export const deleteSelectedTrash = createDeleteSelectedHandler('#view-trash', () => loadTrashCandidates());
export const deleteSelectedLarge = createDeleteSelectedHandler('#view-large', () => loadLargeFiles());
export const deleteSelectedRecent = createDeleteSelectedHandler('#view-recent', () => loadRecentFiles());



export function deleteAllTrash() {

  const paths = [...document.querySelectorAll('#view-trash input[type=checkbox][data-path]')]

    .map(cb => cb.dataset.path);

  promptDelete(paths, () => loadTrashCandidates());

}



export function initFilesSort() {

  document.querySelectorAll('#files-table th[data-sort]').forEach(th => {

    th.addEventListener('click', () => {

      const col = th.dataset.sort;

      if (sortCol === col) sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';

      else { sortCol = col; sortOrder = 'asc'; }

      loadFiles();

    });

  });

  bindSelectAll('files-select-all', '#view-files');

  bindSelectAll('trash-select-all', '#view-trash');

  document.getElementById('trash-confidence-filter')?.addEventListener('change', loadTrashCandidates);

  bindSelectAll('large-select-all', '#view-large');

  bindSelectAll('recent-select-all', '#view-recent');

}

