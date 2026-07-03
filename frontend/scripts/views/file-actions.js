import { api } from '../api.js';
import { showToast, openModal, closeModal } from '../components/ui.js';
import { refreshDashboard } from './dashboard.js';

let pendingDeletePaths = [];
let deleteRefreshCallback = null;

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function escapeAttr(value) {
  return escapeHtml(value);
}

export function truncatePath(path, max = 60) {
  if (!path || path.length <= max) return path;
  const half = Math.floor((max - 3) / 2);
  return path.slice(0, half) + '…' + path.slice(-half);
}

export function fileNameCell(filename, path) {
  return `<button type="button" class="file-link" data-open-path="${escapeAttr(path)}" title="Open with default app">${escapeHtml(filename)}</button>`;
}

export async function openFile(path) {
  if (!path) {
    showToast('Could not open file: missing path', 'error');
    return;
  }
  try {
    const data = await api.open(path);
    showToast(`Opened ${data?.filename || data?.path?.split(/[\\/]/).pop() || 'file'}`, 'success');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

export function bindFileLinks(container) {
  const root = typeof container === 'string' ? document.querySelector(container) : container;
  if (!root) return;
  root.addEventListener('click', (e) => {
    const link = e.target.closest?.('[data-open-path]');
    if (!link || !root.contains(link)) return;
    e.preventDefault();
    openFile(link.getAttribute('data-open-path'));
  });
}

export function getSelectedPaths(containerSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return [];
  return [...container.querySelectorAll('input[type=checkbox][data-path]:checked')]
    .map(cb => cb.dataset.path);
}

export function bindSelectAll(selectAllId, containerSelector) {
  const selectAll = document.getElementById(selectAllId);
  if (!selectAll) return;
  selectAll.addEventListener('change', () => {
    const boxes = document.querySelectorAll(`${containerSelector} input[type=checkbox][data-path]`);
    boxes.forEach(cb => { cb.checked = selectAll.checked; });
    updateDeleteButton(containerSelector);
  });
}

export function updateDeleteButton(containerSelector) {
  const count = getSelectedPaths(containerSelector).length;
  const btn = document.querySelector(`[data-delete-for="${containerSelector}"]`);
  if (btn) {
    btn.disabled = count === 0;
    btn.textContent = count ? `Delete Selected (${count})` : 'Delete Selected';
  }
}

export function wireRowCheckboxes(containerSelector) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  container.querySelectorAll('input[type=checkbox][data-path]').forEach(cb => {
    cb.addEventListener('change', () => updateDeleteButton(containerSelector));
  });
  updateDeleteButton(containerSelector);
}

function resetSelectAllCheckboxes() {
  ['files-select-all', 'trash-select-all', 'large-select-all', 'recent-select-all'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.checked = false;
  });
  updateDeleteButton('#view-files');
  updateDeleteButton('#view-trash');
  updateDeleteButton('#view-large');
  updateDeleteButton('#view-recent');
}

async function refreshAfterFileChange() {
  resetSelectAllCheckboxes();
  if (deleteRefreshCallback) await deleteRefreshCallback();
  await refreshDashboard();
}

export async function promptDelete(paths, onSuccess) {
  if (!paths.length) {
    showToast('Select at least one file', 'error');
    return;
  }
  try {
    const preview = await api.deletePreview(paths);
    pendingDeletePaths = paths;
    deleteRefreshCallback = onSuccess;

    const body = document.getElementById('delete-preview-body');
    const total = document.getElementById('delete-preview-total');
    if (body) {
      body.innerHTML = (preview.files || []).map(f =>
        `<div class="delete-preview-item">${fileNameCell(f.filename, f.path)}<span class="text-muted">${escapeHtml(f.size_human)}</span></div>`
      ).join('');
    }
    if (total) {
      total.textContent = `${preview.files?.length || paths.length} file(s) · ${preview.total_human || '0 B'} — sent to Recycle Bin`;
    }
    openModal('delete-modal');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

export async function confirmDelete() {
  if (!pendingDeletePaths.length) return;
  const pathsToRemove = [...pendingDeletePaths];
  try {
    const data = await api.delete(pendingDeletePaths);
    const ok = data.results?.filter(r => r.success).length || data.deleted_count || 0;
    const fail = data.results?.filter(r => !r.success).length || 0;
    closeModal('delete-modal');
    pendingDeletePaths = [];

    pathsToRemove.forEach(path => {
      document.querySelectorAll('input[type=checkbox][data-path]').forEach(cb => {
        if (cb.dataset.path === path) cb.closest('tr')?.remove();
      });
    });

    if (ok) {
      const freed = data.freed_human ? ` (${data.freed_human} freed)` : '';
      showToast(`${ok} file(s) sent to Recycle Bin${freed}`, 'success');
    }
    if (fail) showToast(`${fail} file(s) could not be deleted`, 'error');

    await refreshAfterFileChange();
    deleteRefreshCallback = null;
  } catch (e) {
    showToast(e.message, 'error');
  }
}

export function initDeleteModal() {
  document.getElementById('delete-confirm-btn')?.addEventListener('click', confirmDelete);
  document.getElementById('delete-cancel-btn')?.addEventListener('click', () => {
    pendingDeletePaths = [];
    closeModal('delete-modal');
  });
}
