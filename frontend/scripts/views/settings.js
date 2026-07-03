import { api } from '../api.js';

import { showToast, openModal, closeModal } from '../components/ui.js';

import { state, syncAiBanner } from '../state.js';



function populateModelSelect(selectEl, models, labels, selected) {

  if (!selectEl || !models) return;

  selectEl.innerHTML = models.map(m => {

    const label = labels?.[m] || m;

    return `<option value="${m}" ${m === selected ? 'selected' : ''}>${label}</option>`;

  }).join('');

}

export async function loadSettings() {

  try {

    const s = await api.getSettings();

    const statusEl = document.getElementById('settings-status');

    const modelEl = document.getElementById('settings-model');

    const setupModelEl = document.getElementById('setup-model');

    const hintEl = document.getElementById('api-key-hint');

    const dataDirEl = document.getElementById('settings-data-dir');



    if (statusEl) {

      statusEl.className = `status-badge ${s.api_key_set ? 'status-connected' : 'status-disconnected'}`;

      statusEl.textContent = s.api_key_set ? '● Connected' : '● Not configured';

    }

    populateModelSelect(modelEl, s.models, s.model_labels, s.model);

    populateModelSelect(setupModelEl, s.models, s.model_labels, s.model);

    if (hintEl && s.api_key_hint) hintEl.textContent = `Current key: ${s.api_key_hint}`;

    if (dataDirEl && s.data_dir) dataDirEl.textContent = s.data_dir;

    return s;

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function saveSettings() {

  const apiKey = document.getElementById('settings-api-key')?.value;

  const model = document.getElementById('settings-model')?.value;

  const body = {};

  if (apiKey) body.api_key = apiKey;

  if (model) body.model = model;

  try {

    const saved = await api.saveSettings(body);

    showToast('Settings saved', 'success');

    document.getElementById('settings-api-key').value = '';
    syncAiBanner(saved.api_key_set);

    await loadSettings();

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function testConnection() {

  const apiKey = document.getElementById('settings-api-key')?.value;

  const model = document.getElementById('settings-model')?.value;

  const body = {};

  if (apiKey) body.api_key = apiKey;

  if (model) body.model = model;

  try {

    const r = await api.testSettings(body);

    showToast(r.message || 'Connected!', 'success');
    syncAiBanner(true);

    if (apiKey || model) await saveSettings();

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export async function completeSetup() {

  const apiKey = document.getElementById('setup-api-key')?.value;

  const model = document.getElementById('setup-model')?.value;

  if (!apiKey) {

    showToast('Please paste your API key first', 'error');

    return;

  }

  try {

    await api.testSettings({ api_key: apiKey, model: model || undefined });

    await api.saveSettings({ api_key: apiKey, model, setup_complete: true });

    showToast('Setup complete!', 'success');

    document.getElementById('setup-modal')?.classList.remove('open');

    state.setupComplete = true;

    state.apiKeySet = true;

    window.location.reload();

  } catch (e) {

    showToast(e.message, 'error');

  }

}



export function skipSetup() {
  api.saveSettings({ setup_complete: true })
    .then(() => {
      document.getElementById('setup-modal')?.classList.remove('open');
      state.setupComplete = true;
      syncAiBanner(false);
    })
    .catch((e) => showToast(e.message, 'error'));
}

export function openResetModal() {
  const input = document.getElementById('reset-confirm-input');
  if (input) input.value = '';
  openModal('reset-modal');
}

export async function confirmReset() {
  const confirm = document.getElementById('reset-confirm-input')?.value?.trim();
  if (confirm !== 'RESET') {
    showToast('Type RESET to confirm', 'error');
    return;
  }
  try {
    await api.resetAll('RESET');
    closeModal('reset-modal');
    showToast('All data reset. Restarting…', 'success');
    window.location.reload();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

export function initResetModal() {
  document.getElementById('reset-all-btn')?.addEventListener('click', openResetModal);
  document.getElementById('reset-confirm-btn')?.addEventListener('click', confirmReset);
  document.getElementById('reset-cancel-btn')?.addEventListener('click', () => {
    closeModal('reset-modal');
  });
}

export async function quitApp() {
  try {
    await api.shutdown();
    showToast('Server stopped. You can close this tab.', 'success');
    setTimeout(() => window.close(), 800);
  } catch (e) {
    showToast(e.message || 'Server stopped. Close this tab or exit the terminal.', 'info');
  }
}

