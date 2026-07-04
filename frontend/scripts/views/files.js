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

    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-muted)">No files yet. Run a scan first.</td></tr>';

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


function updateEmptyFoldersButton(hasDirectories = false) {
  const count = document.querySelectorAll('#view-empty-folders input[type=checkbox][data-path]:checked').length;
  const btn = document.getElementById('empty-folders-delete-btn');
  if (btn) {
    // For debugging: enable if there are directories, regardless of checkbox selection
    btn.disabled = !hasDirectories && count === 0;
    btn.textContent = count ? `Remove Selected (${count})` : 'Remove Selected';
  }
}


function wireEmptyFolderSelection() {
  const boxes = document.querySelectorAll('#view-empty-folders input[type=checkbox][data-path]');
  boxes.forEach(cb => {
    cb.addEventListener('change', () => updateEmptyFoldersButton());
  });
  
  const selectAll = document.getElementById('empty-folders-select-all');
  if (selectAll) {
    selectAll.checked = false;
    selectAll.onclick = () => {
      boxes.forEach(cb => { cb.checked = selectAll.checked; });
      updateEmptyFoldersButton();
    };
  }
  updateEmptyFoldersButton();
}


export async function loadEmptyFolders(path = null) {
  try {
    const data = await api.getEmptyDirectories(path);
    const tbody = document.getElementById('empty-folders-tbody');
    const summary = document.getElementById('empty-folders-summary');
    if (!tbody) return;

    const directories = data.directories || [];
    const scanType = path ? `in ${path.split(/[\\/]/).pop()}` : 'in scanned locations';
    if (summary) summary.textContent = `${directories.length.toLocaleString()} empty folder(s) found ${scanType}`;

    tbody.innerHTML = directories.map(d => `
      <tr>
        <td><input type="checkbox" data-path="${escapeAttr(d.path)}" aria-label="Select ${escapeAttr(d.name)}"></td>
        <td>${escapeHtml(d.name)}</td>
        <td class="mono path-cell" title="${escapeAttr(d.path)}">${escapeHtml(truncatePath(d.path, 90))}</td>
        <td class="mono path-cell" title="${escapeAttr(d.root_path)}">${escapeHtml(truncatePath(d.root_path, 60))}</td>
      </tr>`
    ).join('') || `<tr><td colspan="4" style="text-align:center;padding:32px;color:var(--text-muted)">No empty folders found ${scanType}.</td></tr>`;

    wireEmptyFolderSelection();
    updateEmptyFoldersButton(directories.length > 0);
  } catch (e) {
    showToast(e.message, 'error');
  }
}


export async function deleteSelectedEmptyFolders() {
  const paths = getSelectedPaths('#view-empty-folders');
  if (!paths.length) {
    showToast('Select at least one empty folder', 'error');
    return;
  }
  if (!confirm(`Remove ${paths.length} empty folder(s)? Only folders that are still empty will be removed.`)) return;

  try {
    const data = await api.deleteEmptyDirectories(paths);
    const failures = (data.results || []).filter(r => !r.success).length;
    if (data.removed_count) showToast(`${data.removed_count} empty folder(s) removed`, 'success');
    if (failures) showToast(`${failures} folder(s) could not be removed`, 'error');
    await loadEmptyFolders();
  } catch (e) {
    showToast(e.message, 'error');
  }
}


function updateRenameButton() {
  const count = document.querySelectorAll('#view-rename-tool input[type=checkbox][data-path]:checked').length;
  const btn = document.getElementById('rename-apply-btn');
  if (btn) {
    btn.disabled = count === 0;
    btn.textContent = count ? `Apply Selected (${count})` : 'Apply Selected';
  }
}


function wireRenameSelection() {
  const boxes = document.querySelectorAll('#view-rename-tool input[type=checkbox][data-path]');
  boxes.forEach(cb => {
    cb.addEventListener('change', () => updateRenameButton());
  });

  const selectAll = document.getElementById('rename-select-all');
  if (selectAll) {
    selectAll.checked = false;
    selectAll.onclick = () => {
      boxes.forEach(cb => { cb.checked = selectAll.checked; });
      updateRenameButton();
    };
  }
  updateRenameButton();
}


export async function loadRenameSuggestions() {
  try {
    const data = await api.getRenameSuggestions();
    const tbody = document.getElementById('rename-tbody');
    const summary = document.getElementById('rename-summary');
    if (!tbody) return;

    const suggestions = data.suggestions || [];
    if (summary) summary.textContent = `${suggestions.length.toLocaleString()} rename suggestion(s) from scans`;

    tbody.innerHTML = suggestions.map(s => `
      <tr>
        <td><input type="checkbox" data-path="${escapeAttr(s.path)}" aria-label="Select ${escapeAttr(s.filename)}"></td>
        <td>${fileNameCell(s.filename, s.path)}<div class="mono path-cell" title="${escapeAttr(s.path)}">${escapeHtml(truncatePath(s.path, 72))}</div></td>
        <td><strong>${escapeHtml(s.suggested_filename)}</strong><div class="mono path-cell" title="${escapeAttr(s.target_path)}">${escapeHtml(truncatePath(s.target_path, 72))}</div></td>
        <td>${escapeHtml(s.rename_reason || s.summary || 'Clearer document name')}</td>
        <td>${escapeHtml(s.rename_confidence)}%</td>
      </tr>`
    ).join('') || '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted)">No rename suggestions yet. Run a scan with AI enabled to find poorly named documents.</td></tr>';

    wireRenameSelection();
  } catch (e) {
    showToast(e.message, 'error');
  }
}


export async function applySelectedRenames() {
  const paths = getSelectedPaths('#view-rename-tool');
  if (!paths.length) {
    showToast('Select at least one rename suggestion', 'error');
    return;
  }
  if (!confirm(`Rename ${paths.length} document(s)? Existing files will not be overwritten.`)) return;

  try {
    const data = await api.applyRenameSuggestions(paths);
    const failures = (data.results || []).filter(r => !r.success).length;
    if (data.renamed_count) showToast(`${data.renamed_count} document(s) renamed`, 'success');
    if (failures) showToast(`${failures} rename(s) could not be applied`, 'error');
    await loadRenameSuggestions();
    await loadFiles();
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

