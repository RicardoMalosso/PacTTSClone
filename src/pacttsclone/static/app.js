'use strict';
const t = window.Locale.t;
let initialHealth = null;
let runtimeSetup = {ready: false}, setupAvailable = true;
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let session, state = {jobs: [], voices: [], channels: []}, config;
let selectedChannel = location.pathname.endsWith('/control') ? location.pathname.split('/')[1] : '';
let bugVideoTimer = null, bugVideoOpen = false;
let completedJob = null;
let currentJob = null, busy = false, lastMonitor = null, lastMonitorAt = 0;
let voicesKey = '', historyKey = '', channelKey = '', channelLinksKey = '', channelDashboardKey = '', latestChannelState = null, panicRevision = null, suppressAutoplay = false;
function stopAllAudio() { stopBugVideo(); document.querySelectorAll('audio').forEach(a => { try { a.pause(); if (a.readyState) a.currentTime = 0; } catch { /* keep panic responsive for broken media */ } }); suppressAutoplay = true; }

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
function link(text, href, download = false) { return window.Locale.bind(el('a', {href, ...(download ? {download: ''} : {target: '_blank', rel: 'noopener noreferrer'})}), text); }
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
    const error = new Error(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(x => x.msg).join('; ') : 'Request failed.');
    error.status = response.status; throw error;
  }
  return response.json();
}
function stopBugVideo() {
  clearTimeout(bugVideoTimer); bugVideoTimer = null; bugVideoOpen = false;
  $('bug-video').replaceChildren();
  window.Locale.bind($('bug-video-status'), 'The video loads three seconds after you open this tab.');
}
function openBugVideo() {
  if (bugVideoOpen) return;
  bugVideoOpen = true;
  window.Locale.bind($('bug-video-status'), 'Starting the video in three seconds…');
  bugVideoTimer = setTimeout(() => {
    bugVideoTimer = null;
    if (!bugVideoOpen || $('pane-bugs').hidden) return;
    $('bug-video').append(el('iframe', {
      src: 'https://www.youtube-nocookie.com/embed/b2eEl2oKXLA?autoplay=1&rel=0',
      title: t('Bug reporting guide'), allow: 'autoplay; encrypted-media; picture-in-picture; fullscreen',
      allowfullscreen: '', referrerpolicy: 'strict-origin-when-cross-origin'
    }));
    window.Locale.bind($('bug-video-status'), 'If autoplay is blocked, press play in the video.');
  }, 3000);
}
function tab(name) {
  if (!runtimeSetup.ready && name !== 'setup') name = 'setup';
  window.Locale.apply();
  if (name === 'bugs') openBugVideo(); else stopBugVideo();
  const general = name === 'general';
  if (general) selectedChannel = 'playbackMain';
  else if (name === 'channels' && selectedChannel === 'playbackMain') fillChannel('');
  window.Locale.bind($('playback-heading'), general ? 'Local OBS Sources' : 'Twitch & OBS');
  window.Locale.bind($('playback-description'), general ? 'Queue any generated MP3 here without connecting to Twitch.' : 'Read public Twitch chat. Commands queue local speech; this does not verify Bits or channel-point purchases.');
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
  const pane = general ? 'channels' : name;
  document.querySelectorAll('.pane').forEach(p => { p.hidden = p.id !== 'pane-' + pane; });
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
}
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => tab(b.dataset.tab)));
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
  const source = [job.channel ? `Twitch · #${job.channel}${job.username ? ' · ' + job.username : ''}` : t('Local request'), voice?.title || job.voice_title || job.original_filename, job.kind === 'transcribe' ? t('Voice preparation') : t('Generate speech')].filter(Boolean).join(' · ');
  $('monitor-source').textContent = source; $('live-generation-source').textContent = source;
  $('live-generation').hidden = !runtimeSetup.ready;
  $('status').textContent = job.error || (job.status === 'succeeded' ? (job.kind === 'transcribe' ? t('Voice preparation ready') : t('MP3 ready · {seconds} s elapsed', {seconds: job.elapsed_seconds})) : `${t(job.stage)} · ${job.device || job.config?.device || t('pending device selection')}`);
  $('live-generation-status').textContent = $('status').textContent;
  $('live-generation-cancel').hidden = !['queued', 'running'].includes(job.status);
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
  $('timer').textContent = duration((lastMonitor.elapsed_seconds || 0) + delta);
  $('live-generation-timer').textContent = $('timer').textContent;
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
      completedJob = job.id; autoqueueNote(job); currentJob = null; return;
    }
    await sleep(500);
  }
}
$('generate-form').addEventListener('submit', action(async event => {
  event.preventDefault(); if (busy) return;
  busy = true; $('generate').disabled = true; clearResult(); currentJob = null; suppressAutoplay = false;
  try {
    const voice = $('voice-select').value;
    if (!voice) throw new Error(t('Choose a saved voice in Voices first.'));
    const job = await api(`/api/voices/${voice}/generate`, {method: 'POST', body: {text: $('text').value, language: $('language').value, speed: Number($('speed').value), steps: Number($('steps').value), autoqueue_general: $('autoqueue').checked}});
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
function renderVoices() {
  const key = JSON.stringify([state.voices, state.jobs.filter(j => j.kind === 'transcribe' && ['queued', 'running'].includes(j.status)).map(j => [j.id, j.status, j.stage])]); if (key === voicesKey) return; voicesKey = key;
  const selected = $('voice-select').value;
  $('voice-select').replaceChildren(el('option', {value: ''}, t('Choose a saved voice')));
  for (const v of state.voices.filter(v => v.status === 'ready')) $('voice-select').append(el('option', {value: v.id}, v.title));
  $('voice-select').value = selected; $('voice-select').dispatchEvent(new Event('change'));
  const drafts = new Map([...document.querySelectorAll('.voice-card')].filter(card => card.dataset.dirty === 'true').map(card => [card.dataset.voiceId, {title: card.querySelector('input[data-field="title"]').value, transcript: card.querySelector('textarea').value}]));
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
      el('div', {class: 'row-actions'}, button('Save edits', async () => { await api(`/api/voices/${v.id}`, {method: 'PUT', body: {title: title.value, transcript: transcript.value}}); card.dataset.dirty = 'false'; await refresh(); }),
        v.status !== 'ready' && v.status !== 'pending' ? button(v.status === 'unprepared' ? 'Prepare for first use' : 'Retry preparation', async () => { await api(`/api/voices/${v.id}/prepare`, {method: 'POST'}); await refresh(); }) : null,
        button('Delete voice', async () => { if (confirm(t('Delete saved voice {name}?', {name: v.title}))) { await api(`/api/voices/${v.id}`, {method: 'DELETE'}); await refresh(); } }, 'danger small-button')));
    const draft = drafts.get(v.id);
    if (draft && !preparing) { title.value = draft.title; transcript.value = draft.transcript; card.dataset.dirty = 'true'; }
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
  const jobs = state.jobs.filter(j => j.kind === 'speech' && ['succeeded', 'failed', 'cancelled'].includes(j.status));
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
    actions.append(link('Timing report', `/api/jobs/${j.id}/report`, true));
    $('history-list').append(el('section', {class: 'card'}, el('strong', {}, `${j.voice_title || j.original_filename || t('Voice')} · ${t(j.status)}${j.channel ? ' · #' + j.channel : ''}`),
      el('p', {}, j.request.text), el('p', {class: 'muted'}, `${j.username || t('Local')} · ${new Date(j.created_at * 1000).toLocaleString(window.Locale.language === 'pt' ? 'pt-BR' : 'en-CA')} · ${j.elapsed_seconds} s ${t('elapsed')} · ${j.metrics?.worker_cpu_seconds ?? t('N/A')} ${t('worker CPU s')} · ${j.device || 'device N/A'}`),
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
  refreshCommandVoices();
  renderChannelDashboard();
  const key = JSON.stringify(state.channels.map(c => ({name: c.name})));
  if (key !== channelKey) {
    channelKey = key; $('channel-select').replaceChildren(el('option', {value: ''}, t('Create a channel')));
    for (const c of state.channels) $('channel-select').append(el('option', {value: c.name}, c.name));
    $('channel-select').value = selectedChannel;
  }
  const c = selectedChannel === 'playbackMain' ? {name: 'playbackMain', connection: t('Local OBS Sources')} : state.channels.find(c => c.name === selectedChannel);
  $('channel-connection').textContent = c ? `${c.name}: ${t(c.connection)}${c.connection_error ? ' · ' + c.connection_error : ''}` : t('Choose a saved channel.');
  const linksKey = c?.name || '';
  if (linksKey === channelLinksKey) return;
  channelLinksKey = linksKey;
  $('channel-links').replaceChildren();
  if (c) $('channel-links').append(el('p', {}, link('Open OBS player', `/${c.name}`)), el('input', {readonly: '', value: `${location.origin}/${c.name}`, 'aria-label': 'OBS source URL'}),
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
  $('chat-events').replaceChildren(...snap.chat.map(c => el('div', {class: 'event-row'}, el('strong', {}, `${c.username} · ${c.accepted ? t('accepted') : t('blocked') + ': ' + t(c.reason)}`), el('p', {}, c.text))));
}
$('config-form').addEventListener('submit', action(async event => {
  event.preventDefault(); const value = {device: $('config-device').value, cpu_threads: Number($('config-threads').value), keep_model_loaded: $('config-resident').checked, hotkey: $('config-hotkey').value, max_queue: Number($('config-queue').value)};
  const saved = await api('/api/config', {method: 'PUT', body: value}); config = saved;
  $('hotkey-status').textContent = t(saved.hotkey_status); $('health').textContent = t('Configuration saved. Model will load on the selected device for the next job.');
}));
async function refresh() {
  state = await api('/api/state');
  const monitored = state.active_job || state.jobs.find(j => j.status === 'running') || state.jobs.filter(j => j.status === 'queued').sort((a, b) => a.created_at - b.created_at)[0] || [...state.jobs].sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at))[0];
  if (monitored) renderMonitor(monitored);
  if (completedJob) autoqueueNote(state.jobs.find(j => j.id === completedJob));
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
    await runtimeStatus(); await refresh(); await resources(); await tunnelStatus(); if (selectedChannel) { if (selectedChannel === 'playbackMain') tab('general'); else { fillChannel(selectedChannel); tab('channels'); } } else { commandRow(); tab(runtimeSetup.ready ? 'studio' : 'setup'); }
    $('generate').disabled = !runtimeSetup.ready;
    const loop = async () => { try { await runtimeStatus(); await refresh(); } catch (e) { $('health').textContent = 'Connection interrupted: ' + e.message; } setTimeout(loop, document.hidden ? 2000 : 750); }; setTimeout(loop, 750);
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
  if (lastMonitor) renderMonitor(lastMonitor);
  if (initialHealth) $('health').textContent = [initialHealth.ffmpeg_available ? t('FFmpeg ready') : t('FFmpeg missing from PATH'), initialHealth.inference_installed ? t('Inference dependencies installed') : t('Install inference dependencies'), t('Initial model download can take time')].join(' · ');
  if (session) { renderChannelState().catch(() => {}); tunnelStatus().catch(() => {}); }
});
init();

async function tunnelStatus() {
  if (!runtimeSetup.ready) { $('tunnel-card').hidden = true; return; }
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

function renderSetup(data) {
  const wasReady = runtimeSetup.ready;
  runtimeSetup = data;
  document.querySelectorAll('[data-tab]').forEach(node => { node.disabled = !data.ready && node.dataset.tab !== 'setup'; });
  $('generate').disabled = busy || !data.ready;
  $('live-generation').hidden = !data.ready || !lastMonitor;
  $('tunnel-card').hidden = !data.ready;
  $('setup-start').disabled = data.status === 'running';
  $('setup-cancel').hidden = data.status !== 'running';
  $('setup-device').disabled = data.status === 'running';
  $('setup-progress').value = data.completed_steps || 0;
  $('setup-status').textContent = data.ready ? t('Setup ready. You can open the studio.') : t('Setup stage: ') + t(data.stage || 'idle');
  $('setup-error').hidden = !data.error;
  $('setup-error').textContent = data.error ? t(data.error) : '';
  $('setup-log').textContent = (data.lines || []).join('\n');
  const d = data.download;
  $('setup-file-progress').hidden = !d;
  if (d) { $('setup-file-progress').max = d.file_total || 1; $('setup-file-progress').value = d.file_bytes || 0; }
  $('setup-download-status').textContent = d ? `${d.repo} · ${d.file} · ${t(d.phase || d.cache_status || 'checking cache')} · ${bytes(d.file_bytes)} / ${bytes(d.file_total)} · ${d.reused_files || 0} ${t('verified cached files reused')}` : t('Package installation has no reliable byte total; technical details show actual activity.');
  if (!data.ready && !setupAvailable) return;
  if (!data.ready && (wasReady || !$('pane-setup').hidden)) tab('setup');
}
async function runtimeStatus() {
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

function renderChannelDashboard() {
  const key = JSON.stringify([window.Locale.language, state.channels]);
  if (channelDashboardKey === key) return;
  channelDashboardKey = key;
  $('channel-list').replaceChildren();
  for (const channel of state.channels) {
    const row = el('div', {class: 'job-row', 'data-channel': channel.name},
      el('strong', {}, '#' + channel.name), el('p', {}, t(channel.connection) + (channel.connection_error ? ' · ' + channel.connection_error : '')),
      el('div', {class: 'row-actions'},
        button(channel.enabled ? 'Disconnect' : 'Connect', async () => {
          await api(`/api/channels/${channel.name}/connection`, {method: 'POST', body: {enabled: !channel.enabled}});
          await refresh(); if (selectedChannel === channel.name) fillChannel(channel.name);
        }),
        button('Edit channel', () => fillChannel(channel.name)),
        button('Delete channel', async () => {
          await api(`/api/channels/${channel.name}`, {method: 'DELETE'});
          if (selectedChannel === channel.name) { selectedChannel = ''; }
          await refresh(); fillChannel(selectedChannel);
        }, 'danger small-button')));
    $('channel-list').append(row);
  }
  if (!state.channels.length) $('channel-list').textContent = t('No saved Twitch channels. Add one below.');
}
