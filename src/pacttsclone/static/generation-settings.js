// Shared generation settings, per-engine defaults, and voice settings editor.
import {api, refresh} from './api.js';
import {$, button, el, t} from './dom.js';
import {readKittenOptions, renderKittenOptions, renderMingOptions} from './engines.js';
import {dashboard} from './state.js';

const defaultGenerationSettings = Object.freeze({language: 'auto', volume: 100, speed: 1, duration: null, steps: 32, denoise: true, guidance_scale: 2, preprocess_prompt: true, postprocess_output: true});

const generationFields = [
  ['language', 'Language', 'select'],
  ['volume', 'Output volume (%)', 'number', '0', '300', '5'],
  ['speed', 'Speed', 'number', '0.5', '1.5', '0.05'],
  ['duration', 'Duration (seconds)', 'number', '0.5', '120', '0.1'],
  ['steps', 'Inference Steps', 'number', '4', '64', '1'],
  ['guidance_scale', 'Guidance Scale (CFG)', 'number', '0', '4', '0.1'],
  ['denoise', 'Denoise', 'checkbox'],
  ['preprocess_prompt', 'Preprocess Prompt', 'checkbox'],
  ['postprocess_output', 'Postprocess Output', 'checkbox']
];

const generationHelp = {
  "language": "Automatic lets the model choose the speech language. Select Portuguese or English to force it; this does not translate the text.",
  "volume": "100% keeps the original level; 50% halves the signal amplitude; 200% doubles it. 0% mutes. Large boosts can distort loud peaks. Applies to new MP3s, including OBS and Discord playback; existing files stay unchanged.",
  "speed": "1.0 is normal; below 1 is slower; above 1 is faster. Ignored when Duration is set.",
  "duration": "Leave blank for natural timing controlled by Speed. A number requests a fixed length in seconds and overrides Speed; extreme lengths may sound unnatural.",
  "steps": "Number of generation steps. Default 32; fewer steps are faster, more steps take longer. More steps do not guarantee better audio.",
  "guidance_scale": "How strongly generation follows the conditioning (text and reference voice). Default 2.0. Higher is not always better; start with the default.",
  "denoise": "Enables the model’s audio denoising. Usually leave enabled; compare with it off if the voice sounds processed.",
  "preprocess_prompt": "Trims silence from the reference audio and adds ending punctuation to its transcript when needed. Does not edit your saved reference file.",
  "postprocess_output": "Removes long silences from generated speech. Disable if you want to retain those pauses."
};

function voiceGenerationSettings(voice) {
  const ming = dashboard.state.active_engine === 'ming-3';
  const saved = dashboard.state.active_engine && dashboard.state.active_engine !== 'omnivoice' ? voice?.engine_generation_settings?.[dashboard.state.active_engine] : voice?.generation_settings;
  return {...defaultGenerationSettings, ...(ming ? {language: 'en'} : {}), ...(saved || {})};
}

function voiceAvailable(voice) {
  return voice.status === 'ready' || (dashboard.state.active_engine === 'kittentts2' && voiceGenerationSettings(voice).kitten?.mode === 'preset');
}

function settingsControls(container) {
  return Object.fromEntries(generationFields.map(([key]) => [key, container.querySelector(`[data-setting="${key}"]`)]));
}

function readGenerationSettings(container) {
  const controls = settingsControls(container);
  const values = Object.fromEntries(generationFields.map(([key, , type]) => {
    const input = controls[key];
    if (type === 'checkbox') return [key, input.checked];
    if (type === 'select') return [key, input.value];
    if (key === 'duration' && input.value.trim() === '') return [key, null];
    if (input.value.trim() === '') throw new Error(t('Enter a valid generation setting.'));
    return [key, Number(input.value)];
  }));
  if (dashboard.state.active_engine === 'ming-3') {
    for (const key of ['speed', 'duration', 'steps', 'denoise', 'preprocess_prompt']) values[key] = defaultGenerationSettings[key];
    values.language = 'auto';
    values.ming = Object.fromEntries([...container.querySelectorAll('[data-ming]')].map(input => [input.dataset.ming, input.value]));
  }
  if (dashboard.state.active_engine === 'kittentts2') {
    for (const key of ['speed','duration','steps','denoise','preprocess_prompt','guidance_scale','postprocess_output','language']) values[key] = defaultGenerationSettings[key];
    values.kitten = readKittenOptions(container);
  }
  return values;
}

