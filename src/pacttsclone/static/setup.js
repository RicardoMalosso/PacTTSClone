// Runtime readiness, installation progress, and the countermeasures dialog.
import {api} from './api.js';
import {$, duration, formatTransferBytes, sleep, t} from './dom.js';
import {renderOptionalImport, renderWeightDiscovery} from './imports.js';
import {renderGlobalStatus} from './monitor.js';
import {tab} from './navigation.js';
import {dashboard} from './state.js';

let setupAvailable = true;

let modelSession = null;

let countermeasurePromptOpen = false;

let countermeasureOfferPending = false;

function claimCountermeasures() {
  // The backend permanently claimed this prompt when it was displayed.
  countermeasurePromptOpen = false;
  $('setup-too-long').hidden = true;
}

function refreshCountermeasurePrompt() {
  const eligible = dashboard.runtimeSetup.status === 'running' && !dashboard.runtimeSetup.initial_setup_completed &&
    !dashboard.runtimeSetup.countermeasures_offered && dashboard.runtimeSetup.started_at &&
    Date.now() / 1000 - dashboard.runtimeSetup.started_at >= 30;
  if (eligible && !countermeasureOfferPending && !countermeasurePromptOpen) {
    countermeasureOfferPending = true;
    api('/api/setup/countermeasures/offer', {method: 'POST'}).then(result => {
      if (result.offered && dashboard.runtimeSetup.status === 'running') {
        countermeasurePromptOpen = true;
        $('setup-too-long').hidden = false;
      }
    }).catch(error => console.warn('Countermeasures prompt:', error))
      .finally(() => { countermeasureOfferPending = false; });
  }
  if (dashboard.runtimeSetup.status !== 'running') countermeasurePromptOpen = false;
  $('setup-too-long').hidden = !countermeasurePromptOpen;
}

function closeCountermeasures() { $('countermeasure-modal').hidden = true; const video = $('countermeasure-video'); video.pause(); video.currentTime = 0; }

async function showCountermeasures() {
  if (!$('countermeasure-modal').hidden) return;
  $('countermeasure-modal').hidden = false;
  $('countermeasure-loading').hidden = false;
  const video = $('countermeasure-video');
  video.pause();
  video.currentTime = 0;
  video.hidden = true;
  const bar = $('countermeasure-bar');
  bar.value = 0;
  const started = performance.now();
  while (!($('countermeasure-modal').hidden) && performance.now() - started < 2000) {
    bar.value = Math.min(100, (performance.now() - started) / 20);
    await sleep(40);
  }
  if ($('countermeasure-modal').hidden) return;
  bar.value = 100;
  $('countermeasure-loading').hidden = true;
  video.hidden = false;
  try { await video.play(); } catch (e) { console.warn('Jingling keys playback needs user interaction:', e); }
}

