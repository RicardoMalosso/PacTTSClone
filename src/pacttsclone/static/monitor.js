// Generation progress, resource/residency displays, timers, and panic controls.
import {api, refresh} from './api.js';
import {$, action, bytes, duration, el, t} from './dom.js';
import {voiceAvailable} from './generation-settings.js';
import {stopBugVideo} from './help.js';
import {tab} from './navigation.js';
import {refreshCountermeasurePrompt} from './setup.js';
import {dashboard} from './state.js';

let lastMonitorAt = 0;

function stopAllAudio() { stopBugVideo(); document.querySelectorAll('audio').forEach(a => { try { a.pause(); if (a.readyState) a.currentTime = 0; } catch { /* keep panic responsive for broken media */ } }); dashboard.suppressAutoplay = true; }

function renderMonitor(job) {
  dashboard.lastMonitor = job; lastMonitorAt = performance.now();
  const voice = dashboard.state.voices.find(v => v.id === job.voice_id);
  const source = [job.requester_name && !job.channel ? job.requester_name : null, job.origin === 'cloudflare' ? t('Cloudflare request') : null, job.channel ? `Twitch · #${job.channel}${job.username ? ' · ' + job.username : ''}` : job.origin === 'cloudflare' ? null : job.origin === 'discord' ? t('Discord request') : t('Local request'), voice?.title || job.voice_title || job.original_filename, job.kind === 'transcribe' ? t('Voice preparation') : t('Generate speech')].filter(Boolean).join(' · ');
  $('monitor-source').textContent = source; $('live-generation-source').textContent = source;
  $('live-generation').hidden = false;
  $('status').textContent = job.error || (job.status === 'succeeded' ? (job.kind === 'transcribe' ? t('Voice preparation ready') : t('MP3 ready · {seconds} s elapsed', {seconds: job.elapsed_seconds})) : `${t(job.stage)} · ${job.device || job.config?.device || t('pending device selection')}`);
  $('live-generation-status').textContent = $('status').textContent;
  $('live-generation-cancel').hidden = !['queued', 'running'].includes(job.status);
  $('overall-progress').value = job.progress || 0;
  if (job.status === 'running') $('live-generation-progress').removeAttribute('value'); else $('live-generation-progress').value = job.progress || 0;
  $('cancel-job').hidden = !['queued', 'running'].includes(job.status);
  $('stage-list').replaceChildren();
  const completed = job.metrics?.stages?.length ? job.metrics.stages : job.stages || [];
  const names = {configure: t('CPU setup'), decode: t('Decode MP3'), load_model: t('Load / download'), transcribe: t('Transcribe'), inference: t('Generate speech'), encode: t('Encode MP3')};
  for (const [key, label] of Object.entries(names)) {
    const finished = completed.filter(s => s.name === key);
    const active = job.status === 'running' && job.stage === key;
    const p = el('progress', {max: '1'});
    if (!active) p.value = finished.length ? 1 : 0;
    const seconds = finished.reduce((n, s) => n + s.wall_seconds, 0);
    $('stage-list').append(el('div', {class: 'stage'}, label, p, active ? t('working…') : finished.length ? `${seconds.toFixed(1)} s` : '—'));
    if (finished.length) {
      const ram = Math.max(...finished.map(s => s.sampled_peak_worker_ram_bytes || 0));
      const vram = Math.max(...finished.map(s => s.sampled_peak_cuda_allocated_bytes || 0));
      const cpu = finished.reduce((n, s) => n + s.worker_cpu_seconds, 0);
      $('stage-list').append(el('small', {}, `CPU ${cpu.toFixed(2)} s · ${t('worker RAM peak')} ${bytes(ram)} · ${t('CUDA allocation peak')} ${bytes(vram)}`));
    }
  }
  $('report').textContent = JSON.stringify({elapsed_seconds: job.elapsed_seconds, device: job.device, ...job.metrics}, null, 2);
}

async function cancelMonitoredJob() { if (dashboard.lastMonitor && ['queued', 'running'].includes(dashboard.lastMonitor.status)) { await api(`/api/jobs/${dashboard.lastMonitor.id}/cancel`, {method: 'POST'}); await refresh(); } }