function applySettingsValues(container, values) {
  renderMingOptions(container, values.ming);
  renderKittenOptions(container, values.kitten);
  const controls = settingsControls(container);
  for (const [key, , type] of generationFields) {
    if (type === 'checkbox') controls[key].checked = Boolean(values[key]);
    else controls[key].value = values[key] ?? '';
  }
}

let appliedStudioPreset = '';

function applyStudioVoiceDefaults() {
  const voice = dashboard.state.voices.find(v => v.id === $('voice-select').value);
  const snapshot = voiceGenerationSettings(voice);
  const identity = (dashboard.state.active_engine || 'omnivoice') + (voice?.id || '') + JSON.stringify(snapshot);
  if (identity === appliedStudioPreset) return;
  appliedStudioPreset = identity;
  applySettingsValues($('generate-form'), snapshot);
}

function createVoiceSettingsEditor(voice) {
  const values = voiceGenerationSettings(voice);
  const container = el('div', {class: 'settings voice-setting-fields'});
  for (const [key, label, type, min, max, step] of generationFields) {
    const input = type === 'select'
      ? el('select', {'data-setting': key, 'aria-label': t(label)},
        ...[['auto', 'Automatic'], ['pt', 'Português'], ['en', 'English']].map(([value, name]) => el('option', {value}, t(name))))
      : el('input', {type, 'data-setting': key, 'aria-label': t(label), ...(type === 'number' ? {min, max, step, value: values[key] ?? ''} : {checked: values[key] ? '' : null})});
    if (type === 'select') input.value = values[key];
    const labelNode = type === 'checkbox'
      ? el('label', {class: 'check'}, input, ' ', t(label))
      : el('label', {}, t(label), input);
    labelNode.classList.add('generation-setting');
    labelNode.title = t(generationHelp[key]);
    input.title = t(generationHelp[key]);
    input.setAttribute('aria-description', t(generationHelp[key]));
    container.append(labelNode);
  }
  renderMingOptions(container, values.ming);
  renderKittenOptions(container, values.kitten);
  const editor = el('details', {class: 'voice-generation-settings', 'data-engine':dashboard.state.active_engine || 'omnivoice'},
    el('summary', {}, t('Voice generation defaults')),
    el('p', {class: 'muted'}, t('These defaults apply to Twitch commands and new manual generations.')),
    container, el('p', {class: 'muted'}, t(dashboard.state.active_engine === 'kittentts2' ? 'The token budget limits each chunk; 25 audio tokens are approximately one second. A fixed seed helps reproduce a request.' : 'Duration overrides Speed when provided. Turning off output postprocessing avoids trimming trailing silence.')),
    button(dashboard.state.active_engine === 'kittentts2' ? 'Restore KittenTTS2 defaults' : dashboard.state.active_engine === 'ming-3' ? 'Restore Ming defaults' : 'Restore OmniVoice defaults', () => {
      applySettingsValues(editor, defaultGenerationSettings);
      editor.closest('.voice-card').dataset.settingsDirty = 'true';
    }),
    button('Save generation defaults', async () => {
      await api(`/api/voices/${voice.id}/generation-settings`, {method: 'PUT', body: readGenerationSettings(editor)});
      editor.closest('.voice-card').dataset.settingsDirty = 'false';
      await refresh();
    })
  );
  editor.querySelectorAll('[data-setting], [data-ming], [data-kitten]').forEach(input => input.addEventListener('input', () => { editor.closest('.voice-card').dataset.settingsDirty = 'true'; }));
  return editor;
}

export function initGenerationSettings() {
  for (const [key, explanation] of Object.entries(generationHelp)) {
    const input = $('generate-form').querySelector(`[data-setting="${key}"]`);
    if (input) {
      input.closest('label').classList.add('generation-setting');
      input.title = t(explanation);
      input.setAttribute('aria-description', t(explanation));
      input.closest('label').title = t(explanation);
    }
  }
  $('voice-select').addEventListener('change', applyStudioVoiceDefaults);
}

export {applySettingsValues, createVoiceSettingsEditor, generationFields, readGenerationSettings, voiceAvailable};
