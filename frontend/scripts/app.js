import { api } from './api.js';
import { openModal, closeModal } from './components/ui.js';

import { state, setView, syncAiBanner } from './state.js';

import { refreshDashboard } from './views/dashboard.js';

import { loadSettings, saveSettings, testConnection, completeSetup, skipSetup, initResetModal, quitApp } from './views/settings.js';

import { loadFiles, loadLargeFiles, loadRecentFiles, loadTrashCandidates, loadEmptyFolders, loadRenameSuggestions, initFilesSort, deleteSelectedFiles, deleteSelectedTrash, deleteAllTrash, deleteSelectedLarge, deleteSelectedRecent, deleteSelectedEmptyFolders, applySelectedRenames } from './views/files.js';

import { bindFileLinks, initDeleteModal } from './views/file-actions.js';

import { loadDuplicates, loadScans } from './views/other.js';

import { openFolderPicker, selectFolder, cancelScan, runQuery, startScan } from './views/scan.js';



function greeting() {

  const h = new Date().getHours();

  const period = h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';

  const el = document.getElementById('greeting');

  if (el) el.textContent = `Good ${period}, ${state.username}`;

}

const VIEW_TITLES = {
  files: ['All Files', 'Browse, search, and act on analyzed files.'],
  duplicates: ['Duplicates', 'Compare duplicate groups before deleting anything.'],
  large: ['Large Files', 'Find the files taking up the most space.'],
  recent: ['Recent Files', 'Review files changed most recently.'],
  trash: ['Trash Candidates', 'Review cleanup recommendations before deleting.'],
  'empty-folders': ['Empty Folders', 'Delete folders that are completely empty.'],
  'rename-tool': ['Rename Tool', 'Review AI filename suggestions from scans.'],
  scans: ['Recent Scans', 'Review previous scans or run one again.'],
  settings: ['Settings', 'Manage AI, appearance, and local data.'],
};

function updateHeader(view) {
  const title = document.getElementById('greeting');
  const subtitle = document.getElementById('header-subtitle');
  if (view === 'dashboard') {
    greeting();
    if (subtitle) subtitle.textContent = "Here's what's happening with your files.";
    return;
  }
  const [heading, detail] = VIEW_TITLES[view] || ['AI File Manager', 'Manage your local files.'];
  if (title) title.textContent = heading;
  if (subtitle) subtitle.textContent = detail;
}



async function applyTheme(theme) {

  const dark = theme === 'dark';

  state.darkMode = dark;

  document.documentElement.setAttribute('data-theme', theme);

  localStorage.setItem('aifm-theme', theme);
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');

}



async function toggleTheme() {

  const next = state.darkMode ? 'light' : 'dark';

  await applyTheme(next);

  try {

    await api.saveSettings({ theme: next });

  } catch (e) {

    console.warn('Could not persist theme:', e);

  }

}


let aiSearchEnabled = localStorage.getItem('aifm-ai-search') === 'true';

let aiSearchTimer = null;



function updateAiSearchUi() {

  const input = document.getElementById('files-search');

  const toggle = document.getElementById('files-ai-toggle');

  if (input) input.placeholder = aiSearchEnabled ? 'Ask about your files…' : 'Search files…';

  if (toggle) {

    toggle.classList.toggle('active', aiSearchEnabled);

    toggle.setAttribute('aria-pressed', String(aiSearchEnabled));

    toggle.title = aiSearchEnabled ? 'AI search is on' : 'Toggle AI search';

  }

}



function runFilesAiSearchNow() {

  const input = document.getElementById('files-search');

  if (input?.value?.trim()) runQuery(input, { clear: false });

}



function onFilesSearchInput() {

  if (!aiSearchEnabled) {

    loadFiles();

    return;

  }

  clearTimeout(aiSearchTimer);

  aiSearchTimer = setTimeout(runFilesAiSearchNow, 400);

}



function toggleAiSearch() {

  aiSearchEnabled = !aiSearchEnabled;

  localStorage.setItem('aifm-ai-search', String(aiSearchEnabled));

  updateAiSearchUi();

  if (!aiSearchEnabled) loadFiles();

  else runFilesAiSearchNow();

}



async function onViewChange(view) {

  setView(view);
  updateHeader(view);

  switch (view) {

    case 'dashboard': await refreshDashboard(); break;

    case 'files': await loadFiles(); break;

    case 'duplicates': await loadDuplicates(); break;

    case 'large': await loadLargeFiles(); break;

    case 'recent': await loadRecentFiles(); break;

    case 'trash': await loadTrashCandidates(); break;

    case 'empty-folders': await loadEmptyFolders(); break;

    case 'rename-tool': await loadRenameSuggestions(); break;

    case 'scans': await loadScans(); break;

    case 'settings': await loadSettings(); break;

  }

  if (view === 'files') updateAiSearchUi();

}



