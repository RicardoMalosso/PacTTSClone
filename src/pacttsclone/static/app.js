'use strict';
const t = window.Locale.t;
let initialHealth = null;
let runtimeSetup = {ready: false}, setupAvailable = true;
let showSetupTab = false;
let modelDownloaded = 0, modelSession = null, setupEventsConnected = false;
const $ = id => document.getElementById(id);
new ResizeObserver(() => document.documentElement.style.setProperty('--status-bar-height', `${$('live-generation').offsetHeight}px`)).observe($('live-generation'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let session, state = {jobs: [], voices: [], channels: []}, config;
let selectedChannel = location.pathname.endsWith('/control') ? location.pathname.split('/')[1] : '';
let bugVideoTimer = null, bugVideoOpen = false;
let completedJob = null;
let currentJob = null, busy = false, lastMonitor = null, lastMonitorAt = 0;
let voicesKey = '', historyKey = '', channelKey = '', channelLinksKey = '', channelDashboardKey = '', latestChannelState = null, panicRevision = null, suppressAutoplay = false;
function stopAllAudio() { stopBugVideo(); document.querySelectorAll('audio').forEach(a => { try { a.pause(); if (a.readyState) a.currentTime = 0; } catch { /* keep panic responsive for broken media */ } }); suppressAutoplay = true; }

let requesterId;
try { requesterId = localStorage.getItem('pactts-requester-id'); if (!requesterId) { requesterId = crypto.randomUUID(); localStorage.setItem('pactts-requester-id', requesterId); } $('requester-name').value = localStorage.getItem('pactts-requester-name') || ''; } catch { requesterId = crypto.randomUUID(); }
$('requester-name').addEventListener('input', () => { try { localStorage.setItem('pactts-requester-name', $('requester-name').value); } catch { /* optional persistence */ } });
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}
function error(message) { $('error').textContent = t(message); $('error').hidden = false; $('health').textContent = t(message); }
function action(fn) { return async event => { try { await fn(event); } catch (e) { error(e.message); } }; }
function button(text, fn, cls = 'secondary small-button') { return window.Locale.bind(el('button', {type: 'button', class: cls, onclick: action(fn)}), text); }
function link(text, href, download = false) { return window.Locale.bind(el('a', {href, ...(download ? {download: ''} : {target: '_blank', rel: 'noopener noreferrer'})}), text); }
function bytes(value) { return value == null ? t('N/A') : `${(value / 1073741824).toFixed(2)} GiB`; }
function formatTransferBytes(value) {
  if (!Number.isFinite(value) || value < 0) return 'N/A';
  if (value < 1024) return Math.round(value) + ' B';
  if (value < 1048576) return (value / 1024).toFixed(1) + ' KiB';
  if (value < 1073741824) return (value / 1048576).toFixed(1) + ' MiB';
  return (value / 1073741824).toFixed(2) + ' GiB';
}
function duration(value) { const n = Math.max(0, value || 0); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${(n % 60).toFixed(1).padStart(4, '0')}`; }
async function api(url, options = {}) {
  const opts = {cache: 'no-store', ...options};
  opts.headers = {'X-PacTTS-Requester-ID': requesterId, 'X-PacTTS-Requester-Name': encodeURIComponent($('requester-name').value), ...options.headers};
  if ((opts.method || 'GET') !== 'GET') opts.headers['X-PacTTS-Token'] = session.token;
  if (opts.body && !(opts.body instanceof FormData)) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.body); }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(x => x.msg).join('; ') : 'Request failed.');
    error.status = response.status; throw error;
  }
  return response.json();
}
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
let bugPlayer = null, bugPlayerReady = false, youtubeApiPromise = null, bugVideoRequest = 0;
function stopBugVideo() {
  bugVideoRequest++;
  clearTimeout(bugVideoTimer); bugVideoTimer = null; bugVideoOpen = false; bugPlayerReady = false;
  if (bugPlayer) { bugPlayer.destroy(); bugPlayer = null; }
  $('bug-video').replaceChildren();
  document.querySelector('[data-tab="bugs"]').removeAttribute('aria-busy');
}
function youtubeApi() {
  if (window.YT?.Player) return Promise.resolve();
  if (!youtubeApiPromise) youtubeApiPromise = new Promise((resolve, reject) => {
    window.onYouTubeIframeAPIReady = resolve;
    const script = el('script', {src: 'https://www.youtube.com/iframe_api'});
    script.onerror = () => { youtubeApiPromise = null; script.remove(); reject(new Error('Cannot load video player. Try again or use the YouTube link.')); };
    document.head.append(script);
  });
  return youtubeApiPromise;
}
async function openBugVideo() {
  if (bugVideoOpen) return;
  bugVideoOpen = true;
  const request = ++bugVideoRequest;
  document.querySelector('[data-tab="bugs"]').setAttribute('aria-busy', 'true');
  $('health').textContent = t('Loading bug reporting video…');
  bugVideoTimer = setTimeout(() => {
    if (request !== bugVideoRequest) return;
    stopBugVideo();
    $('health').replaceChildren(t('Video player unavailable. '), link('Watch on YouTube ↗', 'https://youtu.be/b2eEl2oKXLA'));
  }, 20000);
  try {
    await youtubeApi();
    if (!bugVideoOpen || request !== bugVideoRequest) return;
    const mount = el('div', {id: 'bug-player-mount'}); $('bug-video').append(mount);
    bugPlayer = new YT.Player(mount, {
      host: 'https://www.youtube-nocookie.com', videoId: 'b2eEl2oKXLA',
      playerVars: {autoplay: 0, rel: 0, playsinline: 1},
      events: {
        onReady: event => {
          if (!bugVideoOpen || request !== bugVideoRequest) return;
          clearTimeout(bugVideoTimer);
          bugPlayerReady = true;
          event.target.getIframe().title = t('Bug reporting guide');
          document.querySelector('[data-tab="bugs"]').removeAttribute('aria-busy');
          tab('bugs');
          window.Locale.bind($('bug-video-status'), 'If autoplay is blocked, press play in the video.');
          bugVideoTimer = setTimeout(() => {
            if (bugVideoOpen && request === bugVideoRequest) event.target.playVideo();
          }, 200);
        },
        onError: () => {
          if (request !== bugVideoRequest) return;
          stopBugVideo(); $('health').textContent = t('Video unavailable. Open the bug reporting guide on YouTube.');
        }
      }
    });
  } catch (error) {
    if (request === bugVideoRequest) { stopBugVideo(); $('health').textContent = error.message; }
  }
}
const localPlaybackHost = el('section', {id: 'local-playback-host'});
$('pane-studio').append($('general-form'), localPlaybackHost);
const channelControls = $('channel-connection').parentElement;
const channelControlsHost = channelControls.parentElement;
function tab(name) {
  if (name === 'general') name = 'studio';
  if (!runtimeSetup.ready && !['setup', 'config'].includes(name)) name = 'setup';
  if (name === 'bugs' && !bugPlayerReady) { openBugVideo(); return; }
  window.Locale.apply();
  if (name !== 'bugs') stopBugVideo();
  const general = name === 'studio';
  if (general) selectedChannel = 'playbackMain';
  else if (name === 'channels' && selectedChannel === 'playbackMain') fillChannel('');
  window.Locale.bind($('playback-heading'), general ? 'Local OBS Sources' : 'Twitch & OBS');
  window.Locale.bind($('playback-description'), general ? 'Queue any generated MP3 here without connecting to Twitch.' : 'IRC chat starts automatically for saved channels. Optionally authorize Bits, Channel Points and subscriptions.');
  (general ? localPlaybackHost : channelControlsHost).append(channelControls);
  $('channel-form').hidden = general;
  $('channel-dashboard').hidden = general;
  $('general-form').hidden = !general;
  $('chat-events').parentElement.hidden = general;
  if (general && state.general_playback) {
    $('general-delay').value = state.general_playback.delay_seconds;
    $('general-filter').value = state.general_playback.filter_level;
    $('general-custom').value = state.general_playback.custom_filters.join('\n');
  }
  renderChannels();
  if (session) renderChannelState().catch(e => error(e.message));
  const pane = name;
  document.querySelectorAll('.pane').forEach(p => { p.hidden = p.id !== 'pane-' + pane; });
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
}
let userSelectedTab = false;
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { userSelectedTab = true; tab(b.dataset.tab); }));
try { $('autoplay').checked = localStorage.getItem('pactts-autoplay') === 'true'; } catch { /* optional */ }
$('autoplay').addEventListener('change', () => { try { localStorage.setItem('pactts-autoplay', String($('autoplay').checked)); } catch { /* optional */ } });
try { $('autoqueue').checked = localStorage.getItem('pactts-autoqueue') === 'true'; } catch { /* optional */ }
$('autoqueue').addEventListener('change', () => { try { localStorage.setItem('pactts-autoqueue', String($('autoqueue').checked)); } catch { /* optional */ } });
function autoqueueNote(job) {
  $('autoqueue-note').textContent = !job?.request?.autoqueue_general ? '' : job.playback_error ? t('Automatic OBS queue failed: ') + t(job.playback_error) : job.general_playback_item_id ? t('Queued on local OBS source.') : t('Queuing on local OBS source…');
}
// Speech language is independent from the interface locale.
try { const saved = localStorage.getItem('pactts-speech-language'); if (['pt', 'en', 'auto'].includes(saved)) $('language').value = saved; } catch { /* optional */ }
$('language').addEventListener('change', () => { try { localStorage.setItem('pactts-speech-language', $('language').value); } catch { /* optional */ } });
$('text').addEventListener('input', () => { $('count').textContent = `${$('text').value.length} / 2000`; });
$('stop').addEventListener('click', () => { $('player').pause(); $('player').currentTime = 0; });
$('voice-select').addEventListener('change', () => {
  const voice = state.voices.find(v => v.id === $('voice-select').value);
  $('preset-note').textContent = voice ? `${voice.original_filename} · ${t('saved transcript')}: ${voice.transcript}` : '';
});
function clearResult() {
  completedJob = null; $('autoqueue-note').textContent = '';
  $('player').pause(); $('player').removeAttribute('src'); $('player').load();
  $('player').hidden = true; $('actions').hidden = true; $('error').hidden = true;
  $('playback-note').textContent = '';
}
function renderMonitor(job) {
  lastMonitor = job; lastMonitorAt = performance.now();
  const voice = state.voices.find(v => v.id === job.voice_id);
  const source = [job.requester_name && !job.channel ? job.requester_name : null, job.origin === 'cloudflare' ? t('Cloudflare request') : null, job.channel ? `Twitch · #${job.channel}${job.username ? ' · ' + job.username : ''}` : job.origin === 'cloudflare' ? null : t('Local request'), voice?.title || job.voice_title || job.original_filename, job.kind === 'transcribe' ? t('Voice preparation') : t('Generate speech')].filter(Boolean).join(' · ');
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
setInterval(() => {
  if (runtimeSetup.status === 'running' && runtimeSetup.started_at) {
    $('live-generation-timer').textContent = duration(Date.now() / 1000 - runtimeSetup.started_at);
    $('setup-elapsed').textContent = duration(Date.now() / 1000 - runtimeSetup.started_at);
    refreshCountermeasurePrompt();
  }
  if (!lastMonitor) return;
  const delta = lastMonitor.status === 'running' ? (performance.now() - lastMonitorAt) / 1000 : 0;
  $('timer').textContent = duration((lastMonitor.elapsed_seconds || 0) + delta);
  if (runtimeSetup.status === 'running' && runtimeSetup.started_at) $('live-generation-timer').textContent = duration(Date.now() / 1000 - runtimeSetup.started_at);
  else if (lastMonitor.status === 'running') $('live-generation-timer').textContent = $('timer').textContent;
  $('stage-timer').textContent = `${((lastMonitor.stage_elapsed_seconds || 0) + delta).toFixed(1)} s`;
}, 100);
async function watch(id) {
  while (true) {
    const job = await api('/api/jobs/' + id);
    if (job.status === 'running' || !lastMonitor || (lastMonitor.id === job.id && !state.active_job)) renderMonitor(job);
    if (job.status === 'failed' || job.status === 'cancelled') { currentJob = null; throw new Error(job.error || t('Generation cancelled.')); }
    if (job.status === 'succeeded') {
      if (!state.active_job || state.active_job.id === job.id) { $('status').textContent = t('MP3 ready · {seconds} s elapsed', {seconds: job.elapsed_seconds}); $('live-generation-status').textContent = $('status').textContent; }
      $('player').src = job.output_url; $('player').hidden = false; $('actions').hidden = false;
      $('download').href = job.output_url; $('download').download = `pactts-${job.id}.mp3`;
      if ($('autoplay').checked && !suppressAutoplay) {
        try { await $('player').play(); }
        catch { $('playback-note').textContent = t('The browser blocked autoplay. Press play to listen.'); }
      }
      $('result-source').textContent = `${job.voice_title || t('Voice')} · ${job.requester_name || job.username || t('Local')} · ${t(job.origin || 'local')}`;
      completedJob = job.id; autoqueueNote(job); currentJob = null; return;
    }
    await sleep(500);
  }
}
const defaultGenerationSettings = Object.freeze({speed: 1, duration: null, steps: 32, denoise: true, guidance_scale: 2, preprocess_prompt: true, postprocess_output: true});
const generationFields = [
  ['speed', 'Speed', 'number', '0.5', '1.5', '0.05'],
  ['duration', 'Duration (seconds)', 'number', '0.5', '120', '0.1'],
  ['steps', 'Inference Steps', 'number', '4', '64', '1'],
  ['guidance_scale', 'Guidance Scale (CFG)', 'number', '0', '4', '0.1'],
  ['denoise', 'Denoise', 'checkbox'],
  ['preprocess_prompt', 'Preprocess Prompt', 'checkbox'],
  ['postprocess_output', 'Postprocess Output', 'checkbox']
];
function voiceGenerationSettings(voice) { return {...defaultGenerationSettings, ...(voice?.generation_settings || {})}; }
function settingsControls(container) {
  return Object.fromEntries(generationFields.map(([key]) => [key, container.querySelector(`[data-setting="${key}"]`)]));
}
function readGenerationSettings(container) {
  const controls = settingsControls(container);
  return Object.fromEntries(generationFields.map(([key, , type]) => {
    const input = controls[key];
    if (type === 'checkbox') return [key, input.checked];
    if (key === 'duration' && input.value.trim() === '') return [key, null];
    if (input.value.trim() === '') throw new Error(t('Enter a valid generation setting.'));
    return [key, Number(input.value)];
  }));
}
function applySettingsValues(container, values) {
  const controls = settingsControls(container);
  for (const [key, , type] of generationFields) {
    if (type === 'checkbox') controls[key].checked = Boolean(values[key]);
    else controls[key].value = values[key] ?? '';
  }
}
let appliedStudioPreset = '';
function applyStudioVoiceDefaults() {
  const voice = state.voices.find(v => v.id === $('voice-select').value);
  const snapshot = voiceGenerationSettings(voice);
  const identity = (voice?.id || '') + JSON.stringify(snapshot);
  if (identity === appliedStudioPreset) return;
  appliedStudioPreset = identity;
  applySettingsValues($('generate-form'), snapshot);
}
$('voice-select').addEventListener('change', applyStudioVoiceDefaults);
$('generate-form').addEventListener('submit', action(async event => {
  event.preventDefault(); if (busy) return;
  busy = true; $('generate').disabled = true; clearResult(); currentJob = null; suppressAutoplay = false;
  try {
    const voice = $('voice-select').value;
    if (!$('requester-name').value.trim()) { $('requester-name').focus(); throw new Error(t('Enter a requester name.')); }
    if (!voice) throw new Error(t('Choose a saved voice in Voices first.'));
    const job = await api(`/api/voices/${voice}/generate`, {method: 'POST', body: {text: $('text').value, language: $('language').value, ...readGenerationSettings($('generate-form')), autoqueue_general: $('autoqueue').checked, requester_name: $('requester-name').value.trim(), requester_id: requesterId}});
    currentJob = job.id; await watch(job.id);
  } finally { busy = false; $('generate').disabled = !runtimeSetup.ready; }
}));
async function cancelMonitoredJob() { if (lastMonitor && ['queued', 'running'].includes(lastMonitor.status)) { await api(`/api/jobs/${lastMonitor.id}/cancel`, {method: 'POST'}); await refresh(); } }
$('cancel-job').addEventListener('click', action(cancelMonitoredJob));
$('live-generation-cancel').addEventListener('click', action(cancelMonitoredJob));
$('view-monitor').addEventListener('click', () => { tab('studio'); $('monitor-source').scrollIntoView({behavior: 'smooth', block: 'center'}); });
$('panic').addEventListener('click', action(async () => { stopAllAudio(); await api('/api/panic', {method: 'POST'}); }));
$('cancel-all').addEventListener('click', action(async () => { stopAllAudio(); await api('/api/cancel-all', {method: 'POST'}); }));
document.addEventListener('keydown', action(async e => {
  const parts = (config?.hotkey || '').toUpperCase().split('+').map(p => p === 'CONTROL' ? 'CTRL' : p);
  if (parts.at(-1) === e.key.toUpperCase() && e.ctrlKey === parts.includes('CTRL') && e.altKey === parts.includes('ALT') && e.shiftKey === parts.includes('SHIFT')) {
    e.preventDefault(); stopAllAudio(); await api('/api/panic', {method: 'POST'});
  }
}));
$('voice-form').addEventListener('submit', action(async event => {
  event.preventDefault(); const submit = event.target.querySelector('[type=submit]'); submit.disabled = true;
  try { const voice = await api('/api/voices', {method: 'POST', body: new FormData(event.target)}); event.target.reset(); $('voice-upload-note').textContent = voice.warning ? t(voice.warning) : ''; $('voice-upload-note').hidden = !voice.warning; await refresh(); }
  finally { submit.disabled = false; }
}));
function createVoiceSettingsEditor(voice) {
  const values = voiceGenerationSettings(voice);
  const container = el('div', {class: 'settings voice-setting-fields'});
  for (const [key, label, type, min, max, step] of generationFields) {
    const input = el('input', {type, 'data-setting': key, 'aria-label': t(label), ...(type === 'number' ? {min, max, step, value: values[key] ?? ''} : {checked: values[key] ? '' : null})});
    const labelNode = type === 'checkbox'
      ? el('label', {class: 'check'}, input, ' ', t(label))
      : el('label', {}, t(label), input);
    container.append(labelNode);
  }
  const editor = el('details', {class: 'voice-generation-settings'},
    el('summary', {}, t('Voice generation defaults')),
    el('p', {class: 'muted'}, t('These defaults apply to Twitch commands and new manual generations.')),
    container, el('p', {class: 'muted'}, t('Duration overrides Speed when provided. Turning off output postprocessing avoids trimming trailing silence.')),
    button('Save generation defaults', async () => {
      await api(`/api/voices/${voice.id}/generation-settings`, {method: 'PUT', body: readGenerationSettings(editor)});
      editor.closest('.voice-card').dataset.settingsDirty = 'false';
      await refresh();
    })
  );
  editor.querySelectorAll('[data-setting]').forEach(input => input.addEventListener('input', () => { editor.closest('.voice-card').dataset.settingsDirty = 'true'; }));
  return editor;
}
function renderVoices() {
  const key = JSON.stringify([state.voices, state.jobs.filter(j => j.kind === 'transcribe' && ['queued', 'running'].includes(j.status)).map(j => [j.id, j.status, j.stage])]); if (key === voicesKey) return; voicesKey = key;
  const selected = $('voice-select').value;
  $('voice-select').replaceChildren(el('option', {value: ''}, t('Choose a saved voice')));
  for (const v of state.voices.filter(v => v.status === 'ready')) $('voice-select').append(el('option', {value: v.id}, v.title));
  $('voice-select').value = selected; $('voice-select').dispatchEvent(new Event('change'));
  const drafts = new Map([...document.querySelectorAll('.voice-card')].filter(card => card.dataset.dirty === 'true').map(card => [card.dataset.voiceId, {title: card.querySelector('input[data-field="title"]').value, transcript: card.querySelector('textarea').value}]));
  const editorDrafts = new Map([...document.querySelectorAll('.voice-card')].map(card => {
    const editor = card.querySelector('.voice-generation-settings');
    if (!editor) return [card.dataset.voiceId, null];
    const dirty = card.dataset.settingsDirty === 'true';
    return [card.dataset.voiceId, {open: editor.open, dirty, values: dirty ? Object.fromEntries(generationFields.map(([key, , type]) => {
      const input = editor.querySelector(`[data-setting="${key}"]`);
      return [key, type === 'checkbox' ? input.checked : input.value];
    })) : null}];
  }));
  $('voices-list').replaceChildren();
  for (const v of state.voices) {
    const preparing = v.status === 'pending';
    const prep = state.jobs.find(j => j.id === v.preparation_job_id);
    const title = el('input', {...(preparing ? {disabled: ''} : {}), value: v.title, maxlength: '100', 'data-field': 'title', 'aria-label': t('Voice title')});
    const transcript = el('textarea', {...(preparing ? {disabled: ''} : {}), rows: '3', maxlength: '4000', 'aria-label': t('Saved transcript')}); transcript.value = v.transcript || '';
    const thumbnailInput = el('input', {type: 'file', accept: 'image/png,image/jpeg,image/webp', 'aria-label': t('Replace thumbnail')});
    const thumbnailControl = el('label', {}, t('Add / replace thumbnail (up to 2 MiB)'), thumbnailInput);
    thumbnailInput.addEventListener('change', action(async () => { const file = thumbnailInput.files[0]; if (!file) return; const body = new FormData(); body.set('thumbnail', file); await api(`/api/voices/${v.id}/thumbnail`, {method: 'POST', body}); await refresh(); }));
    const card = el('section', {class: 'card voice-card', 'data-voice-id': v.id}, v.thumbnail_url ? el('img', {src: v.thumbnail_url, alt: v.title}) : null,
      el('h2', {}, v.title), el('p', {class: 'muted'}, v.original_filename), v.warning ? el('p', {class: 'notice'}, t(v.warning)) : null, thumbnailControl, el('span', {class: 'pill'}, t(v.status)),
      v.status === 'unprepared' ? el('p', {class: 'preparation-note'}, t('Not prepared for first use. Complete Initial Setup, then click Prepare to save the reference transcript locally.')) : null,
      preparing ? el('div', {class: 'preparation-note', role: 'status'}, el('strong', {}, t('Preparing for first use…')), el('progress', {max: '1'}), el('p', {}, `${t(prep?.stage || 'queued')} · ${t('Model files are already verified. Loading and transcription run locally. You can cancel and retry.')} `), button('Cancel preparation', async () => { await api(`/api/jobs/${v.preparation_job_id}/cancel`, {method: 'POST'}); await refresh(); }, 'danger small-button')) : null,
      v.error ? el('p', {class: 'error'}, v.error) : null, el('label', {}, t('Title'), title), el('label', {}, t('Saved reference transcript'), transcript),
      el('audio', {controls: '', src: `/api/voices/${v.id}/reference`, preload: 'none'}),
      createVoiceSettingsEditor(v),
      el('div', {class: 'row-actions'}, button('Save edits', async () => { await api(`/api/voices/${v.id}`, {method: 'PUT', body: {title: title.value, transcript: transcript.value}}); card.dataset.dirty = 'false'; await refresh(); }),
        v.status !== 'ready' && v.status !== 'pending' ? button(v.status === 'unprepared' ? 'Prepare for first use' : 'Retry preparation', async () => { await api(`/api/voices/${v.id}/prepare`, {method: 'POST'}); await refresh(); }) : null,
        button('Delete voice', async () => { if (confirm(t('Delete saved voice {name}?', {name: v.title}))) { await api(`/api/voices/${v.id}`, {method: 'DELETE'}); await refresh(); } }, 'danger small-button')));
    const draft = drafts.get(v.id);
    if (draft && !preparing) { title.value = draft.title; transcript.value = draft.transcript; card.dataset.dirty = 'true'; }
    const editorDraft = editorDrafts.get(v.id);
    if (editorDraft) {
      const editor = card.querySelector('.voice-generation-settings');
      editor.open = editorDraft.open;
      if (editorDraft.dirty) {
        applySettingsValues(editor, editorDraft.values);
        card.dataset.settingsDirty = 'true';
      }
    }
    for (const field of [title, transcript]) field.addEventListener('input', () => { card.dataset.dirty = 'true'; });
    card.querySelector('.row-actions button').disabled = preparing;
    $('voices-list').append(card);
  }
  window.Locale.bind($('prepare-voices'), state.voices.some(v => v.status !== 'ready') ? 'Some voices need preparation · open Voices' : 'Manage voices');
  if (!state.voices.length) $('voices-list').append(el('p', {class: 'muted'}, t('No saved voices yet.')));
}
function renderJobs() {
  const pending = state.jobs.filter(j => ['queued', 'running'].includes(j.status)).sort((a, b) => a.created_at - b.created_at);
  $('generation-queue').replaceChildren(...pending.map(j => el('div', {class: 'job-row'}, el('strong', {}, `${j.voice_title || j.original_filename || t('Uploaded voice')} · ${t(j.status)}`),
    el('p', {}, j.request.text), el('p', {class: 'muted'}, `${t(j.stage)} · ${j.elapsed_seconds || 0} s${j.channel ? ' · #' + j.channel : ''}`),
    button('Cancel generation', async () => { await api(`/api/jobs/${j.id}/cancel`, {method: 'POST'}); await refresh(); }))));
  if (!pending.length) $('generation-queue').textContent = t('No pending generations.');
}
function renderHistory() {
  const jobs = state.request_history || state.jobs;
  const key = JSON.stringify(jobs); if (key === historyKey) return; historyKey = key;
  $('history-list').replaceChildren();
  for (const j of jobs) {
    const preview = el('audio', {controls: '', preload: 'none', class: 'history-preview', hidden: ''});
    const actions = el('div', {class: 'row-actions'});
    if (j.output_url) {
      actions.append(button('Preview here', () => { preview.hidden = !preview.hidden; if (!preview.hidden) preview.src = j.output_url; else preview.pause(); }), link('Download MP3', j.output_url, true));
      actions.append(button('Queue on local OBS source', () => queueGeneral(j.id)));
      if (j.channel) actions.append(button('Replay on OBS', async () => { await api(`/api/channels/${j.channel}/replay/${j.id}`, {method: 'POST'}); }));
    }
    if (j.status !== 'blocked') actions.append(link('Timing report', `/api/jobs/${j.id}/report`, true));
    $('history-list').append(el('section', {class: 'card'}, el('strong', {}, `${j.voice_title || j.original_filename || t('Voice')} · ${t(j.status)}${j.channel ? ' · #' + j.channel : ''}`),
      el('p', {}, j.request.text), el('p', {class: 'muted'}, `${t('Requester ID')}: ${j.requester_id || t('Legacy request')} · ${t('Origin ID')}: ${j.origin_id || t('Legacy request')} · ${t(j.kind || 'speech')}`), el('p', {class: 'muted'}, `${j.requester_name || j.username || t('Local')} · ${t(j.origin || (j.channel ? 'twitch' : 'local'))} · ${new Date(j.created_at * 1000).toLocaleString(window.Locale.language === 'pt' ? 'pt-BR' : 'en-CA')} · ${j.elapsed_seconds} s ${t('elapsed')} · ${j.metrics?.worker_cpu_seconds ?? t('N/A')} ${t('worker CPU s')} · ${j.device || 'device N/A'}`),
      j.error ? el('p', {class: 'error'}, j.error) : null, j.playback_error ? el('p', {class: 'error'}, j.playback_error) : null, actions, preview,
      el('details', {}, el('summary', {}, t('Per-stage hardware accounting')), el('pre', {}, JSON.stringify(j.metrics, null, 2)))));
  }
}
function refreshCommandVoices() {
  for (const select of document.querySelectorAll('.command-row select')) {
    const selected = select.value;
    const ready = state.voices.filter(v => v.status === 'ready');
    const key = JSON.stringify([window.Locale.language, ready.map(v => [v.id, v.title])]);
    if (select.dataset.voicesKey === key) continue;
    select.dataset.voicesKey = key;
    select.replaceChildren(el('option', {value: ''}, t('Choose voice')));
    for (const voice of ready) select.append(el('option', {value: voice.id}, voice.title));
    select.value = ready.some(v => v.id === selected) ? selected : '';
    select.setAttribute('aria-label', t('Command voice'));
  }
}
function commandRow(keyword = '', voiceId = '') {
  const input = el('input', {placeholder: '!lula', value: keyword, pattern: '![a-zA-Z0-9_]{1,30}', required: '', 'aria-label': 'Command keyword'});
  const select = el('select', {'aria-label': 'Command voice', required: ''}, el('option', {value: ''}, t('Choose voice')));
  for (const voice of state.voices.filter(v => v.status === 'ready')) select.append(el('option', {value: voice.id}, voice.title));
  select.value = voiceId;
  const row = el('div', {class: 'command-row'}, input, select, button('Remove', () => row.remove()));
  $('commands-list').append(row);
}
$('add-command').addEventListener('click', () => commandRow());
function fillChannel(name) {
  selectedChannel = name;
  const c = state.channels.find(c => c.name === name);
  $('channel-name').value = c?.name || ''; $('channel-transport').value = c?.transport || 'irc';
  $('event-rules').replaceChildren(); for (const rule of c?.event_rules || []) eventRuleRow(rule); updateTwitchMode();
  $('channel-paused').checked = c?.paused || false; $('channel-delay').value = c?.delay_seconds ?? 5;
  $('channel-cooldown').value = c?.user_cooldown_seconds ?? 15; $('channel-limit').value = c?.max_message_chars ?? 300;
  $('channel-filter').value = c?.filter_level || 'slurs'; $('channel-custom').value = (c?.custom_filters || []).join('\n');
  $('commands-list').replaceChildren(); for (const [key, id] of Object.entries(c?.commands || {})) commandRow(key, id);
  if (!c) commandRow();
}
$('channel-select').addEventListener('change', () => fillChannel($('channel-select').value));
$('channel-form').addEventListener('submit', action(async event => {
  event.preventDefault(); $('channel-save-status').textContent = ''; const name = $('channel-name').value.trim().toLowerCase(); const commands = {};
  document.querySelectorAll('.command-row').forEach(row => { const key = row.querySelector('input').value.trim().toLowerCase(); if (commands[key]) throw new Error(t('Duplicate command keyword.')); commands[key] = row.querySelector('select').value; });
  await api(`/api/channels/${name}`, {method: 'PUT', body: {name, enabled: state.channels.find(c => c.name === name)?.enabled ?? true, paused: $('channel-paused').checked,
    transport: $('channel-transport').value, event_rules: $('channel-transport').value === 'oauth' ? readEventRules() : (state.channels.find(c => c.name === name)?.event_rules || []), commands, filter_level: $('channel-filter').value, custom_filters: $('channel-custom').value.split('\n').map(s => s.trim()).filter(Boolean),
    delay_seconds: Number($('channel-delay').value), user_cooldown_seconds: Number($('channel-cooldown').value), max_message_chars: Number($('channel-limit').value)}});
  selectedChannel = name; channelKey = ''; await refresh(); fillChannel(name); $('channel-save-status').textContent = t('Channel saved');
}));
$('pause-channel').addEventListener('click', action(async () => { if (selectedChannel) { await api(`/api/channels/${selectedChannel}/pause`, {method: 'POST', body: {paused: !latestChannelState?.paused}}); await refresh(); } }));
function renderChannels() {
  refreshCommandVoices();
  renderChannelDashboard();
  refreshEventVoices();
  const key = JSON.stringify(state.channels.map(c => ({name: c.name})));
  if (key !== channelKey) {
    channelKey = key; $('channel-select').replaceChildren(el('option', {value: ''}, t('Create a channel')));
    for (const c of state.channels) $('channel-select').append(el('option', {value: c.name}, c.name));
    $('channel-select').value = selectedChannel;
  }
  const c = selectedChannel === 'playbackMain' ? {name: 'playbackMain', connection: t('Local OBS Sources')} : state.channels.find(c => c.name === selectedChannel);
  $('channel-connection').textContent = c ? `${c.name}: ${t(c.connection)}${c.connection_error ? ' · ' + c.connection_error : ''}` : t('Choose a saved channel.');
  const playerUrl = c ? (session?.remote_access ? state.player_links?.[c.name] || `/${c.name}` : `/${c.name}`) : '';
  const linksKey = JSON.stringify([c?.name || '', playerUrl]);
  $('local-obs-player-link').href = session?.remote_access ? state.player_links?.playbackMain || '/playbackMain' : '/playbackMain';
  if (linksKey === channelLinksKey) return;
  channelLinksKey = linksKey;
  $('channel-links').replaceChildren();
  if (c) $('channel-links').append(el('p', {}, link('Open OBS player', playerUrl)), el('input', {readonly: '', value: new URL(playerUrl, location.origin).href, 'aria-label': 'OBS source URL'}),
    el('p', {}, link('Open separate control page', `/${c.name}/control`)));
}
async function renderChannelState() {
  if (!selectedChannel || (selectedChannel !== 'playbackMain' && !state.channels.some(c => c.name === selectedChannel))) return;
  const snap = await api(`/api/channels/${selectedChannel}/state`); latestChannelState = snap;
  $('channel-player-status').textContent = `${snap.paused ? t('Playback paused') : t('Playback enabled')} · ${snap.player_connected ? t('OBS player connected') : t('No active OBS player')}`;
  const pending = snap.items.filter(i => ['queued', 'countdown', 'ready', 'playing'].includes(i.status));
  $('channel-queue').replaceChildren(...pending.map(i => el('div', {class: 'job-row'}, el('strong', {}, `${i.voice_title} · ${t(i.status)}`), el('p', {}, `${i.username || t('Replay')}: ${i.text}`),
    i.deadline && i.status === 'countdown' ? el('p', {class: 'muted'}, t('Starts in {seconds} s', {seconds: Math.max(0, i.deadline - snap.server_time).toFixed(1)})) : null,
    button('Cancel audio', async () => { await api(`/api/playback/${i.id}/cancel`, {method: 'POST'}); await renderChannelState(); }))));
  renderTwitchEvents(snap.events || []);
  $('chat-events').replaceChildren(...snap.chat.map(c => el('div', {class: 'event-row'}, el('strong', {}, `${c.username} · ${c.accepted ? t('accepted') : t('blocked') + ': ' + t(c.reason)}`), el('p', {}, c.text))));
}
$('config-form').addEventListener('submit', action(async event => {
  event.preventDefault(); const value = {device: $('config-device').value, cpu_threads: Number($('config-threads').value), keep_model_loaded: $('config-resident').checked, hotkey: $('config-hotkey').value, max_queue: Number($('config-queue').value), vram_warning_mib: Number($('config-vram-warning').value)};
  const saved = await api('/api/config', {method: 'PUT', body: value}); config = saved;
  $('hotkey-status').textContent = t(saved.hotkey_status); $('health').textContent = t('Configuration saved. Model will load on the selected device for the next job.');
}));
async function refresh() {
  state = await api('/api/state');
  if (session?.remote_access) await runtimeStatus();
  const monitored = state.active_job || state.jobs.find(j => j.status === 'running') || state.jobs.filter(j => j.status === 'queued').sort((a, b) => a.created_at - b.created_at)[0] || [...state.jobs].sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at))[0];
  if (monitored) renderMonitor(monitored);
  renderResidency(); renderGlobalStatus();
  const latestAudio = state.jobs.filter(job => job.kind === 'speech' && job.status === 'succeeded' && job.output_url).sort((a, b) => b.finished_at - a.finished_at)[0];
  if (!busy && latestAudio && latestAudio.id !== completedJob && $('player').paused) showSharedResult(latestAudio);
  if (completedJob) autoqueueNote(state.jobs.find(j => j.id === completedJob));
  if (panicRevision !== null && panicRevision !== state.panic_revision) stopAllAudio();
  panicRevision = state.panic_revision;
  renderVoices(); renderJobs(); renderHistory(); renderChannels();
  $('hotkey-status').textContent = t(state.hotkey_status);
  await renderChannelState();
}
async function resources() {
  const data = await api('/api/resources'), r = data.live, gpu = r.gpus[0];
  $('gpu-pressure-warning').hidden = !data.gpu_warning;
  $('gpu-pressure-warning').textContent = data.gpu_warning ? t(data.gpu_warning.message) + ' ' + bytes(data.gpu_warning.free_bytes) + ' / ' + bytes(data.gpu_warning.threshold_bytes) : '';
  $('cpu').textContent = `${r.system_cpu_percent.toFixed(0)}%`;
  $('ram').textContent = data.worker_pid ? bytes(r.process_ram_bytes) : t('Worker unloaded');
  $('system-ram').textContent = `${bytes(r.system_ram_used_bytes)} / ${bytes(r.system_ram_total_bytes)}`;
  $('vram').textContent = gpu ? `${bytes(gpu.used_bytes)} / ${bytes(gpu.total_bytes)}` : t('N/A');
  $('gpu').textContent = gpu?.utilization_percent == null ? t('N/A') : `${gpu.utilization_percent}%`;
  $('hardware-description').textContent = JSON.stringify(data.hardware, null, 2);
}
async function init() {
  try {
    const shareKey = new URLSearchParams(location.hash.slice(1)).get('admin');
    if (shareKey) {
      const response = await fetch('/api/remote/session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: shareKey})});
      if (!response.ok) throw new Error('This share link has expired or is invalid.');
      history.replaceState(null, '', location.pathname + location.search);
    }
    session = await api('/api/session'); config = await api('/api/config');
    $('config-device').value = config.device === 'cpu' ? 'cuda' : config.device; $('config-threads').value = config.cpu_threads; $('config-resident').checked = config.keep_model_loaded;
    $('config-vram-warning').value = config.vram_warning_mib ?? 512; $('config-hotkey').value = config.hotkey; $('config-queue').value = config.max_queue;
    const health = await api('/api/health'); initialHealth = health;
    $('health').textContent = [health.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), health.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
    await runtimeStatus();
    if (!session?.remote_access && 'EventSource' in window) {
      const setupEvents = new EventSource('/api/setup/stream');
      setupEvents.onopen = () => { setupEventsConnected = true; };
      setupEvents.onmessage = event => {
        try { renderSetup(JSON.parse(event.data)); } catch (e) { console.warn('Setup stream:', e); }
      };
      setupEvents.onerror = () => { setupEventsConnected = false; };
    }
    await refresh();
    if (!selectedChannel && !$('commands-list').children.length) commandRow();
    await resources(); await tunnelStatus();
    // Initialization may finish after the user has opened a tab and edited a
    // channel. Never replace that draft with the persisted channel at this point.
    if (!userSelectedTab) {
      if (selectedChannel) {
        if (selectedChannel === 'playbackMain') tab('general');
        else { fillChannel(selectedChannel); tab('channels'); }
      } else tab(runtimeSetup.ready ? 'studio' : 'setup');
    }
    $('generate').disabled = !runtimeSetup.ready;
    const loop = async () => { try { if (!setupEventsConnected) await runtimeStatus(); await refresh(); } catch (e) { $('health').textContent = 'Connection interrupted: ' + e.message; } setTimeout(loop, document.hidden ? 2000 : 750); }; setTimeout(loop, 750);
    const monitor = async () => { try { await resources(); await tunnelStatus(); } catch { /* server may be restarting */ } setTimeout(monitor, 2000); }; setTimeout(monitor, 2000);
  } catch (e) { error(e.message); $('health').textContent = t('Could not initialize. Refresh after checking the server terminal.'); }
}
window.addEventListener('localechange', () => {
  if (completedJob) autoqueueNote(state.jobs.find(j => j.id === completedJob));
  const guide = $('bug-video').querySelector('iframe'); if (guide) guide.title = t('Bug reporting guide');
  document.querySelectorAll('.resources strong').forEach(node => { node.textContent = t(node.textContent); });
  $('hotkey-status').textContent = t(state.hotkey_status || '');
  const drafts = [...document.querySelectorAll('.voice-card')].map(card => ({id: card.dataset.voiceId, title: card.querySelector('input[data-field="title"]')?.value, transcript: card.querySelector('textarea')?.value}));
  voicesKey = historyKey = ''; renderVoices(); renderHistory(); renderJobs(); renderChannels();
  for (const d of drafts) { const card = [...document.querySelectorAll('.voice-card')].find(c => c.dataset.voiceId === d.id); if (card) { card.querySelector('input[data-field="title"]').value = d.title; card.querySelector('textarea').value = d.transcript; } }
  if (lastMonitor) renderMonitor(lastMonitor); renderResidency(); renderGlobalStatus();
  if (initialHealth) $('health').textContent = [initialHealth.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), initialHealth.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
  if (session) { renderChannelState().catch(() => {}); tunnelStatus().catch(() => {}); }
});
init();

async function tunnelStatus() {
  if (session?.remote_access || !runtimeSetup.ready) { $('tunnel-card').hidden = true; return; }
  try {
    const data = await api('/api/tunnel');
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
$('tunnel-start').addEventListener('click', action(async () => { await api('/api/tunnel/start', {method: 'POST'}); await tunnelStatus(); }));
$('tunnel-stop').addEventListener('click', action(async () => { await api('/api/tunnel/stop', {method: 'POST'}); await tunnelStatus(); }));

async function queueGeneral(id) {
  await api(`/api/channels/playbackMain/replay/${id}`, {method: 'POST'});
  $('playback-note').textContent = t('Queued on local OBS source.');
}
$('send-general').addEventListener('click', action(async () => { if (completedJob) await queueGeneral(completedJob); }));
$('general-form').addEventListener('submit', action(async event => {
  event.preventDefault();
  await api('/api/general-playback', {method: 'PUT', body: {name: 'general', delay_seconds: Number($('general-delay').value), filter_level: $('general-filter').value, custom_filters: $('general-custom').value.split('\n').map(s => s.trim()).filter(Boolean), paused: latestChannelState?.paused || false}});
  await refresh();
}));

$('prepare-voices').addEventListener('click', () => tab('voices'));

let countermeasurePromptOpen = false, countermeasureOfferPending = false;
function claimCountermeasures() {
  // The backend permanently claimed this prompt when it was displayed.
  countermeasurePromptOpen = false;
  $('setup-too-long').hidden = true;
}
function refreshCountermeasurePrompt() {
  const eligible = runtimeSetup.status === 'running' && !runtimeSetup.initial_setup_completed &&
    !runtimeSetup.countermeasures_offered && runtimeSetup.started_at &&
    Date.now() / 1000 - runtimeSetup.started_at >= 30;
  if (eligible && !countermeasureOfferPending && !countermeasurePromptOpen) {
    countermeasureOfferPending = true;
    api('/api/setup/countermeasures/offer', {method: 'POST'}).then(result => {
      if (result.offered && runtimeSetup.status === 'running') {
        countermeasurePromptOpen = true;
        $('setup-too-long').hidden = false;
      }
    }).catch(error => console.warn('Countermeasures prompt:', error))
      .finally(() => { countermeasureOfferPending = false; });
  }
  if (runtimeSetup.status !== 'running') countermeasurePromptOpen = false;
  $('setup-too-long').hidden = !countermeasurePromptOpen;
}
function closeCountermeasures() { $('countermeasure-modal').hidden = true; const video = $('countermeasure-video'); video.pause(); video.currentTime = 0; }
$('setup-too-long-no').addEventListener('click', claimCountermeasures);
$('setup-too-long-close').addEventListener('click', claimCountermeasures);
$('setup-too-long-yes').addEventListener('click', async () => {
  claimCountermeasures();
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
});
$('countermeasure-close').addEventListener('click', closeCountermeasures);

function renderSetup(data) {
  renderWeightDiscovery(data);
  renderOptionalImport(data);
  const wasReady = runtimeSetup.ready;
  runtimeSetup = data;
  document.querySelector('[data-tab="setup"]').hidden = data.ready && !showSetupTab;
  if (data.ready && !showSetupTab && !$('pane-setup').hidden) tab('config');
  if (modelSession !== data.started_at) { modelSession = data.started_at; modelDownloaded = 0; }
  if (data.stage === 'models' && data.download?.total_bytes) {
    modelDownloaded = Math.max(modelDownloaded, data.download.completed_bytes || 0);
  }
  document.querySelectorAll('[data-tab]').forEach(node => { node.disabled = !data.ready && !['setup', 'config'].includes(node.dataset.tab); });
  $('generate').disabled = busy || !data.ready;
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
    (d.total_bytes ? ` · total ${(100 * modelDownloaded / d.total_bytes).toFixed(1)}%` : '') +
    ` · ${d.reused_files || 0} ${t('verified cached files reused')}` :
    (isDependency ? 'Dependency progress appears above.' : 'Waiting for model downloads.');
  if (!data.ready && !setupAvailable) return;
  if (!data.ready && $('pane-config').hidden && (wasReady || !$('pane-setup').hidden)) tab('setup');
}
async function runtimeStatus() {
  if (session?.remote_access) { renderSetup({ready: state.setup_ready ?? session.setup_ready, status: 'host', stage: 'Waiting for host setup', ...(state.setup_activity || {})}); document.querySelector('[data-tab="setup"]').hidden = runtimeSetup.ready; $('setup-start').hidden = true; $('setup-cancel').hidden = true; $('setup-device').disabled = true; $('tunnel-card').hidden = true; return; }
  try { renderSetup(await api('/api/setup')); }
  catch (e) {
    // Shared administrators cannot install host software; generation remains
    // governed by the server readiness guard.
    if (e.status === 403 && session && location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') {
      setupAvailable = false; runtimeSetup = {ready: true};
      document.querySelector('[data-tab="setup"]').hidden = true;
    } else throw e;
  }
}
function setupAction(fn) { return async () => { try { await fn(); } catch (e) { $('setup-error').hidden = false; $('setup-error').textContent = t(e.message); } }; }
$('setup-start').addEventListener('click', setupAction(async () => {
  renderSetup(await api('/api/setup/start', {method: 'POST', body: {device: $('setup-device').value}}));
}));
$('setup-cancel').addEventListener('click', setupAction(async () => { renderSetup(await api('/api/setup/cancel', {method: 'POST'})); }));
window.addEventListener('localechange', () => { if (setupAvailable) renderSetup(runtimeSetup); });

function showSharedResult(job) {
  // A different browser or Twitch can finish this job. Expose its controls without
  // causing another speaker to autoplay or enqueue the same clip twice.
  completedJob = job.id;
  $('player').src = job.output_url; $('player').hidden = false; $('actions').hidden = false;
  $('download').href = job.output_url; $('download').download = `pactts-${job.id}.mp3`;
  $('result-source').textContent = `${job.voice_title || t('Voice')} · ${job.requester_name || job.username || t('Local')} · ${t(job.origin || 'local')}`;
  autoqueueNote(job);
}

function renderResidency() {
  const residency = state.model_residency || {};
  const active = state.active_job;
  const latest = [...(state.jobs || [])].sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at))[0];
  const lastFailure = latest?.status === 'failed' && /CUDA|GPU memory/i.test(latest.error || '') ? latest : null;
  const currentError = lastFailure && (!active || lastFailure.finished_at > active.created_at);
  $('cuda-status').textContent = currentError ? 'CUDA error: ' + lastFailure.error :
    active?.device === 'cuda' ? 'CUDA: active · ' + t(active.stage) :
    residency.loaded && residency.device === 'cuda' ? 'CUDA: model loaded on GPU · idle' :
    'CUDA: not checked · no model loaded. GPU utilization alone does not confirm CUDA.';

  const model = state.model_residency || {};
  const warm = Boolean(model.loaded);
  $('model-residency').textContent = `${model.model || 'k2-fsa/OmniVoice'} · ${t(warm ? 'Warm · loaded in memory' : 'Cold · not loaded')} · ${model.device || t('N/A')}`;
  $('voice-residency-list').replaceChildren(...state.voices.map(voice => el('p', {}, `${voice.title} · ${t(voice.status === 'ready' ? (warm ? 'Warm' : 'Cold') : 'Needs preparation')}`)));
}
function renderGlobalStatus() {
  $('live-generation').hidden = false;
  const running = state.active_job || state.jobs.find(job => job.status === 'running');
  if (runtimeSetup.import_status?.status === 'running') {
    $('live-generation-source').textContent = t('Import');
    $('live-generation-status').textContent = t(runtimeSetup.import_status.category === 'models' ? 'Importing model weights' : 'Importing personal data');
    $('live-generation-progress').removeAttribute('value');
    $('live-generation-timer').textContent = duration(Date.now() / 1000 - runtimeSetup.import_status.started_at);
    $('live-generation-cancel').hidden = true; return;
  }
  if (runtimeSetup.status === 'running') {
    $('live-generation-source').textContent = t('Initial Setup');
    $('live-generation-status').textContent = t(runtimeSetup.stage === 'models' ? 'Downloading / verifying models' : 'Installing dependencies') + ' · ' + t(runtimeSetup.stage || '');
    const d = runtimeSetup.download;
    if (d?.total_bytes) { $('live-generation-progress').value = Math.min(1, modelDownloaded / d.total_bytes); } else $('live-generation-progress').removeAttribute('value');
    $('live-generation-cancel').hidden = true; return;
  }
  if (running) { renderMonitor(running); return; }
  $('live-generation-source').textContent = t(runtimeSetup.ready ? 'Idle' : 'Initial Setup');
  $('live-generation-status').textContent = !runtimeSetup.ready ? t('Waiting for host setup') : state.jobs.some(job => job.status === 'queued') ? t('Waiting for queued work') : t('Ready for the next request');
  $('live-generation-progress').value = 0; $('live-generation-timer').textContent = '00:00.0'; $('live-generation-cancel').hidden = true;
}

function refreshDashboardQueues() {
  for (const channel of state.channels) {
    const list = document.querySelector(`[data-channel="${channel.name}"] [data-queue-items]`);
    if (!list) continue;
    const items = channel.playback_queue || [];
    const key = JSON.stringify(items);
    if (list.dataset.key === key) continue;
    list.dataset.key = key;
    list.parentElement.querySelector('summary').textContent = t('Queue') + ' · ' + items.length;
    list.replaceChildren(...(items.length ? items.map(item => el('div', {class: 'event-row'},
      el('strong', {}, t(item.status)), el('p', {}, item.text),
      button('Cancel audio', async () => { await api(`/api/playback/${item.id}/cancel`, {method: 'POST'}); await refresh(); }))) : [el('p', {}, t('Queue is empty'))]));
  }
}
$('config-show-setup').addEventListener('change', () => {
  showSetupTab = $('config-show-setup').checked;
  try { localStorage.setItem('pactts-show-setup', String(showSetupTab)); } catch {}
  renderSetup(runtimeSetup);
});
try { showSetupTab = localStorage.getItem('pactts-show-setup') === 'true'; } catch {}
$('config-show-setup').checked = showSetupTab;
function renderChannelDashboard() {
  const key = JSON.stringify([window.Locale.language, state.channels.map(({playback_queue, ...channel}) => channel), state.player_links]);
  if (channelDashboardKey === key) { refreshDashboardQueues(); return; }
  const expanded = new Set([...document.querySelectorAll('[data-channel] details[open][data-queue]')].map(node => node.closest('[data-channel]').dataset.channel));
  channelDashboardKey = key;
  $('channel-list').replaceChildren();
  for (const channel of state.channels) {
    const row = el('div', {class: 'job-row', 'data-channel': channel.name},
      el('strong', {}, '#' + channel.name + ' · IRC · ' + t(channel.enabled ? 'On' : 'Off')), el('p', {}, t(channel.connection) + (channel.connection_error ? ' · ' + t(channel.connection_error) : '')),
      channel.transport === 'oauth' ? el('p', {}, t('Twitch events') + ': ' + t(channel.event_connection) + (channel.event_connection_error ? ' · ' + t(channel.event_connection_error) : '')) : null,
      channel.transport === 'oauth' ? el('details', {}, el('summary', {}, t('Event subscriptions')), ...channel.event_subscriptions.map(name => el('p', {}, name)), ...Object.entries(channel.event_errors).map(([name, reason]) => el('p', {class: 'error'}, name + ': ' + t(reason))), channel.reward_recovery ? el('p', {class: 'error'}, channel.reward_recovery.error) : null, el('p', {class: 'muted'}, t('Events during connection gaps may be missed. Managed point redemptions are checked for refunds on reconnect.'))) : null,
      el('div', {class: 'row-actions'},
        button(channel.enabled ? 'Turn off' : 'Turn on', async () => {
          await api(`/api/channels/${channel.name}/connection`, {method: 'POST', body: {enabled: !channel.enabled}});
          await refresh(); if (selectedChannel === channel.name) fillChannel(channel.name);
        }),
        button(channel.paused ? 'Resume playback' : 'Pause playback', async () => {
          await api(`/api/channels/${channel.name}/pause`, {method: 'POST', body: {paused: !channel.paused}});
          await refresh();
        }),
        el('a', {href: session?.remote_access ? state.player_links?.[channel.name] || `/${channel.name}` : `/${channel.name}`, target: '_blank', rel: 'noopener noreferrer', class: 'download'}, t('Open OBS player')),
        button('Edit channel', () => fillChannel(channel.name)),
        button(channel.oauth_authorized ? 'Configure Twitch events' : 'Enable Bits, points and subscriptions', () => { fillChannel(channel.name); $('enable-twitch-events').click(); }),
        button('Delete channel', async () => {
          await api(`/api/channels/${channel.name}`, {method: 'DELETE'});
          if (selectedChannel === channel.name) { selectedChannel = ''; }
          await refresh(); fillChannel(selectedChannel);
        }, 'danger small-button')));
    const queue = el('details', {'data-queue': ''}, el('summary', {}, t('Queue')), el('div', {'data-queue-items': ''}));
    queue.open = expanded.has(channel.name);
    row.append(queue);
    $('channel-list').append(row);
  }
  refreshDashboardQueues();
  if (!state.channels.length) $('channel-list').textContent = t('No saved Twitch channels. Add one below.');
}


const eventNames = {reward: 'Channel Points reward', bits: 'Bits and Power-ups', subscribe: 'New subscription', gift: 'Gift subscriptions', resub: 'Resubscription message', subscription_end: 'Subscription ended', follow: 'New follower', raid: 'Incoming raid', online: 'Stream online', offline: 'Stream offline'};
const eventTemplates = {reward: '{text}', bits: '{username} used {bits} Bits. {text}', subscribe: 'Welcome {username}', gift: '{username} gifted {total} subscriptions', resub: '{username}: {text}', subscription_end: "{username}'s subscription ended", follow: 'Welcome {username}', raid: '{username} raided with {viewers} viewers', online: 'Stream is online', offline: 'Stream is offline'};
let twitchAuthChannel = '', twitchAuthPending = false, twitchAuthBusy = false;
function eventRuleRow(rule = {}) {
  const kind = el('select', {'aria-label': t('Event type')}, ...Object.entries(eventNames).map(([value, name]) => el('option', {value}, t(name))));
  kind.value = rule.kind || 'reward';
  const voice = el('select', {'aria-label': t('Event voice'), 'data-voice': ''});
  const reward = el('input', {'aria-label': t('Reward ID'), placeholder: t('Reward ID'), value: rule.reward_id || ''});
  const minimum = el('input', {type: 'number', min: '1', max: '10000000', 'aria-label': t('Minimum Bits'), value: rule.min_bits || 1});
  const template = el('textarea', {rows: '2', maxlength: '1000', 'aria-label': t('Event text template')}); template.value = rule.template || eventTemplates[kind.value];
  const row = el('section', {class: 'event-rule card'}, el('label', {}, t('Event type'), kind), el('label', {}, t('Event voice'), voice), el('label', {}, t('Reward ID'), reward), el('label', {}, t('Minimum Bits'), minimum), el('label', {}, t('Event text template'), template), button('Remove', () => row.remove()));
  const visibility = () => { reward.parentElement.hidden = kind.value !== 'reward'; minimum.parentElement.hidden = kind.value !== 'bits'; };
  let previousKind = kind.value;
  kind.addEventListener('change', () => { if (template.value === eventTemplates[previousKind]) template.value = eventTemplates[kind.value]; previousKind = kind.value; visibility(); }); visibility();
  $('event-rules').append(row); refreshEventVoices(); voice.value = rule.voice_id || '';
}
function refreshEventVoices() {
  for (const select of document.querySelectorAll('#event-rules [data-voice]')) {
    const key = JSON.stringify([window.Locale.language, state.voices.map(v => [v.id, v.title, v.status])]);
    if (select.dataset.key === key) continue;
    const selected = select.value; select.dataset.key = key;
    select.replaceChildren(el('option', {value: ''}, t('Choose voice')), ...state.voices.filter(v => v.status === 'ready').map(v => el('option', {value: v.id}, v.title))); select.value = selected;
  }
}
function readEventRules() {
  return [...document.querySelectorAll('.event-rule')].map(row => {
    const rule = {kind: row.querySelector('select').value, voice_id: row.querySelector('[data-voice]').value, reward_id: row.querySelector('input:not([type])').value.trim(), min_bits: Number(row.querySelector('input[type=number]').value), template: row.querySelector('textarea').value};
    if (!rule.voice_id) throw new Error(t('Choose a voice for each event rule.'));
    return rule;
  });
}
function updateTwitchMode() {
  const oauth = $('channel-transport').value === 'oauth';
  $('enable-twitch-events').hidden = oauth;
  $('disable-twitch-events').hidden = !oauth;
  $('event-rules-panel').hidden = !oauth;
  $('twitch-oauth-panel').hidden = !oauth || Boolean(session?.remote_access);
  twitchAuthChannel = ''; $('twitch-auth-status').textContent = ''; $('twitch-device').hidden = true; $('twitch-rewards').replaceChildren();
  if (oauth && !session?.remote_access && selectedChannel && state.channels.some(c => c.name === selectedChannel)) loadTwitchAuth().catch(e => { $('twitch-auth-status').textContent = t(e.message); });
}
async function loadTwitchAuth() {
  const channel = selectedChannel;
  if (!channel || session?.remote_access || twitchAuthBusy) return;
  twitchAuthBusy = true;
  try {
    const info = await api(`/api/twitch/${channel}/authorization`);
    if (channel !== selectedChannel) return;
    twitchAuthChannel = channel; twitchAuthPending = info.pending;
    $('twitch-auth-status').textContent = info.error || (info.pending ? t('Waiting for Twitch authorization…') : info.authorized ? t('Authorized broadcaster') + ': ' + info.login + ' · ' + info.scopes.join(', ') : t('Not authorized'));
    $('twitch-device').hidden = !info.pending; $('twitch-user-code').textContent = info.user_code || '';
    $('twitch-activate').href = info.verification_uri || 'https://www.twitch.tv/activate';
    $('twitch-authorize').disabled = Boolean(info.pending);
    if (info.authorized && !info.pending) await refresh();
  } finally { twitchAuthBusy = false; }
}
$('enable-twitch-events').addEventListener('click', () => { $('channel-transport').value = 'oauth'; updateTwitchMode(); $('twitch-oauth-panel').scrollIntoView({behavior: 'smooth', block: 'start'}); });
$('disable-twitch-events').addEventListener('click', () => { $('channel-transport').value = 'irc'; updateTwitchMode(); });
$('add-event-rule').addEventListener('click', () => eventRuleRow());
$('twitch-authorize').addEventListener('click', action(async () => {
  if (!selectedChannel || !state.channels.some(c => c.name === selectedChannel)) throw new Error(t('Save the channel first.'));
  await api(`/api/twitch/${selectedChannel}/authorization`, {method: 'POST', body: {features: [...$('twitch-features').querySelectorAll('input:checked')].map(n => n.value)}});
  await loadTwitchAuth();
}));
$('twitch-forget').addEventListener('click', action(async () => {
  if (selectedChannel) { await api(`/api/twitch/${selectedChannel}/authorization`, {method: 'DELETE'}); await loadTwitchAuth(); await refresh(); }
}));
const rewardLimitFields = [
  ['global_cooldown_seconds', 'Reward cooldown (seconds) · 0 disables', 604800],
  ['max_per_stream', 'Redemptions per stream · 0 disables', 2147483647],
  ['max_per_user_per_stream', 'Redemptions per user per stream · 0 disables', 2147483647]
];
function rewardLimitsEditor(reward = {}, disabled = false) {
  return el('div', {class: 'reward-limits'}, ...rewardLimitFields.map(([key, label, maximum]) =>
    el('label', {}, t(label), el('input', {type: 'number', min: '0', max: maximum, step: '1', value: reward[key] || 0, 'data-reward-limit': key, 'aria-label': t(label), ...(disabled ? {disabled: ''} : {})}))));
}
function readRewardLimits(container) {
  return Object.fromEntries([...container.querySelectorAll('[data-reward-limit]')].map(input => [input.dataset.rewardLimit, Number(input.value)]));
}
$('twitch-new-reward-limits').append(rewardLimitsEditor());
async function loadTwitchRewards() {
  const channel = selectedChannel; const rewards = await api(`/api/twitch/${channel}/rewards`);
  if (channel !== selectedChannel) return;
  $('twitch-rewards').replaceChildren(...rewards.map(r => {
    const limits = rewardLimitsEditor(r, !r.manageable);
    return el('div', {class: 'job-row', 'data-reward-id': r.id}, el('strong', {}, `${r.title} · ${r.cost}`), el('p', {class: 'muted'}, `${r.id} · ${t(r.manageable ? 'Automatic fulfillment / refund' : 'Manage in Twitch')}`), limits,
      r.manageable ? button('Save reward limits', async () => { await api(`/api/twitch/${channel}/rewards/${encodeURIComponent(r.id)}`, {method: 'PATCH', body: readRewardLimits(limits)}); if (channel === selectedChannel) await loadTwitchRewards(); }) : el('p', {}, t('Edit limits for this reward in Twitch.')),
      button('Use reward', () => eventRuleRow({kind: 'reward', reward_id: r.id})));
  }));
}
$('twitch-load-rewards').addEventListener('click', action(loadTwitchRewards));
$('twitch-create-reward').addEventListener('click', action(async () => {
  const channel = selectedChannel;
  const reward = await api(`/api/twitch/${channel}/rewards`, {method: 'POST', body: {title: $('twitch-reward-title').value, cost: Number($('twitch-reward-cost').value), ...readRewardLimits($('twitch-new-reward-limits'))}});
  if (channel !== selectedChannel) return;
  eventRuleRow({kind: 'reward', reward_id: reward.id}); await loadTwitchRewards();
}));
function renderTwitchEvents(events) {
  let panel = $('twitch-event-history');
  if (!panel) { panel = el('div', {id: 'twitch-event-history'}); $('chat-events').parentElement.append(panel); }
  panel.replaceChildren(...events.map(e => el('div', {class: 'event-row'}, el('strong', {}, `${t(eventNames[e.kind] || e.kind)} · ${e.username} · ${t(e.status)}`), el('p', {}, e.text), e.reason ? el('p', {class: 'error'}, t(e.reason)) : null, el('p', {class: 'muted'}, `${t('Redemption status')}: ${e.settlement}${e.settlement_error ? ' · ' + t(e.settlement_error) : ''}`))));
}
setInterval(() => { if (twitchAuthPending && twitchAuthChannel === selectedChannel && !session?.remote_access) loadTwitchAuth().catch(() => {}); }, 2000);
window.addEventListener('localechange', () => { refreshEventVoices(); });
window.addEventListener('localechange', () => {
  for (const row of document.querySelectorAll('.event-rule')) {
    const kind = row.querySelector('select');
    for (const option of kind.options) option.textContent = t(eventNames[option.value]);
    const fields = [kind, row.querySelector('[data-voice]'), row.querySelector('input:not([type])'), row.querySelector('input[type=number]'), row.querySelector('textarea')];
    ['Event type', 'Event voice', 'Reward ID', 'Minimum Bits', 'Event text template'].forEach((key, i) => { fields[i].setAttribute('aria-label', t(key)); fields[i].parentElement.firstChild.nodeValue = t(key); });
  }
});

function weightSearchRoots() { return $('weight-search-roots').value.split('\n').map(v => v.trim()).filter(Boolean); }
function renderWeightDiscovery(data) {
  $('weight-reuse-panel').hidden = Boolean(session?.remote_access);
  if (document.activeElement !== $('weight-search-roots') && !$('weight-search-roots').dataset.edited) $('weight-search-roots').value = (data.weight_search_roots || []).join('\n');
  const scan = data.weight_discovery || {status: 'idle', files: []};
  const running = scan.status === 'running';
  $('weight-scan').disabled = running || data.status === 'running';
  $('weight-scan-cancel').hidden = !running;
  $('weight-search-roots').disabled = running || data.status === 'running';
  $('weight-move').disabled = running || data.status === 'running';
  $('weight-scan-status').textContent = t('Model search') + ': ' + t(scan.status) + ' · ' + (scan.files || []).length + ' ' + t('candidate weights') + (scan.limited ? ' · ' + t('Search limit reached; add a more specific folder.') : '');
  if (data.weight_import?.files) $('weight-scan-status').textContent += ' · ' + t('Moved verified weights') + ': ' + formatTransferBytes(data.weight_import.moved_bytes || 0);
  const key = JSON.stringify(scan.files || []);
  if ($('weight-candidates').dataset.key !== key) {
    $('weight-candidates').dataset.key = key;
    $('weight-candidates').replaceChildren(...(scan.files || []).map(file => el('p', {class: 'muted'}, file.path + ' · ' + formatTransferBytes(file.size))));
  }
}
$('weight-search-roots').addEventListener('input', () => { $('weight-search-roots').dataset.edited = 'true'; });
$('weight-scan').addEventListener('click', importAction(async () => {
  renderSetup(await api('/api/setup/weights/scan', {method: 'POST', body: {search_roots: weightSearchRoots(), move_weights: $('weight-move').checked}}));
}));
$('weight-scan-cancel').addEventListener('click', importAction(async () => {
  renderSetup(await api('/api/setup/weights/cancel', {method: 'POST'}));
}));

function importAction(fn) { return async () => { try { await fn(); } catch (e) { $('optional-import-status').textContent = t(e.message); } }; }
$('weight-import').addEventListener('click', importAction(async () => {
  renderSetup(await api('/api/import/start', {method: 'POST', body: {category: 'models', search_roots: weightSearchRoots(), move_weights: $('weight-move').checked}}));
}));
$('personal-import').addEventListener('click', importAction(async () => {
  renderSetup(await api('/api/import/start', {method: 'POST', body: {category: 'personal', source: $('personal-import-source').value.trim(), sections: [...$('personal-import-sections').querySelectorAll('input:checked')].map(n => n.value), replace_config: $('personal-replace-config').checked}}));
}));
$('optional-import-cancel').addEventListener('click', importAction(async () => {
  renderSetup(await api('/api/import/cancel', {method: 'POST'}));
}));
function renderOptionalImport(data) {
  $('import-card').hidden = Boolean(session?.remote_access);
  const job = data.import_status || {status: 'idle'};
  const running = job.status === 'running';
  $('weight-import').disabled = running || data.status === 'running' || data.weight_discovery?.status === 'running';
  $('personal-import').disabled = running || data.status === 'running';
  $('optional-import-cancel').hidden = !running;
  $('optional-import-status').textContent = t('Import') + ': ' + t(job.status) + (job.error ? ' · ' + t(job.error) : '') + (job.bytes ? ' · ' + formatTransferBytes(job.bytes) : '');
  const result = job.result || {};
  const key = JSON.stringify(result);
  if ($('optional-import-result').dataset.key === key) return;
  $('optional-import-result').dataset.key = key;
  const notes = [];
  if (job.category === 'personal' && job.status === 'succeeded') {
    notes.push(`${t('Imported voices')}: ${result.voices || 0} · ${t('Imported audio')}: ${result.outputs || 0} · ${t('Imported channels')}: ${result.channels || 0}`);
    if (result.backup) notes.push(t('Current database backup') + ': ' + result.backup);
    notes.push(...(result.warnings || []));
  }
  if (job.category === 'models' && job.status === 'succeeded') {
    notes.push(t('Verified local weight files') + ': ' + (result.files || []).length);
    notes.push(t('Missing weights can be downloaded in Initial Setup.') + ' ' + (result.missing_weights || []).map(f => f.repo + '/' + f.file).join(', '));
    notes.push(t('Moved verified weights') + ': ' + (result.weight_import || []).filter(f => f.moved).length);
  }
  $('optional-import-result').replaceChildren(...notes.map(note => el('p', {class: 'muted'}, note)));
}
