// Update check and summary; update_panel.js owns persistent version selection.
import {api} from './api.js';
import {$, t} from './dom.js';
import {dashboard} from './state.js';

async function refreshUpdates(check = false) {
  $('updates-card').hidden = Boolean(dashboard.session?.remote_access);
  if (!dashboard.session || dashboard.session.remote_access) return;
  try {
    const value = await api('/api/updates' + (check ? '/check' : ''), check ? {method: 'POST'} : {});
    renderUpdateStatus(value);
  } catch (_) { /* Host-only controls are unavailable to shared administrators. */ }
}

function renderUpdateStatus(value) {
  $('update-status').textContent = `${value.version} · ${t(value.status)}${value.next_version ? ' · ' + value.next_version : ''}${value.error ? ' · ' + value.error : ''}`;
}

export function initUpdates() {
  $('update-check').onclick = () => refreshUpdates(true);
  refreshUpdates();
}

export {refreshUpdates, renderUpdateStatus};
