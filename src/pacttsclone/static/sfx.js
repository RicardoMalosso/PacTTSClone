// Saved SFX are the primary view. Reuse unchanged cards to preserve other edits.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {dashboard} from './state.js';

const triggers = value => value.split('\n').map(s => s.trim()).filter(Boolean);

function feedback(node, text, failed = false) {
  node.textContent = text; node.hidden = false; node.className = failed ? 'error' : 'notice';
}

async function reloadSfx() {
  dashboard.state.sfx = await api('/api/sfx');
  renderSfx();
}

function filterSfx() {
  const query = $('sfx-search').value.trim().toLocaleLowerCase();
  const cards = [...$('sfx-list').querySelectorAll('.sfx-card')];
  cards.forEach(card => { card.hidden = !card.dataset.search.includes(query); });
  $('sfx-no-match').hidden = !cards.length || cards.some(card => !card.hidden);
}

function createCard(effect) {
  const title = el('input', {value: effect.title, maxlength: 100, required: ''});
  const aliases = el('textarea', {rows: 2, required: ''}, effect.triggers.join('\n'));
  const volume = el('input', {type: 'number', min: 0, max: 300, value: effect.volume});
  const duration = el('input', {type: 'number', min: 0.05, max: 15, step: 0.01, value: effect.duration ?? ''});
  const enabled = el('input', {type: 'checkbox'}); enabled.checked = effect.enabled;
  const upload = el('input', {type: 'file', accept: '.mp3,.wav,.ogg,.flac,.m4a,audio/*'});
  const preview = el('audio', {controls: '', preload: 'none', src: effect.audio_url.replace('/audio', '/preview')});
  const label = (name, input) => el('label', {}, t(name), input);
  const saveStatus = el('p', {role: 'status', hidden: ''});
  const editor = el('form', {hidden: ''},
    label('Sound effect name', title), label('Triggers · one per line', aliases),
    label('SFX volume (%)', volume), label('SFX duration (seconds) · blank uses original', duration),
    el('label', {class: 'check'}, enabled, t('Enable sound effect')), label('Replace audio', upload),
    el('button', {type: 'submit'}, t('Save sound effect')), saveStatus);
  const edit = button('Edit sound effect', () => {
    editor.hidden = !editor.hidden; edit.setAttribute('aria-expanded', String(!editor.hidden));
    if (!editor.hidden) title.focus();
  });
  edit.setAttribute('aria-expanded', 'false');
  const card = el('section', {class: 'card sfx-card', 'data-sfx-id': effect.id},
    el('h3', {}, effect.title),
    el('p', {}, ...effect.triggers.map(trigger => el('span', {class: 'pill'}, trigger))),
    el('p', {class: 'muted'}, `${t(effect.enabled ? 'Enabled' : 'Disabled')} · ${(effect.duration ?? effect.audio_duration).toFixed(2)} s · ${effect.volume}%`),
    el('p', {class: 'muted'}, t('Preview saved volume and duration')), preview,
    el('div', {class: 'row-actions'}, edit, button('Delete sound effect', async () => {
      preview.pause(); await api(`/api/sfx/${effect.id}`, {method: 'DELETE'}); await refresh();
    }, 'danger small-button')), editor);
  editor.addEventListener('submit', action(async event => {
    event.preventDefault();
    // Capture the selected file before SSE can replace this saved card.
    const replacement = upload.files[0];
    const submit = editor.querySelector('[type=submit]'); submit.disabled = true;
    feedback(saveStatus, t('Saving sound effect…'));
    try {
      const settings = {
        title: title.value, triggers: triggers(aliases.value), volume: Number(volume.value),
        duration: duration.value ? Number(duration.value) : null, enabled: enabled.checked,
      };
      if (replacement) {
        const body = new FormData();
        body.append('audio', replacement);
        body.append('settings', JSON.stringify(settings));
        await api(`/api/sfx/${effect.id}/audio`, {method: 'POST', body});
      } else {
        await api(`/api/sfx/${effect.id}`, {method: 'PUT', body: settings});
      }
      await reloadSfx();
      feedback($('sfx-feedback'), t('Sound effect saved.'));
    } catch (error) { feedback(saveStatus, error.message, true); feedback($('sfx-feedback'), error.message, true); }
    finally { submit.disabled = false; }
  }));
  card.dataset.search = [effect.title, ...effect.triggers].join(' ').toLocaleLowerCase();
  card.dataset.effectKey = JSON.stringify([window.Locale.language, effect]);
  return card;
}

export function renderSfx() {
  const effects = dashboard.state.sfx || [];
  const host = $('sfx-list');
  const existing = new Map([...host.querySelectorAll('.sfx-card')].map(card => [card.dataset.sfxId, card]));
  const ids = new Set(effects.map(effect => effect.id));
  for (const child of [...host.children]) {
    if (!ids.has(child.dataset.sfxId)) { child.querySelectorAll('audio').forEach(a => a.pause()); child.remove(); }
  }
  for (const effect of [...effects].sort((a, b) => a.title.localeCompare(b.title))) {
    const old = existing.get(effect.id);
    const key = JSON.stringify([window.Locale.language, effect]);
    const card = old?.dataset.effectKey === key ? old : createCard(effect);
    if (old && card !== old) { old.querySelectorAll('audio').forEach(a => a.pause()); old.replaceWith(card); }
    host.append(card);
  }
  if (!effects.length) host.append(el('p', {}, t('No sound effects yet. Add one to get started.')));
  $('sfx-count').textContent = String(effects.length);
  filterSfx();
}

function showCreate(show) {
  $('sfx-create').hidden = !show;
  $('sfx-add-toggle').setAttribute('aria-expanded', String(show));
  if (show) { $('sfx-create').scrollIntoView({block: 'nearest'}); $('sfx-form').elements.title.focus(); }
}

export function initSfx() {
  $('sfx-reload').addEventListener('click', action(async () => {
    await reloadSfx(); feedback($('sfx-feedback'), t('Saved effects reloaded.'));
  }));
  $('sfx-add-toggle').addEventListener('click', () => showCreate($('sfx-create').hidden));
  $('sfx-add-cancel').addEventListener('click', () => showCreate(false));
  $('sfx-search').addEventListener('input', filterSfx);
  $('sfx-form').addEventListener('submit', action(async event => {
    event.preventDefault(); const form = $('sfx-form');
    const body = new FormData(form); if (!body.get('duration')) body.delete('duration');
    const submit = form.querySelector('[type=submit]'); submit.disabled = true;
    const status = $('sfx-save-status'); feedback(status, t('Saving sound effect…'));
    let accepted = false;
    try {
      const effect = await api('/api/sfx', {method: 'POST', body}); accepted = true;
      await reloadSfx();
      const card = [...$('sfx-list').children].find(node => node.dataset.sfxId === effect.id);
      if (!card) {
        feedback(status, t('The uploaded sound was missing from the saved list. Reload saved effects to check again.'), true);
        return;
      }
      form.reset(); $('sfx-search').value = ''; showCreate(false); filterSfx();
      feedback($('sfx-feedback'), `${t('Sound effect saved.')}: ${effect.title}`);
      card.scrollIntoView({block: 'nearest'});
    } catch (error) {
      feedback(status, (accepted ? t('Upload accepted. Could not verify the saved list. Use Reload saved effects.') + ' ' : '') + error.message, true);
    } finally { submit.disabled = false; }
  }));
  window.addEventListener('localechange', renderSfx);
}
