// Dedicated sound-effects catalogue. User strings are always rendered as text.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {dashboard} from './state.js';

let renderedKey = '';
const triggers = value => value.split('\n').map(s => s.trim()).filter(Boolean);

export function renderSfx() {
  const effects = dashboard.state.sfx || [];
  const key = JSON.stringify([window.Locale.language, effects]);
  if (key === renderedKey) return;
  renderedKey = key;
  const cards = effects.map(effect => {
    const title = el('input', {value: effect.title, maxlength: 100, required: ''});
    const aliases = el('textarea', {rows: 2, required: ''}, effect.triggers.join('\n'));
    const volume = el('input', {type: 'number', min: 0, max: 300, value: effect.volume});
    const duration = el('input', {type: 'number', min: 0.05, max: 15, step: 0.01, value: effect.duration ?? ''});
    const enabled = el('input', {type: 'checkbox'}); enabled.checked = effect.enabled;
    const upload = el('input', {type: 'file', accept: '.mp3,.wav,.ogg,.flac,.m4a,audio/*'});
    const preview = el('audio', {controls: '', preload: 'none', src: effect.audio_url});
    const label = (name, input) => el('label', {}, t(name), input);
    const form = el('form', {class: 'card sfx-card', 'data-sfx-id': effect.id},
      el('h2', {}, effect.title), el('p', {}, t('Original sound preview')), preview,
      label('Sound effect name', title), label('Triggers · one per line', aliases),
      label('SFX volume (%)', volume), label('SFX duration (seconds) · blank uses original', duration),
      el('label', {class: 'check'}, enabled, t('Enable sound effect')),
      label('Replace audio', upload),
      el('div', {class: 'row-actions'}, el('button', {type: 'submit'}, t('Save sound effect')),
        button('Delete sound effect', async () => {
          preview.pause();
          await api(`/api/sfx/${effect.id}`, {method: 'DELETE'}); await refresh();
        }, 'danger small-button')));
    form.addEventListener('submit', action(async event => {
      event.preventDefault();
      await api(`/api/sfx/${effect.id}`, {method: 'PUT', body: {
        title: title.value, triggers: triggers(aliases.value), volume: Number(volume.value),
        duration: duration.value ? Number(duration.value) : null, enabled: enabled.checked,
      }});
      if (upload.files.length) {
        const body = new FormData(); body.append('audio', upload.files[0]);
        await api(`/api/sfx/${effect.id}/audio`, {method: 'POST', body});
      }
      await refresh();
    }));
    return form;
  });
  $('sfx-list').querySelectorAll('audio').forEach(audio => audio.pause());
  $('sfx-list').replaceChildren(...(cards.length ? cards : [el('p', {}, t('No sound effects yet.'))]));
}

export function initSfx() {
  $('sfx-form').addEventListener('submit', action(async event => {
    event.preventDefault();
    const form = $('sfx-form');
    const body = new FormData(form);
    if (!body.get('duration')) body.delete('duration');
    await api('/api/sfx', {method: 'POST', body});
    form.reset(); await refresh();
  }));
  window.addEventListener('localechange', renderSfx);
}
