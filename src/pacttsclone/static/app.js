// Dashboard entrypoint: initialize features, route snapshots, and connect SSE.
import {api, initApi, refresh} from './api.js';
import {commandRow, fillChannel, initChannels, renderChannelState, renderChannels} from './channels.js';
import {initConfig, tunnelStatus} from './config.js';
import {initDiscord, loadDiscord, renderDiscordStatus} from './discord.js';
import {$, error, t} from './dom.js';
import {initEngines, renderEngines} from './engines.js';
import {initGenerationSettings} from './generation-settings.js';
import {renderHistory, renderJobs} from './history.js';
import {initImports} from './imports.js';
import {initMonitor, renderGlobalStatus, renderMonitor, renderResidency, resources, stopAllAudio} from './monitor.js';
import {initNavigation, tab} from './navigation.js';
import {initSetup, renderSetup, runtimeStatus} from './setup.js';
import {dashboard, subscribeState, updateState} from './state.js';
import {autoqueueNote, initStudio, showSharedResult} from './studio.js';
import {initTwitch, loadTwitchAuth} from './twitch.js';
import {initUpdates, refreshUpdates, renderUpdateStatus} from './updates.js';
import {initVoices, renderVoices} from './voices.js';

let initialHealth = null;

let eventVersions = {};

let panicRevision = null;

async function applyState(value, sections = null) {
  window.dispatchEvent(new Event('studio-state'));
  if (dashboard.session?.remote_access) await runtimeStatus();
  const monitored = dashboard.state.active_job || dashboard.state.jobs.find(j => j.status === 'running') || dashboard.state.jobs.filter(j => j.status === 'queued').sort((a, b) => a.created_at - b.created_at)[0] || [...dashboard.state.jobs].sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at))[0];
  if (monitored) renderMonitor(monitored);
  renderResidency(); renderGlobalStatus();
  const latestAudio = dashboard.state.jobs.filter(job => job.kind === 'speech' && job.status === 'succeeded' && job.output_url).sort((a, b) => b.finished_at - a.finished_at)[0];
  if (!dashboard.busy && latestAudio && latestAudio.id !== dashboard.completedJob && $('player').paused) showSharedResult(latestAudio);
  if (dashboard.completedJob) autoqueueNote(dashboard.state.jobs.find(j => j.id === dashboard.completedJob));
  if (panicRevision !== null && panicRevision !== dashboard.state.panic_revision) stopAllAudio();
  panicRevision = dashboard.state.panic_revision;
  const changed = kinds => !sections || kinds.some(kind => sections.includes(kind));
  if (changed(['voice', 'job'])) renderVoices();
  if (changed(['job'])) renderJobs();
  if (changed(['job', 'request'])) renderHistory();
  if (changed(['channel', 'playback', 'connections'])) renderChannels();
  $('hotkey-status').textContent = t(dashboard.state.hotkey_status);
  if (!sections || sections.some(k => ['connections', 'channel', 'playback', 'chat', 'twitch_event'].includes(k))) await renderChannelState();
}

