let lastFocusedElement = null;

export function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

export function openModal(id) {
  const overlay = document.getElementById(id);
  if (!overlay) return;
  lastFocusedElement = document.activeElement;
  overlay.classList.add('open');
  const dialog = overlay.querySelector('.modal, .progress-card');
  if (dialog) {
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    if (!dialog.hasAttribute('tabindex')) dialog.setAttribute('tabindex', '-1');
    const focusTarget = dialog.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') || dialog;
    focusTarget.focus?.();
  }
}

export function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
  lastFocusedElement?.focus?.();
  lastFocusedElement = null;
}

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  const open = document.querySelector('.modal-overlay.open');
  if (open) closeModal(open.id);
});

export function renderDonut(svgId, segments, centerText) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const size = 120;
  const stroke = 18;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  let html = `<circle cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="var(--border)" stroke-width="${stroke}"/>`;
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  for (const seg of segments) {
    const len = (seg.value / total) * circumference;
    html += `<circle cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="${seg.color}"
      stroke-width="${stroke}" stroke-dasharray="${len} ${circumference - len}"
      stroke-dashoffset="${-offset}" transform="rotate(-90 ${size/2} ${size/2})"/>`;
    offset += len;
  }
  html += `<text x="${size/2}" y="${size/2 - 6}" class="donut-center" text-anchor="middle" font-size="11" fill="var(--text-muted)">${centerText.line1 || ''}</text>`;
  html += `<text x="${size/2}" y="${size/2 + 12}" class="donut-center" text-anchor="middle" font-size="14" font-weight="600" fill="var(--text-primary)">${centerText.line2 || ''}</text>`;
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svg.innerHTML = html;
}

export function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) {
    return `Today, ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function actionBadge(action) {
  const cls = action === 'Delete' ? 'badge-delete' : action === 'Keep' ? 'badge-keep' : 'badge-review';
  return `<span class="badge ${cls}">${action || 'Review'}</span>`;
}
