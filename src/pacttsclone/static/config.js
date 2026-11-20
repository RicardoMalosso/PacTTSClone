// Host configuration, setup-tab preference, and optional tunnel controls.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {renderSetup} from './setup.js';
import {dashboard, subscribeState} from './state.js';

function renderVolumeTestVoices() {
  const select = $('volume-test-voice');
  const card = $('volume-test-card');
  if (!select || !card) return;
  const previous = select.value;
  select.replaceChildren();
  for (const voice of dashboard.state.voices || []) {
    select.append(el('option', {value: voice.id}, voice.title));
  }
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  card.hidden = Boolean(dashboard.session?.remote_access);
  $('volume-test-run').disabled = !select.options.length;
}

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
  subscribeState(renderVolumeTestVoices);
  renderVolumeTestVoices();
  let latestVolumeReport = null;
  $('volume-test-run').addEventListener('click', action(async () => {
    const run = $('volume-test-run');
    const status = $('volume-test-status');
    const report = $('volume-test-report');
    const download = $('volume-test-download');
    run.disabled = true;
    status.textContent = t('Running local volume test…');
    report.hidden = true;
    download.hidden = true;
    try {
      latestVolumeReport = await api('/api/volume-test', {
        method: 'POST', body: {voice_id: $('volume-test-voice').value},
      });
      report.textContent = JSON.stringify(latestVolumeReport, null, 2);
      report.hidden = false;
      download.hidden = false;
      status.textContent = t(
        latestVolumeReport.result === 'pass' ? 'Volume test passed.' : 'Volume test failed.',
      );
    } catch (error) {
      status.textContent = t('Volume test failed: {message}', {message: error.message});
    } finally {
      renderVolumeTestVoices();
    }
  }));
  $('volume-test-download').addEventListener('click', () => {
    if (!latestVolumeReport) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(latestVolumeReport, null, 2)], {type: 'application/json'}),
    );
    const anchor = el('a', {href: url, download: 'pactts-volume-test.json'});
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
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
