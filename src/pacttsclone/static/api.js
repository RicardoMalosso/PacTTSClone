// REST transport, requester identity, CSRF headers, and snapshot refresh.
import {$} from './dom.js';
import {dashboard, updateState} from './state.js';

async function api(url, options = {}) {
  const opts = {cache: 'no-store', ...options};
  opts.headers = {'X-PacTTS-Requester-ID': dashboard.requesterId, 'X-PacTTS-Requester-Name': encodeURIComponent($('requester-name').value), ...options.headers};
  if ((opts.method || 'GET') !== 'GET') opts.headers['X-PacTTS-Token'] = dashboard.session.token;
  if (opts.body && !(opts.body instanceof FormData)) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.body); }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(x => x.msg).join('; ') : 'Request failed.');
    error.status = response.status; throw error;
  }
  return response.json();
}

export function initApi() {
  try { dashboard.requesterId = localStorage.getItem('pactts-requester-id'); if (!dashboard.requesterId) { dashboard.requesterId = crypto.randomUUID(); localStorage.setItem('pactts-requester-id', dashboard.requesterId); } $('requester-name').value = localStorage.getItem('pactts-requester-name') || ''; } catch { dashboard.requesterId = crypto.randomUUID(); }
  $('requester-name').addEventListener('input', () => { try { localStorage.setItem('pactts-requester-name', $('requester-name').value); } catch { /* optional persistence */ } });
}

export {api};

export async function refresh() {
  await updateState(await api('/api/state'));
}
