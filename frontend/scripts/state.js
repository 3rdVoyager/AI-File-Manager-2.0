export const state = {
  username: '',
  darkMode: true,
  setupComplete: false,
  apiKeySet: false,
  currentView: 'dashboard',
  scanId: null,
  scanPoll: null,
};

export function setView(name) {
  state.currentView = name;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.remove('active');
    n.removeAttribute('aria-current');
  });
  const view = document.getElementById(`view-${name}`);
  const nav = document.querySelector(`[data-view="${name}"]`);
  if (view) view.classList.add('active');
  if (nav) {
    nav.classList.add('active');
    nav.setAttribute('aria-current', 'page');
  }
}

export function syncAiBanner(apiKeySet) {
  state.apiKeySet = Boolean(apiKeySet);
  const banner = document.getElementById('ai-banner');
  if (banner) banner.style.display = state.apiKeySet ? 'none' : 'flex';
}