async function resources(data = null) {
  data = data || await api('/api/resources');
  const r = data.live, gpu = r.gpus[0];
  $('gpu-pressure-warning').hidden = !data.gpu_warning;
  $('gpu-pressure-warning').textContent = data.gpu_warning ? t(data.gpu_warning.message) + ' ' + bytes(data.gpu_warning.free_bytes) + ' / ' + bytes(data.gpu_warning.threshold_bytes) : '';
  $('cpu').textContent = `${r.system_cpu_percent.toFixed(0)}%`;
  $('ram').textContent = data.worker_pid ? bytes(r.process_ram_bytes) : t('Worker unloaded');
  $('system-ram').textContent = `${bytes(r.system_ram_used_bytes)} / ${bytes(r.system_ram_total_bytes)}`;
  $('vram').textContent = gpu ? `${bytes(gpu.used_bytes)} / ${bytes(gpu.total_bytes)}` : t('N/A');
  $('gpu').textContent = gpu?.utilization_percent == null ? t('N/A') : `${gpu.utilization_percent}%`;
  $('hardware-description').textContent = JSON.stringify(data.hardware, null, 2);
}

function renderResidency() {
  const kitten = dashboard.state.active_engine === 'kittentts2';
  const ming = dashboard.state.active_engine === 'ming-3';
  $('engine-text-hint').textContent = t(kitten ? 'KittenTTS2 supports [emotion], <event> and (((emphasis))) tags; language is detected automatically.' : ming ? 'Ming interprets punctuation and supported vocal tags.' : 'Punctuation is interpreted by OmniVoice.');
  $('engine-timing-hint').textContent = t(kitten ? 'The token budget limits each chunk; 25 audio tokens are approximately one second. A fixed seed helps reproduce a request.' : ming ? 'Each Ming task has its own controls; saved voice selection also chooses its settings preset.' : 'Duration overrides Speed when provided. Turning off output postprocessing avoids trimming trailing silence.');
  const residency = dashboard.state.model_residency || {};
  const active = dashboard.state.active_job;
  const latest = [...(dashboard.state.jobs || [])].sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at))[0];
  const lastFailure = latest?.status === 'failed' && /CUDA|GPU memory/i.test(latest.error || '') ? latest : null;
  const currentError = lastFailure && (!active || lastFailure.finished_at > active.created_at);
  $('cuda-status').textContent = currentError ? 'CUDA error: ' + lastFailure.error :
    active?.device === 'cuda' ? 'CUDA: active · ' + t(active.stage) :
    residency.loaded && residency.device === 'cuda' ? 'CUDA: model loaded on GPU · idle' :
    'CUDA: not checked · no model loaded. GPU utilization alone does not confirm CUDA.';

  const model = dashboard.state.model_residency || {};
  const warm = Boolean(model.loaded);
  $('model-residency').textContent = `${model.model || 'k2-fsa/OmniVoice'} · ${t(warm ? 'Warm · loaded in memory' : 'Cold · not loaded')} · ${model.device || t('N/A')}`;
  $('voice-residency-list').replaceChildren(...dashboard.state.voices.map(voice => el('p', {}, `${voice.title} · ${t(voiceAvailable(voice) ? (warm ? 'Warm' : 'Cold') : 'Needs preparation')}`)));
}

