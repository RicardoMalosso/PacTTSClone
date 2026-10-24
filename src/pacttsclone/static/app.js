'use strict';
const t = window.Locale.t;
let initialHealth = null;
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let session, state = {jobs: [], voices: [], channels: []}, config;
let selectedChannel = location.pathname.endsWith('/control') ? location.pathname.split('/')[1] : '';
let currentJob = null, busy = false, lastMonitor = null, lastMonitorAt = 0;
let voicesKey = '', historyKey = '', channelKey = '', latestChannelState = null, panicRevision = null, suppressAutoplay = false;
function stopAllAudio() { document.querySelectorAll('audio').forEach(a => { try { a.pause(); if (a.readyState) a.currentTime = 0; } catch { /* keep panic responsive for broken media */ } }); suppressAutoplay = true; }

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
function error(message) { $('error').textContent = t(message); $('error').hidden = false; }
function action(fn) { return async event => { try { await fn(event); } catch (e) { error(e.message); } }; }
function button(text, fn, cls = 'secondary small-button') { return window.Locale.bind(el('button', {type: 'button', class: cls, onclick: action(fn)}), text); }
function link(text, href, download = false) { return window.Locale.bind(el('a', {href, ...(download ? {download: ''} : {})}), text); }
function bytes(value) { return value == null ? t('N/A') : `${(value / 1073741824).toFixed(2)} GiB`; }
function duration(value) { const n = Math.max(0, value || 0); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${(n % 60).toFixed(1).padStart(4, '0')}`; }
async function api(url, options = {}) {
  const opts = {cache: 'no-store', ...options};
  opts.headers = {...options.headers};
  if ((opts.method || 'GET') !== 'GET') opts.headers['X-PacTTS-Token'] = session.token;
  if (opts.body && !(opts.body instanceof FormData)) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.body); }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(x => x.msg).join('; ') : 'Request failed.');
  }
  return response.json();
}
function tab(name) {
  document.querySelectorAll('.pane').forEach(p => { p.hidden = p.id !== 'pane-' + name; });
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
}
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => tab(b.dataset.tab)));
try { $('autoplay').checked = localStorage.getItem('pactts-autoplay') === 'true'; } catch { /* optional */ }
$('autoplay').addEventListener('change', () => { try { localStorage.setItem('pactts-autoplay', String($('autoplay').checked)); } catch { /* optional */ } });
$('text').addEventListener('input', () => { $('count').textContent = `${$('text').value.length} / 2000`; });
$('stop').addEventListener('click', () => { $('player').pause(); $('player').currentTime = 0; });
$('voice-select').addEventListener('change', () => {
  const voice = state.voices.find(v => v.id === $('voice-select').value);
  $('upload-fields').hidden = Boolean(voice);
  $('reference').required = !voice;
  $('preset-note').textContent = voice ? `${voice.original_filename} · ${t('saved transcript')}: ${voice.transcript}` : '';
});
function clearResult() {
  $('player').pause(); $('player').removeAttribute('src'); $('player').load();
  $('player').hidden = true; $('actions').hidden = true; $('error').hidden = true;
  $('playback-note').textContent = '';
}
function renderMonitor(job) {
  lastMonitor = job; lastMonitorAt = performance.now();
  $('status').textContent = job.error || `${t(job.stage)} · ${job.device || job.config?.device || t('pending device selection')}`;
  $('overall-progress').value = job.progress || 0;
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
  if (!lastMonitor) return;
  const delta = lastMonitor.status === 'running' ? (performance.now() - lastMonitorAt) / 1000 : 0;
  $('timer').textContent = duration(lastMonitor.elapsed_seconds + delta);
  $('stage-timer').textContent = `${((lastMonitor.stage_elapsed_seconds || 0) + delta).toFixed(1)} s`;
}, 100);
async function watch(id) {
  while (true) {
    const job = await api('/api/jobs/' + id); renderMonitor(job);
    if (job.status === 'failed' || job.status === 'cancelled') { currentJob = null; throw new Error(job.error || t('Generation cancelled.')); }
    if (job.status === 'succeeded') {
      $('status').textContent = t('MP3 ready · {seconds} s elapsed', {seconds: job.elapsed_seconds});
      $('player').src = job.output_url; $('player').hidden = false; $('actions').hidden = false;
      $('download').href = job.output_url; $('download').download = `pactts-${job.id}.mp3`;
      if ($('autoplay').checked && !suppressAutoplay) {
        try { await $('player').play(); }
        catch { $('playback-note').textContent = t('The browser blocked autoplay. Press play to listen.'); }
      }
      currentJob = null; return;
    }
    await sleep(500);
  }
}
$('generate-form').addEventListener('submit', action(async event => {
  event.preventDefault(); if (busy) return;
  busy = true; $('generate').disabled = true; clearResult(); currentJob = null; suppressAutoplay = false;
  try {
    const voice = $('voice-select').value;
    let job;
    if (voice) job = await api(`/api/voices/${voice}/generate`, {method: 'POST', body: {text: $('text').value, language: $('language').value, speed: Number($('speed').value), steps: Number($('steps').value)}});
    else {
      const file = $('reference').files[0];
      if (!file || !file.name.toLowerCase().endsWith('.mp3')) throw new Error('Choose an MP3 reference.');
      if (file.size > session.max_upload_bytes) throw new Error('MP3 exceeds 20 MiB.');
      job = await api('/api/jobs', {method: 'POST', body: new FormData($('generate-form'))});
    }
    currentJob = job.id; await watch(job.id);
  } finally { busy = false; $('generate').disabled = false; }
}));
$('cancel-job').addEventListener('click', action(async () => { if (currentJob) await api(`/api/jobs/${currentJob}/cancel`, {method: 'POST'}); }));
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
  try { await api('/api/voices', {method: 'POST', body: new FormData(event.target)}); event.target.reset(); await refresh(); }
  finally { submit.disabled = false; }
}));
function renderVoices() {
  const key = JSON.stringify(state.voices); if (key === voicesKey) return; voicesKey = key;
  const selected = $('voice-select').value;
  $('voice-select').replaceChildren(el('option', {value: ''}, t('Upload an MP3 instead')));
  for (const v of state.voices.filter(v => v.status === 'ready')) $('voice-select').append(el('option', {value: v.id}, v.title));
  $('voice-select').value = selected; $('voice-select').dispatchEvent(new Event('change'));
  $('voices-list').replaceChildren();
  for (const v of state.voices) {
    const title = el('input', {value: v.title, maxlength: '100', 'aria-label': t('Voice title')});
    const transcript = el('textarea', {rows: '3', maxlength: '4000', 'aria-label': t('Saved transcript')}); transcript.value = v.transcript || '';
    const card = el('section', {class: 'card voice-card', 'data-voice-id': v.id}, v.thumbnail_url ? el('img', {src: v.thumbnail_url, alt: v.title}) : null,
      el('h2', {}, v.title), el('p', {class: 'muted'}, v.original_filename), el('span', {class: 'pill'}, t(v.status)),
      v.error ? el('p', {class: 'error'}, v.error) : null, el('label', {}, t('Title'), title), el('label', {}, t('Saved reference transcript'), transcript),
      el('audio', {controls: '', src: `/api/voices/${v.id}/reference`, preload: 'none'}),
      el('div', {class: 'row-actions'}, button('Save edits', async () => { await api(`/api/voices/${v.id}`, {method: 'PUT', body: {title: title.value, transcript: transcript.value}}); await refresh(); }),
        v.status !== 'ready' && v.status !== 'pending' ? button('Retry transcription', async () => { await api(`/api/voices/${v.id}/prepare`, {method: 'POST'}); await refresh(); }) : null,
        button('Delete voice', async () => { if (confirm(t('Delete saved voice {name}?', {name: v.title}))) { await api(`/api/voices/${v.id}`, {method: 'DELETE'}); await refresh(); } }, 'danger small-button')));
    $('voices-list').append(card);
  }
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
  const jobs = state.jobs.filter(j => j.kind === 'speech' && ['succeeded', 'failed', 'cancelled'].includes(j.status));
  const key = JSON.stringify(jobs); if (key === historyKey) return; historyKey = key;
  $('history-list').replaceChildren();
  for (const j of jobs) {
    const preview = el('audio', {controls: '', preload: 'none', class: 'history-preview', hidden: ''});
    const actions = el('div', {class: 'row-actions'});
    if (j.output_url) {
      actions.append(button('Preview here', () => { preview.hidden = !preview.hidden; if (!preview.hidden) preview.src = j.output_url; else preview.pause(); }), link('Download MP3', j.output_url, true));
      if (j.channel) actions.append(button('Replay on OBS', async () => { await api(`/api/channels/${j.channel}/replay/${j.id}`, {method: 'POST'}); }));
    }
    actions.append(link('Timing report', `/api/jobs/${j.id}/report`, true));
    $('history-list').append(el('section', {class: 'card'}, el('strong', {}, `${j.voice_title || j.original_filename || t('Voice')} · ${t(j.status)}${j.channel ? ' · #' + j.channel : ''}`),
      el('p', {}, j.request.text), el('p', {class: 'muted'}, `${j.username || t('Local')} · ${new Date(j.created_at * 1000).toLocaleString(window.Locale.language === 'pt' ? 'pt-BR' : 'en-CA')} · ${j.elapsed_seconds} s ${t('elapsed')} · ${j.metrics?.worker_cpu_seconds ?? t('N/A')} ${t('worker CPU s')} · ${j.device || 'device N/A'}`),
      j.error ? el('p', {class: 'error'}, j.error) : null, j.playback_error ? el('p', {class: 'error'}, j.playback_error) : null, actions, preview,
      el('details', {}, el('summary', {}, t('Per-stage hardware accounting')), el('pre', {}, JSON.stringify(j.metrics, null, 2)))));
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
  $('channel-name').value = c?.name || ''; $('channel-enabled').checked = c?.enabled || false;
  $('channel-paused').checked = c?.paused || false; $('channel-delay').value = c?.delay_seconds ?? 5;
  $('channel-cooldown').value = c?.user_cooldown_seconds ?? 15; $('channel-limit').value = c?.max_message_chars ?? 300;
  $('channel-filter').value = c?.filter_level || 'slurs'; $('channel-custom').value = (c?.custom_filters || []).join('\n');
  $('commands-list').replaceChildren(); for (const [key, id] of Object.entries(c?.commands || {})) commandRow(key, id);
  if (!c) commandRow();
}
$('channel-select').addEventListener('change', () => fillChannel($('channel-select').value));
$('channel-form').addEventListener('submit', action(async event => {
  event.preventDefault(); const name = $('channel-name').value.trim().toLowerCase(); const commands = {};
  document.querySelectorAll('.command-row').forEach(row => { const key = row.querySelector('input').value.trim().toLowerCase(); if (commands[key]) throw new Error(t('Duplicate command keyword.')); commands[key] = row.querySelector('select').value; });
  await api(`/api/channels/${name}`, {method: 'PUT', body: {name, enabled: $('channel-enabled').checked, paused: $('channel-paused').checked,
    commands, filter_level: $('channel-filter').value, custom_filters: $('channel-custom').value.split('\n').map(s => s.trim()).filter(Boolean),
    delay_seconds: Number($('channel-delay').value), user_cooldown_seconds: Number($('channel-cooldown').value), max_message_chars: Number($('channel-limit').value)}});
  selectedChannel = name; channelKey = ''; await refresh(); fillChannel(name);
}));
$('pause-channel').addEventListener('click', action(async () => { if (selectedChannel) { await api(`/api/channels/${selectedChannel}/pause`, {method: 'POST', body: {paused: !latestChannelState?.paused}}); await refresh(); } }));
function renderChannels() {
  const key = JSON.stringify(state.channels.map(c => ({name: c.name})));
  if (key !== channelKey) {
    channelKey = key; $('channel-select').replaceChildren(el('option', {value: ''}, t('Create a channel')));
    for (const c of state.channels) $('channel-select').append(el('option', {value: c.name}, c.name));
    $('channel-select').value = selectedChannel;
  }
  const c = state.channels.find(c => c.name === selectedChannel);
  $('channel-connection').textContent = c ? `${c.name}: ${t(c.connection)}${c.connection_error ? ' · ' + c.connection_error : ''}` : t('Choose a saved channel.');
  $('channel-links').replaceChildren();
  if (c) $('channel-links').append(el('p', {}, link('Open OBS player', `/${c.name}`)), el('input', {readonly: '', value: `${location.origin}/${c.name}`, 'aria-label': 'OBS source URL'}),
    el('p', {}, link('Open separate control page', `/${c.name}/control`)));
}
async function renderChannelState() {
  if (!selectedChannel || !state.channels.some(c => c.name === selectedChannel)) return;
  const snap = await api(`/api/channels/${selectedChannel}/state`); latestChannelState = snap;
  $('channel-player-status').textContent = `${snap.paused ? t('Playback paused') : t('Playback enabled')} · ${snap.player_connected ? t('OBS player connected') : t('No active OBS player')}`;
  const pending = snap.items.filter(i => ['queued', 'countdown', 'ready', 'playing'].includes(i.status));
  $('channel-queue').replaceChildren(...pending.map(i => el('div', {class: 'job-row'}, el('strong', {}, `${i.voice_title} · ${t(i.status)}`), el('p', {}, `${i.username || t('Replay')}: ${i.text}`),
    i.deadline && i.status === 'countdown' ? el('p', {class: 'muted'}, t('Starts in {seconds} s', {seconds: Math.max(0, i.deadline - snap.server_time).toFixed(1)})) : null,
    button('Cancel audio', async () => { await api(`/api/playback/${i.id}/cancel`, {method: 'POST'}); await renderChannelState(); }))));
  $('chat-events').replaceChildren(...snap.chat.map(c => el('div', {class: 'event-row'}, el('strong', {}, `${c.username} · ${c.accepted ? t('accepted') : t('blocked') + ': ' + t(c.reason)}`), el('p', {}, c.text))));
}
$('config-form').addEventListener('submit', action(async event => {
  event.preventDefault(); const value = {device: $('config-device').value, cpu_threads: Number($('config-threads').value), keep_model_loaded: $('config-resident').checked, hotkey: $('config-hotkey').value, max_queue: Number($('config-queue').value)};
  const saved = await api('/api/config', {method: 'PUT', body: value}); config = saved;
  $('hotkey-status').textContent = t(saved.hotkey_status); $('health').textContent = t('Configuration saved. Model will load on the selected device for the next job.');
}));
async function refresh() {
  state = await api('/api/state');
  if (panicRevision !== null && panicRevision !== state.panic_revision) stopAllAudio();
  panicRevision = state.panic_revision;
  renderVoices(); renderJobs(); renderHistory(); renderChannels();
  $('hotkey-status').textContent = t(state.hotkey_status);
  await renderChannelState();
}
async function resources() {
  const data = await api('/api/resources'), r = data.live, gpu = r.gpus[0];
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
    $('config-device').value = config.device; $('config-threads').value = config.cpu_threads; $('config-resident').checked = config.keep_model_loaded;
    $('config-hotkey').value = config.hotkey; $('config-queue').value = config.max_queue;
    const health = await api('/api/health'); initialHealth = health;
    $('health').textContent = [health.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), health.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
    await refresh(); await resources(); await tunnelStatus(); if (selectedChannel) { fillChannel(selectedChannel); tab('channels'); } else commandRow();
    $('generate').disabled = false;
    const loop = async () => { try { await refresh(); } catch (e) { $('health').textContent = 'Connection interrupted: ' + e.message; } setTimeout(loop, document.hidden ? 2000 : 750); }; setTimeout(loop, 750);
    const monitor = async () => { try { await resources(); await tunnelStatus(); } catch { /* server may be restarting */ } setTimeout(monitor, 2000); }; setTimeout(monitor, 2000);
  } catch (e) { error(e.message); $('health').textContent = t('Could not initialize. Refresh after checking the server terminal.'); }
}
window.addEventListener('localechange', () => {
  document.querySelectorAll('.resources strong').forEach(node => { node.textContent = t(node.textContent); });
  $('hotkey-status').textContent = t(state.hotkey_status || '');
  const drafts = [...document.querySelectorAll('.voice-card')].map(card => ({id: card.dataset.voiceId, title: card.querySelector('input')?.value, transcript: card.querySelector('textarea')?.value}));
  voicesKey = historyKey = ''; renderVoices(); renderHistory(); renderJobs(); renderChannels();
  for (const d of drafts) { const card = [...document.querySelectorAll('.voice-card')].find(c => c.dataset.voiceId === d.id); if (card) { card.querySelector('input').value = d.title; card.querySelector('textarea').value = d.transcript; } }
  if (lastMonitor) renderMonitor(lastMonitor);
  if (initialHealth) $('health').textContent = [initialHealth.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), initialHealth.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
  if (session) { renderChannelState().catch(() => {}); tunnelStatus().catch(() => {}); }
});
init();

async function tunnelStatus() {
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
