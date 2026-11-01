// Host configuration, setup-tab preference, and optional tunnel controls.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {renderSetup} from './setup.js';
import {dashboard} from './state.js';

async function tunnelStatus(data = null) {
  if (dashboard.session?.remote_access || !dashboard.runtimeSetup.ready) { $('tunnel-card').hidden = true; return; }
  try {
    data = data || await api('/api/tunnel');
    $('tunnel-start').hidden = ['starting', 'downloading', 'running'].includes(data.status);
    $('tunnel-stop').hidden = !['starting', 'downloading', 'running'].includes(data.status);
    $('tunnel-status').textContent = data.error ? t('Tunnel failed') + ': ' + data.error : data.status === 'running' ? data.url : data.status === 'downloading' ? t('Downloading cloudflared…') : data.status === 'starting' ? t('Preparing tunnel…') : t('Tunnel stopped');
    $('tunnel-progress').hidden = !['starting', 'downloading'].includes(data.status);
    if (data.total_bytes) $('tunnel-progress').value = data.downloaded_bytes / data.total_bytes; else $('tunnel-progress').removeAttribute('value');
    $('tunnel-links').replaceChildren();
    function share(label, url) {
      const input = el('input', {readonly: '', value: url, 'aria-label': label});
      $('tunnel-links').append(el('div', {class: 'share-link'}, el('strong', {}, t(label)), input, button('Copy link', async () => { try { await navigator.clipboard.writeText(url); } catch { input.select(); document.execCommand('copy'); } })));
    }
    if (data.admin_url) share('Admin panel link', data.admin_url);
    for (const [name, url] of Object.entries(data.players || {})) share('OBS · ' + name, url);
    if (data.admin_url && !Object.keys(data.players).length) $('tunnel-links').append(el('p', {class: 'muted'}, t('Save a channel first to get an OBS-only link.')));
  } catch { $('tunnel-card').hidden = true; }
}

export function initConfig() {
  $('restart-cuda').addEventListener('click', action(async () => {
    if (!confirm('Restart the GPU inference worker? This unloads the model; the next generation will reload CUDA. Active work must finish or be cancelled first.')) return;
    const control = $('restart-cuda');
    control.disabled = true;
    try {
      const result = await api('/api/inference/restart', {method: 'POST'});
      $('health').textContent = result.message;
      await refresh();
    } finally { control.disabled = false; }
  }));
  $('config-form').addEventListener('submit', action(async event => {
    event.preventDefault(); const value = {device: $('config-device').value, cpu_threads: Number($('config-threads').value), keep_model_loaded: $('config-resident').checked, hotkey: $('config-hotkey').value, max_queue: Number($('config-queue').value), vram_warning_mib: Number($('config-vram-warning').value)};
    const saved = await api('/api/config', {method: 'PUT', body: value}); dashboard.config = saved;
    $('hotkey-status').textContent = t(saved.hotkey_status); $('health').textContent = t('Configuration saved. Model will load on the selected device for the next job.');
  }));
  $('tunnel-start').addEventListener('click', action(async () => { await api('/api/tunnel/start', {method: 'POST'}); await tunnelStatus(); }));
  $('tunnel-stop').addEventListener('click', action(async () => { await api('/api/tunnel/stop', {method: 'POST'}); await tunnelStatus(); }));
  $('config-show-setup').addEventListener('change', () => {
    dashboard.showSetupTab = $('config-show-setup').checked;
    try { localStorage.setItem('pactts-show-setup', String(dashboard.showSetupTab)); } catch {}
    renderSetup(dashboard.runtimeSetup);
  });
  try { dashboard.showSetupTab = localStorage.getItem('pactts-show-setup') === 'true'; } catch {}
  $('config-show-setup').checked = dashboard.showSetupTab;
}

export {tunnelStatus};
