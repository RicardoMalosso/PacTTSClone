// Pending generation queue and request history rendering.
import {api, refresh} from './api.js';
import {$, button, el, link, t} from './dom.js';
import {dashboard} from './state.js';
import {queueGeneral} from './studio.js';

function renderJobs() {
  const pending = dashboard.state.jobs.filter(j => ['queued', 'running'].includes(j.status)).sort((a, b) => a.created_at - b.created_at);
  $('generation-queue').replaceChildren(...pending.map(j => el('div', {class: 'job-row'}, el('strong', {}, `${j.voice_title || j.original_filename || t('Uploaded voice')} · ${t(j.status)}`),
    el('p', {}, j.request.text), el('p', {class: 'muted'}, `${t(j.stage)} · ${j.elapsed_seconds || 0} s${j.channel ? ' · #' + j.channel : ''}`),
    button('Cancel generation', async () => { await api(`/api/jobs/${j.id}/cancel`, {method: 'POST'}); await refresh(); }))));
  if (!pending.length) $('generation-queue').textContent = t('No pending generations.');
}

function renderHistory() {
  const jobs = dashboard.state.request_history || dashboard.state.jobs;
  const key = JSON.stringify(jobs); if (key === dashboard.historyKey) return; dashboard.historyKey = key;
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

export {renderHistory, renderJobs};
