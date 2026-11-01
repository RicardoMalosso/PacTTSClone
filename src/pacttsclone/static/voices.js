// Saved-voice upload, preparation, editing, and draft-preserving rendering.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {readKittenOptions} from './engines.js';
import {applySettingsValues, createVoiceSettingsEditor, generationFields, voiceAvailable} from './generation-settings.js';
import {tab} from './navigation.js';
import {dashboard} from './state.js';

function renderVoices() {
  const key = JSON.stringify([dashboard.state.active_engine, dashboard.state.voices, dashboard.state.jobs.filter(j => j.kind === 'transcribe' && ['queued', 'running'].includes(j.status)).map(j => [j.id, j.status, j.stage])]); if (key === dashboard.voicesKey) return; dashboard.voicesKey = key;
  const selected = $('voice-select').value;
  $('voice-select').replaceChildren(el('option', {value: ''}, t('Choose a saved voice')));
  for (const v of dashboard.state.voices.filter(voiceAvailable)) $('voice-select').append(el('option', {value: v.id}, v.title));
  $('voice-select').value = selected; $('voice-select').dispatchEvent(new Event('change'));
  const drafts = new Map([...document.querySelectorAll('.voice-card')].filter(card => card.dataset.dirty === 'true').map(card => [card.dataset.voiceId, {title: card.querySelector('input[data-field="title"]').value, transcript: card.querySelector('textarea').value}]));
  const editorDrafts = new Map([...document.querySelectorAll('.voice-card')].map(card => {
    const editor = card.querySelector('.voice-generation-settings');
    if (!editor) return [card.dataset.voiceId, null];
    const dirty = card.dataset.settingsDirty === 'true' && (editor.dataset.engine || 'omnivoice') === (dashboard.state.active_engine || 'omnivoice');
    const values = dirty ? Object.fromEntries(generationFields.map(([key, , type]) => {
      const input = editor.querySelector(`[data-setting="${key}"]`);
      return [key, type === 'checkbox' ? input.checked : input.value];
    })) : null;
    if (dirty && dashboard.state.active_engine === 'ming-3') values.ming = Object.fromEntries([...editor.querySelectorAll('[data-ming]')].map(input => [input.dataset.ming, input.value]));
    if (dirty && dashboard.state.active_engine === 'kittentts2') values.kitten = readKittenOptions(editor);
    return [card.dataset.voiceId, {engine: editor.dataset.engine || 'omnivoice', open: editor.open, dirty, values}];
  }));
  $('voices-list').replaceChildren();
  for (const v of dashboard.state.voices) {
    const preparing = v.status === 'pending';
    const prep = dashboard.state.jobs.find(j => j.id === v.preparation_job_id);
    const title = el('input', {...(preparing ? {disabled: ''} : {}), value: v.title, maxlength: '100', 'data-field': 'title', 'aria-label': t('Voice title')});
    const transcript = el('textarea', {...(preparing ? {disabled: ''} : {}), rows: '3', maxlength: '4000', 'aria-label': t('Saved transcript')}); transcript.value = v.transcript || '';
    const thumbnailInput = el('input', {type: 'file', accept: 'image/png,image/jpeg,image/webp', 'aria-label': t('Replace thumbnail')});
    const thumbnailControl = el('label', {}, t('Add / replace thumbnail (up to 2 MiB)'), thumbnailInput);
    thumbnailInput.addEventListener('change', action(async () => { const file = thumbnailInput.files[0]; if (!file) return; const body = new FormData(); body.set('thumbnail', file); await api(`/api/voices/${v.id}/thumbnail`, {method: 'POST', body}); await refresh(); }));
    const card = el('section', {class: 'card voice-card', 'data-voice-id': v.id}, v.thumbnail_url ? el('img', {src: v.thumbnail_url, alt: v.title}) : null,
      el('h2', {}, v.title), el('p', {class: 'muted'}, v.original_filename), v.warning ? el('p', {class: 'notice'}, t(v.warning)) : null, thumbnailControl, el('span', {class: 'pill'}, t(v.status)),
      v.status === 'unprepared' && !voiceAvailable(v) ? el('p', {class: 'preparation-note'}, t('Not prepared for first use. Complete Initial Setup, then click Prepare to save the reference transcript locally.')) : null,
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
    if (editorDraft && editorDraft.engine === (dashboard.state.active_engine || 'omnivoice')) {
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
  window.Locale.bind($('prepare-voices'), dashboard.state.voices.some(v => !voiceAvailable(v)) ? 'Some voices need preparation · open Voices' : 'Manage voices');
  if (!dashboard.state.voices.length) $('voices-list').append(el('p', {class: 'muted'}, t('No saved voices yet.')));
}

export function initVoices() {
  $('voice-form').addEventListener('submit', action(async event => {
    event.preventDefault(); const submit = event.target.querySelector('[type=submit]'); submit.disabled = true;
    try { const voice = await api('/api/voices', {method: 'POST', body: new FormData(event.target)}); event.target.reset(); $('voice-upload-note').textContent = voice.warning ? t(voice.warning) : ''; $('voice-upload-note').hidden = !voice.warning; await refresh(); }
    finally { submit.disabled = false; }
  }));
  $('prepare-voices').addEventListener('click', () => tab('voices'));
}

export {renderVoices};
