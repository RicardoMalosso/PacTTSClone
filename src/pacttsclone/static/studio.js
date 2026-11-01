// Local generation, result playback, autoqueue preferences, and local OBS.
import {api, refresh} from './api.js';
import {$, action, sleep, t} from './dom.js';
import {readGenerationSettings} from './generation-settings.js';
import {renderMonitor} from './monitor.js';
import {dashboard} from './state.js';

let currentJob = null;

function autoqueueNote(job) {
  $('autoqueue-note').textContent = !job?.request?.autoqueue_general ? '' : job.playback_error ? t('Automatic OBS queue failed: ') + t(job.playback_error) : job.general_playback_item_id ? t('Queued on local OBS source.') : t('Queuing on local OBS source…');
}

function clearResult() {
  dashboard.completedJob = null; $('autoqueue-note').textContent = '';
  $('player').pause(); $('player').removeAttribute('src'); $('player').load();
  $('player').hidden = true; $('actions').hidden = true; $('error').hidden = true;
  $('playback-note').textContent = '';
}

async function watch(id) {
  while (true) {
    const job = (dashboard.realtime?.healthy && dashboard.state.jobs.find(j => j.id === id)) || await api('/api/jobs/' + id);
    if (job.status === 'running' || !dashboard.lastMonitor || (dashboard.lastMonitor.id === job.id && !dashboard.state.active_job)) renderMonitor(job);
    if (job.status === 'failed' || job.status === 'cancelled') { currentJob = null; throw new Error(job.error || t('Generation cancelled.')); }
    if (job.status === 'succeeded') {
      if (!dashboard.state.active_job || dashboard.state.active_job.id === job.id) { $('status').textContent = t('MP3 ready · {seconds} s elapsed', {seconds: job.elapsed_seconds}); $('live-generation-status').textContent = $('status').textContent; }
      $('player').src = job.output_url; $('player').hidden = false; $('actions').hidden = false;
      $('download').href = job.output_url; $('download').download = `pactts-${job.id}.mp3`;
      if ($('autoplay').checked && !dashboard.suppressAutoplay) {
        try { await $('player').play(); }
        catch { $('playback-note').textContent = t('The browser blocked autoplay. Press play to listen.'); }
      }
      $('result-source').textContent = `${job.voice_title || t('Voice')} · ${job.requester_name || job.username || t('Local')} · ${t(job.origin || 'local')}`;
      dashboard.completedJob = job.id; autoqueueNote(job); currentJob = null; return;
    }
    if (dashboard.realtime?.healthy) await new Promise(resolve => {
      const done = () => { clearTimeout(timer); window.removeEventListener('studio-state', done); resolve(); };
      const timer = setTimeout(done, 5000);
      window.addEventListener('studio-state', done, {once: true});
    });
    else await sleep(5000);
  }
}

async function queueGeneral(id) {
  await api(`/api/channels/playbackMain/replay/${id}`, {method: 'POST'});
  $('playback-note').textContent = t('Queued on local OBS source.');
}

function showSharedResult(job) {
  // A different browser or Twitch can finish this job. Expose its controls without
  // causing another speaker to autoplay or enqueue the same clip twice.
  dashboard.completedJob = job.id;
  $('player').src = job.output_url; $('player').hidden = false; $('actions').hidden = false;
  $('download').href = job.output_url; $('download').download = `pactts-${job.id}.mp3`;
  $('result-source').textContent = `${job.voice_title || t('Voice')} · ${job.requester_name || job.username || t('Local')} · ${t(job.origin || 'local')}`;
  autoqueueNote(job);
}

export function initStudio() {
  try { $('autoplay').checked = localStorage.getItem('pactts-autoplay') === 'true'; } catch { /* optional */ }
  $('autoplay').addEventListener('change', () => { try { localStorage.setItem('pactts-autoplay', String($('autoplay').checked)); } catch { /* optional */ } });
  try { $('autoqueue').checked = localStorage.getItem('pactts-autoqueue') === 'true'; } catch { /* optional */ }
  $('autoqueue').addEventListener('change', () => { try { localStorage.setItem('pactts-autoqueue', String($('autoqueue').checked)); } catch { /* optional */ } });
  $('text').addEventListener('input', () => { $('count').textContent = `${$('text').value.length} / 2000`; });
  $('stop').addEventListener('click', () => { $('player').pause(); $('player').currentTime = 0; });
  $('voice-select').addEventListener('change', () => {
    const voice = dashboard.state.voices.find(v => v.id === $('voice-select').value);
    $('preset-note').textContent = voice ? `${voice.original_filename} · ${t('saved transcript')}: ${voice.transcript}` : '';
  });
  $('generate-form').addEventListener('submit', action(async event => {
    event.preventDefault(); if (dashboard.busy) return;
    dashboard.busy = true; $('generate').disabled = true; clearResult(); currentJob = null; dashboard.suppressAutoplay = false;
    try {
      const voice = $('voice-select').value;
      if (!$('requester-name').value.trim()) { $('requester-name').focus(); throw new Error(t('Enter a requester name.')); }
      if (!voice) throw new Error(t('Choose a saved voice in Voices first.'));
      const job = await api(`/api/voices/${voice}/generate`, {method: 'POST', body: {text: $('text').value, ...readGenerationSettings($('generate-form')), autoqueue_general: $('autoqueue').checked, requester_name: $('requester-name').value.trim(), requester_id: dashboard.requesterId}});
      currentJob = job.id; await watch(job.id);
    } finally { dashboard.busy = false; $('generate').disabled = !dashboard.runtimeSetup.ready; }
  }));
  $('send-general').addEventListener('click', action(async () => { if (dashboard.completedJob) await queueGeneral(dashboard.completedJob); }));
  $('general-form').addEventListener('submit', action(async event => {
    event.preventDefault();
    await api('/api/general-playback', {method: 'PUT', body: {name: 'general', delay_seconds: Number($('general-delay').value), filter_level: $('general-filter').value, custom_filters: $('general-custom').value.split('\n').map(s => s.trim()).filter(Boolean), paused: dashboard.latestChannelState?.paused || false}});
    await refresh();
  }));
}

export {autoqueueNote, queueGeneral, showSharedResult};