function renderGlobalStatus() {
  $('live-generation').hidden = false;
  const running = dashboard.state.active_job || dashboard.state.jobs.find(job => job.status === 'running');
  if (dashboard.runtimeSetup.import_status?.status === 'running') {
    $('live-generation-source').textContent = t('Import');
    $('live-generation-status').textContent = t(dashboard.runtimeSetup.import_status.category === 'models' ? 'Importing model weights' : 'Importing personal data');
    $('live-generation-progress').removeAttribute('value');
    $('live-generation-timer').textContent = duration(Date.now() / 1000 - dashboard.runtimeSetup.import_status.started_at);
    $('live-generation-cancel').hidden = true; return;
  }
  if (dashboard.runtimeSetup.status === 'running') {
    $('live-generation-source').textContent = t('Initial Setup');
    $('live-generation-status').textContent = t(dashboard.runtimeSetup.stage === 'models' ? 'Downloading / verifying models' : 'Installing dependencies') + ' · ' + t(dashboard.runtimeSetup.stage || '');
    const d = dashboard.runtimeSetup.download;
    if (d?.total_bytes) { $('live-generation-progress').value = Math.min(1, dashboard.modelDownloaded / d.total_bytes); } else $('live-generation-progress').removeAttribute('value');
    $('live-generation-cancel').hidden = true; return;
  }
  if (running) { renderMonitor(running); return; }
  $('live-generation-source').textContent = t(dashboard.runtimeSetup.ready ? 'Idle' : 'Initial Setup');
  $('live-generation-status').textContent = !dashboard.runtimeSetup.ready ? t('Waiting for host setup') : dashboard.state.jobs.some(job => job.status === 'queued') ? t('Waiting for queued work') : t('Ready for the next request');
  $('live-generation-progress').value = 0; $('live-generation-timer').textContent = '00:00.0'; $('live-generation-cancel').hidden = true;
}

export function initMonitor() {
  new ResizeObserver(() => document.documentElement.style.setProperty('--status-bar-height', `${$('live-generation').offsetHeight}px`)).observe($('live-generation'));
  setInterval(() => {
    document.querySelectorAll('[data-countdown-until]').forEach(node => { node.textContent = t('Starts in {seconds} s', {seconds: Math.max(0, (Number(node.dataset.countdownUntil) - Date.now()) / 1000).toFixed(1)}); });
    if (dashboard.runtimeSetup.status === 'running' && dashboard.runtimeSetup.started_at) {
      $('live-generation-timer').textContent = duration(Date.now() / 1000 - dashboard.runtimeSetup.started_at);
      $('setup-elapsed').textContent = duration(Date.now() / 1000 - dashboard.runtimeSetup.started_at);
      refreshCountermeasurePrompt();
    }
    if (!dashboard.lastMonitor) return;
    const delta = dashboard.lastMonitor.status === 'running' ? (performance.now() - lastMonitorAt) / 1000 : 0;
    $('timer').textContent = duration((dashboard.lastMonitor.elapsed_seconds || 0) + delta);
    if (dashboard.runtimeSetup.status === 'running' && dashboard.runtimeSetup.started_at) $('live-generation-timer').textContent = duration(Date.now() / 1000 - dashboard.runtimeSetup.started_at);
    else if (dashboard.lastMonitor.status === 'running') $('live-generation-timer').textContent = $('timer').textContent;
    $('stage-timer').textContent = `${((dashboard.lastMonitor.stage_elapsed_seconds || 0) + delta).toFixed(1)} s`;
  }, 100);
  $('cancel-job').addEventListener('click', action(cancelMonitoredJob));
  $('live-generation-cancel').addEventListener('click', action(cancelMonitoredJob));
  $('view-monitor').addEventListener('click', () => { tab('studio'); $('monitor-source').scrollIntoView({behavior: 'smooth', block: 'center'}); });
  $('panic').addEventListener('click', action(async () => { stopAllAudio(); await api('/api/panic', {method: 'POST'}); }));
  $('cancel-all').addEventListener('click', action(async () => { stopAllAudio(); await api('/api/cancel-all', {method: 'POST'}); }));
  document.addEventListener('keydown', action(async e => {
    const parts = (dashboard.config?.hotkey || '').toUpperCase().split('+').map(p => p === 'CONTROL' ? 'CTRL' : p);
    if (parts.at(-1) === e.key.toUpperCase() && e.ctrlKey === parts.includes('CTRL') && e.altKey === parts.includes('ALT') && e.shiftKey === parts.includes('SHIFT')) {
      e.preventDefault(); stopAllAudio(); await api('/api/panic', {method: 'POST'});
    }
  }));
}

export {renderGlobalStatus, renderMonitor, renderResidency, resources, stopAllAudio};