function renderSetup(data) {
  renderWeightDiscovery(data);
  renderOptionalImport(data);
  const wasReady = dashboard.runtimeSetup.ready;
  dashboard.runtimeSetup = data;
  document.querySelector('[data-tab="setup"]').hidden = data.ready && !dashboard.showSetupTab;
  if (data.ready && !dashboard.showSetupTab && !$('pane-setup').hidden) tab('config');
  if (modelSession !== data.started_at) { modelSession = data.started_at; dashboard.modelDownloaded = 0; }
  if (data.stage === 'models' && data.download?.total_bytes) {
    dashboard.modelDownloaded = Math.max(dashboard.modelDownloaded, data.download.completed_bytes || 0);
  }
  document.querySelectorAll('[data-tab]').forEach(node => { node.disabled = !data.ready && !['setup', 'config', 'engines'].includes(node.dataset.tab); });
  $('generate').disabled = dashboard.busy || !data.ready;
  renderGlobalStatus();
  $('tunnel-card').hidden = !data.ready;
  $('setup-start').disabled = data.status === 'running';
  $('setup-cancel').hidden = data.status !== 'running';
  $('setup-device').disabled = data.status === 'running';
  $('setup-progress').value = data.completed_steps || 0;
  $('setup-status').textContent = data.ready ? t('Setup ready. You can open the studio.') : t('Setup stage: ') + t(data.stage || 'idle');
  $('setup-error').hidden = !data.error;
  $('setup-error').textContent = data.error ? t(data.error) : '';
  const logPanel = $('setup-log');
  const follow = logPanel.scrollTop + logPanel.clientHeight >= logPanel.scrollHeight - 36;
  logPanel.textContent = (data.lines || []).join('\n');
  if (follow) logPanel.scrollTop = logPanel.scrollHeight;
  if (data.started_at) $('setup-elapsed').textContent = duration((data.finished_at || Date.now() / 1000) - data.started_at);
  refreshCountermeasurePrompt();
  const d = data.download;
  $('setup-file-progress').hidden = !d;
  if (d) { $('setup-file-progress').max = d.file_total || 1; $('setup-file-progress').value = d.phase?.startsWith('verifying') ? (d.file_total || 1) : (d.file_bytes || 0); }
  const isDependency = data.stage === 'pytorch' || data.stage === 'inference';
  const p = isDependency ? data.dependency_progress : null;
  $('setup-package-status').textContent = isDependency ?
    (p?.message || 'Preparing dependency downloads — resolving package information') : '';
  $('setup-dependency-progress').hidden = !isDependency;
  if (isDependency) {
    const bar = $('setup-dependency-progress');
    if (p?.total_bytes > 0 && p.downloaded_bytes != null) {
      bar.max = p.total_bytes;
      bar.value = Math.min(p.downloaded_bytes, p.total_bytes);
      $('setup-dependency-metrics').textContent =
        `${p.percent?.toFixed(1) ?? '0.0'}% · ${formatTransferBytes(p.downloaded_bytes)} / ${formatTransferBytes(p.total_bytes)}` +
        (p.speed_bytes_per_second ? ` · ${formatTransferBytes(p.speed_bytes_per_second)}/s` : '') +
        (p.eta_seconds != null ? ` · ~${Math.round(p.eta_seconds)} s remaining` : '');
    } else {
      bar.removeAttribute('value');
      $('setup-dependency-metrics').textContent = p?.phase === 'installing' ?
        'Installing downloaded packages (time remaining unknown)' :
        'Waiting for measurable download bytes (time remaining unknown)';
    }
  } else $('setup-dependency-metrics').textContent = '';
  $('setup-download-status').textContent = d ?
    `${d.repo} · ${d.file} · ${t(d.phase || d.cache_status || 'checking cache')} · ${d.file_total ? (100 * (d.file_bytes || 0) / d.file_total).toFixed(1) + '%' : 'N/A'}` +
    ` · ${formatTransferBytes(d.file_bytes)} / ${formatTransferBytes(d.file_total)}` +
    (d.total_bytes ? ` · total ${(100 * dashboard.modelDownloaded / d.total_bytes).toFixed(1)}%` : '') +
    ` · ${d.reused_files || 0} ${t('verified cached files reused')}` :
    (isDependency ? 'Dependency progress appears above.' : 'Waiting for model downloads.');
  if (!data.ready && !setupAvailable) return;
  if (!data.ready && $('pane-config').hidden && $('pane-engines').hidden && (wasReady || !$('pane-setup').hidden)) tab('setup');
}

async function runtimeStatus() {
  if (dashboard.session?.remote_access) { renderSetup({ready: dashboard.state.setup_ready ?? dashboard.session.setup_ready, status: 'host', stage: 'Waiting for host setup', ...(dashboard.state.setup_activity || {})}); document.querySelector('[data-tab="setup"]').hidden = dashboard.runtimeSetup.ready; $('setup-start').hidden = true; $('setup-cancel').hidden = true; $('setup-device').disabled = true; $('tunnel-card').hidden = true; return; }
  try { renderSetup(await api('/api/setup')); }
  catch (e) {
    // Shared administrators cannot install host software; generation remains
    // governed by the server readiness guard.
    if (e.status === 403 && dashboard.session && location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') {
      setupAvailable = false; dashboard.runtimeSetup = {ready: true};
      document.querySelector('[data-tab="setup"]').hidden = true;
    } else throw e;
  }
}

function setupAction(fn) { return async () => { try { await fn(); } catch (e) { $('setup-error').hidden = false; $('setup-error').textContent = t(e.message); } }; }

export function initSetup() {
  $('setup-too-long-no').addEventListener('click', claimCountermeasures);
  $('setup-too-long-close').addEventListener('click', claimCountermeasures);
  $('setup-too-long-yes').addEventListener('click', () => {
    claimCountermeasures();
    showCountermeasures();
  });
  $('config-countermeasures').addEventListener('click', showCountermeasures);
  $('countermeasure-close').addEventListener('click', closeCountermeasures);
  $('setup-start').addEventListener('click', setupAction(async () => {
    renderSetup(await api('/api/setup/start', {method: 'POST', body: {device: $('setup-device').value}}));
  }));
  $('setup-cancel').addEventListener('click', setupAction(async () => { renderSetup(await api('/api/setup/cancel', {method: 'POST'})); }));
  window.addEventListener('localechange', () => { if (setupAvailable) renderSetup(dashboard.runtimeSetup); });
}

export {refreshCountermeasurePrompt, renderSetup, runtimeStatus};