async function init() {

  const savedTheme = localStorage.getItem('aifm-theme') || 'dark';

  await applyTheme(savedTheme);



  try {

    const status = await api.getStatus();

    state.username = status.username || 'User';

    state.setupComplete = status.setup_complete;

    syncAiBanner(status.api_key_set);

    greeting();
    updateHeader('dashboard');



    if (status.theme) {

      await applyTheme(status.theme);

    }



    const avatar = document.getElementById('user-avatar');

    const userName = document.getElementById('user-name');

    if (avatar) avatar.textContent = state.username.charAt(0).toUpperCase();

    if (userName) userName.textContent = state.username;



    if (!status.setup_complete) {

      document.getElementById('setup-modal')?.classList.add('open');

      await loadSettings();

    }



    await refreshDashboard();

  } catch (e) {

    console.error('Init failed:', e);

  }



  document.querySelectorAll('[data-view]').forEach(btn => {

    btn.addEventListener('click', () => onViewChange(btn.dataset.view));

  });



  function handleScanTableClick(e) {

    const scanBtn = e.target.closest('[data-scan-path]');

      if (scanBtn) {

        startScan(scanBtn.dataset.scanPath, false);

      return;

    }

    const btn = e.target.closest('[data-view]');

    if (btn) onViewChange(btn.dataset.view);

  }

  document.getElementById('scans-tbody')?.addEventListener('click', handleScanTableClick);

  document.getElementById('recent-scans-tbody')?.addEventListener('click', handleScanTableClick);



  document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);

  document.getElementById('new-scan-btn')?.addEventListener('click', openFolderPicker);

  document.getElementById('select-folder-btn')?.addEventListener('click', selectFolder);

  document.getElementById('folder-cancel-btn')?.addEventListener('click', () => {

    document.getElementById('folder-modal')?.classList.remove('open');

  });

  document.getElementById('cancel-scan-btn')?.addEventListener('click', cancelScan);
  document.getElementById('background-scan-btn')?.addEventListener('click', () => { 
    state.scanInBackground = true;
    closeModal('progress-modal');
  });

  document.getElementById('sidebar-show-scan')?.addEventListener('click', () => {
    openModal('progress-modal');
  });

  document.getElementById('settings-save')?.addEventListener('click', saveSettings);

  document.getElementById('settings-test')?.addEventListener('click', testConnection);

  document.getElementById('setup-save')?.addEventListener('click', completeSetup);

  document.getElementById('setup-skip')?.addEventListener('click', skipSetup);

  bindFileLinks(document.body);

  updateAiSearchUi();

  document.getElementById('files-ai-toggle')?.addEventListener('click', toggleAiSearch);

  document.getElementById('files-search')?.addEventListener('input', onFilesSearchInput);

  document.getElementById('files-search')?.addEventListener('keydown', e => {

    if (e.key === 'Enter' && aiSearchEnabled) {

      e.preventDefault();

      clearTimeout(aiSearchTimer);

      runFilesAiSearchNow();

    }

  });

  document.getElementById('banner-settings')?.addEventListener('click', () => onViewChange('settings'));

  document.getElementById('close-query-results')?.addEventListener('click', () => {

    closeModal('query-results');

  });



  initFilesSort();

  initDeleteModal();

  document.getElementById('files-delete-btn')?.addEventListener('click', deleteSelectedFiles);

  document.getElementById('trash-delete-btn')?.addEventListener('click', deleteSelectedTrash);

  document.getElementById('trash-delete-all-btn')?.addEventListener('click', deleteAllTrash);
  document.getElementById('large-delete-btn')?.addEventListener('click', deleteSelectedLarge);
  document.getElementById('recent-delete-btn')?.addEventListener('click', deleteSelectedRecent);
  document.getElementById('empty-folders-delete-btn')?.addEventListener('click', deleteSelectedEmptyFolders);
  document.getElementById('empty-folders-scan-btn')?.addEventListener('click', () => openFolderPicker('empty-folders'));
  document.getElementById('duplicates-refresh-btn')?.addEventListener('click', loadDuplicates);
  document.getElementById('rename-refresh-btn')?.addEventListener('click', loadRenameSuggestions);
  document.getElementById('rename-apply-btn')?.addEventListener('click', applySelectedRenames);
  document.getElementById('quit-btn')?.addEventListener('click', quitApp);
  initResetModal();



  document.addEventListener('keydown', async e => {

    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {

      e.preventDefault();

      if (state.currentView !== 'files') await onViewChange('files');

      document.getElementById('files-search')?.focus();

    }

  });



  window.setView = onViewChange;

  window.loadFilesPage = (p) => loadFiles({ page: p });

}



document.addEventListener('DOMContentLoaded', init);