async function init() {
  try {
    const shareKey = new URLSearchParams(location.hash.slice(1)).get('admin');
    if (shareKey) {
      const response = await fetch('/api/remote/session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: shareKey})});
      if (!response.ok) throw new Error('This share link has expired or is invalid.');
      history.replaceState(null, '', location.pathname + location.search);
    }
    dashboard.session = await api('/api/session'); dashboard.config = await api('/api/config');
    $('config-device').value = dashboard.config.device === 'cpu' ? 'cuda' : dashboard.config.device; $('config-threads').value = dashboard.config.cpu_threads; $('config-resident').checked = dashboard.config.keep_model_loaded;
    $('config-vram-warning').value = dashboard.config.vram_warning_mib ?? 512; $('config-hotkey').value = dashboard.config.hotkey; $('config-queue').value = dashboard.config.max_queue;
    await loadDiscord(true);
    const health = await api('/api/health'); initialHealth = health;
    $('health').textContent = [health.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), health.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
    await runtimeStatus();
    await refresh();
    if (!dashboard.selectedChannel && !$('commands-list').children.length) commandRow();
    await resources(); await tunnelStatus();
    // Initialization may finish after the user has opened a tab and edited a
    // channel. Never replace that draft with the persisted channel at this point.
    if (!dashboard.userSelectedTab) {
      if (dashboard.selectedChannel) {
        if (dashboard.selectedChannel === 'playbackMain') tab('general');
        else { fillChannel(dashboard.selectedChannel); tab('channels'); }
      } else tab(dashboard.runtimeSetup.ready ? 'studio' : 'setup');
    }
    $('generate').disabled = !dashboard.runtimeSetup.ready;
    const synchronize = async () => {
      // Server restarts rotate CSRF tokens. Reconnect refreshes that token too.
      dashboard.session = await api('/api/session');
      eventVersions = {};
      await refresh(); await runtimeStatus(); await resources();
      await tunnelStatus(); await loadDiscord(); await refreshUpdates();
      await renderEngines();
      if (dashboard.twitchAuthPending) await loadTwitchAuth();
      window.dispatchEvent(new Event('studio-resync'));
    };
    dashboard.realtime = new StudioEventStream({
      enabled: dashboard.session.realtime?.sse ?? !dashboard.session.remote_access,
      fallbackMs: dashboard.session.realtime?.fallback_ms || 5000,
      synchronize, fallback: synchronize,
      handlers: {
        state: data => {
          const sections = Object.keys(data.versions).filter(k => eventVersions[k] !== data.versions[k]);
          eventVersions = data.versions;
          return updateState(data.value, sections);
        },
        resources: data => resources(data),
        setup: async data => { renderSetup(data); await renderEngines(); },
        discord: data => { if (!dashboard.discordBusy) { dashboard.discordSnapshot = data; renderDiscordStatus(); } },
        tunnel: data => tunnelStatus(data),
        updates: data => { renderUpdateStatus(data); window.dispatchEvent(new CustomEvent('studio-updates', {detail: data})); }
      }
    });
    dashboard.realtime.start();

  } catch (e) { error(e.message); $('health').textContent = t('Could not initialize. Refresh after checking the server terminal.'); }
}

function initApp() {
  window.addEventListener('localechange', () => {
    if (dashboard.completedJob) autoqueueNote(dashboard.state.jobs.find(j => j.id === dashboard.completedJob));
    const guide = $('bug-video').querySelector('iframe'); if (guide) guide.title = t('Bug reporting guide');
    document.querySelectorAll('.resources strong').forEach(node => { node.textContent = t(node.textContent); });
    $('hotkey-status').textContent = t(dashboard.state.hotkey_status || '');
    const drafts = [...document.querySelectorAll('.voice-card')].map(card => ({id: card.dataset.voiceId, title: card.querySelector('input[data-field="title"]')?.value, transcript: card.querySelector('textarea')?.value}));
    dashboard.voicesKey = dashboard.historyKey = ''; renderVoices(); renderHistory(); renderJobs(); renderChannels();
    for (const d of drafts) { const card = [...document.querySelectorAll('.voice-card')].find(c => c.dataset.voiceId === d.id); if (card) { card.querySelector('input[data-field="title"]').value = d.title; card.querySelector('textarea').value = d.transcript; } }
    if (dashboard.lastMonitor) renderMonitor(dashboard.lastMonitor); renderResidency(); renderGlobalStatus();
    if (initialHealth) $('health').textContent = [initialHealth.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), initialHealth.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
    if (dashboard.session) { renderChannelState().catch(() => {}); tunnelStatus().catch(() => {}); }
  });
}

subscribeState(applyState);

initApi();
initNavigation();
initGenerationSettings();
initStudio();
initMonitor();
initVoices();
initChannels();
initConfig();
initDiscord();
initSetup();
initTwitch();
initImports();
initUpdates();
initEngines();
initApp();
init();
