// Engine installation and activation plus Ming/Kitten generation controls.
import {api, refresh} from './api.js';
import {$, button, el, error, t} from './dom.js';
import {runtimeStatus} from './setup.js';
import {dashboard} from './state.js';

async function renderEngines() {
  if (!dashboard.session || dashboard.session.remote_access || $('pane-engines').hidden) return;
  const data = await api('/api/engines');
  const size = n => n == null ? t('Not verified') : `${(n / 1073741824).toFixed(2)} GiB`;
  $('engine-hardware').textContent = (dashboard.state.model_residency?.loaded ? t('Model loaded in memory') : t('Model unloaded')) + ' · ' + $('vram').textContent;
  $('engine-storage').textContent = `${data.directory} · ${size(data.free_bytes)} ${t('free')}`;
  $('engine-rows').replaceChildren(...data.engines.map(engine => {
    const controls = el('td');
    const details = el('details', {}, el('summary', {}, t('Requirements and features')));
    const add = (label, value) => details.append(el('p', {}, `${t(label)}: ${t(value)}`));
    add('Runtime', engine.runtime); add('System RAM', engine.ram);
    if (engine.directory) add('Installation directory', engine.directory);
    add('Languages', engine.languages); add('License', engine.license);
    for (const [name, value] of Object.entries(engine.capabilities)) add(name, value);
    for (const model of engine.models) details.append(el('p', {}, `${model.repo}@${model.revision}`));
    details.append(el('a', {href: engine.source, target: '_blank', rel: 'noopener noreferrer'}, t('Model documentation')));
    const run = operation => async () => {
      if (operation === 'uninstall' && !confirm(t('Remove installed engine model files? Saved voices and audio are retained.'))) return;
      await api(`/api/engines/${engine.id}/${operation}`, {method: 'POST'});
      await refresh(); await runtimeStatus(); await renderEngines();
    };
    if (['ming-3','kittentts2'].includes(engine.id)) controls.append(el('a', {href: `/api/engines/${engine.id}/log`, download: ''}, t('Installation log')));
    if (!engine.supported) controls.textContent = t('Available in a later release');
    else if (data.busy && ((['ming-3','kittentts2'].includes(engine.id) && engine.installation?.status === 'running') || (engine.id === 'omnivoice' && data.setup.status === 'running'))) controls.append(button('Cancel setup', run('cancel')));
    else if (data.busy) controls.append(el('span', {}, t('Wait for installation')));
    else if (!engine.installed) controls.append(button('Install', run('install')));
    else {
      controls.append(button(engine.active ? 'Deactivate' : 'Activate', run(engine.active ? 'deactivate' : 'activate')));
      const remove = button('Uninstall', run('uninstall'));
      remove.disabled = engine.active;
      controls.append(remove);
    }
    return el('tr', {}, el('td', {}, engine.name),
      el('td', {}, `${size(engine.installed_bytes)} ${t('installed')} / ${size(engine.download_bytes)} ${t('download')}; ${t('Peak installation space')}: ${engine.runtime_reserve_bytes ? size(engine.download_bytes + engine.runtime_reserve_bytes) + ' (' + t('conservative budget') + ')' : t('Not verified')}`),
      el('td', {}, t(engine.vram)), el('td', {}, t(engine.features), details, ...(engine.installation ? [el('p', {}, engine.installation.error || `${t(engine.installation.stage || 'idle')} · ${size(engine.installation.completed_bytes)} / ${size(engine.installation.total_bytes)}`)] : [])),
      el('td', {}, t(engine.active ? (data.loaded ? 'Active / loaded' : 'Active / unloaded') : engine.status)), controls);
  }));
  const download = data.setup.download;
  $('engine-progress').textContent = data.setup.error || (download ? `${download.phase || ''}: ${size(download.completed_bytes)} / ${size(download.total_bytes)}` : data.setup.stage);
}

function renderMingOptions(container, saved = {}) {
  container.querySelector('.ming-options')?.remove();
  const active = dashboard.state.active_engine === 'ming-3';
  for (const key of ['language', 'speed', 'duration', 'steps', 'denoise', 'preprocess_prompt']) {
    const input = container.querySelector(`[data-setting="${key}"]`);
    if (input) input.closest('label').hidden = active;
  }
  if (!active) return;
  const panel = el('fieldset', {class: 'ming-options'}, el('legend', {}, t('Ming task settings')),
    el('p', {}, t('Each task uses its own controls. Cloning uses reference audio and transcript; freeform, voice design and presets create their own voice. Portuguese is unsupported.')));
  const fields = [
    ['task', 'Task', [['TTS','Clone / vocal tags'],['EMOTION','Emotion'],['BASIC','Speed / pitch / loudness'],['FREEFORM','Delivery instruction'],['VOICE_DESIGN','Voice design'],['IP','Built-in voice'],['DIALECT','Dialect']]],
    ['language','Ming language', [['en','English'],['zh','Chinese'],['de','German'],['es','Spanish'],['fr','French'],['ko','Korean'],['ja','Japanese']]],
    ['emotion','Emotion', ['neutral','happy','sad','angry','afraid','disgusted','surprised'].map(x=>[x,x])],
    ['speed','Ming speed', ['normal','slow','fast'].map(x=>[x,x])],
    ['pitch','Pitch', ['normal','low','high'].map(x=>[x,x])],
    ['loudness','Loudness', ['normal','low','high'].map(x=>[x,x])],
    ['voice','Built-in voice', ['US_Emma','UK_George','UK_Charlotte'].map(x=>[x,x])],
    ['dialect','Dialect', [['cantonese','Cantonese'],['chuanyu dialect','Sichuanese']]]
  ];
  for (const [key,label,options] of fields) {
    const input = el('select', {'data-ming':key, title:t(label)}, ...options.map(([value,label])=>el('option',{value},t(label))));
    if (saved?.[key]) input.value = saved[key];
    panel.append(el('label',{},t(label),input));
  }
  const instruction = el('textarea', {'data-ming':'instruction', maxlength:'1000', title:t('Delivery instruction / voice description')});
  instruction.value = saved?.instruction || '';
  panel.append(el('label', {}, t('Delivery instruction / voice description'), instruction));
  const visibility = () => {
    const task = panel.querySelector('[data-ming="task"]').value;
    const visible = {TTS:['language'], EMOTION:['emotion'], BASIC:['speed','pitch','loudness'], FREEFORM:['instruction'], VOICE_DESIGN:['instruction'], IP:['voice'], DIALECT:['dialect']}[task];
    for (const input of panel.querySelectorAll('[data-ming]')) input.closest('label').hidden = input.dataset.ming !== 'task' && !visible.includes(input.dataset.ming);
  };
  panel.querySelector('[data-ming="task"]').addEventListener('change', visibility);
  panel.append(el('details', {}, el('summary', {}, t('Supported vocal tags')),
    '[Breathing] [Cough] [Sigh] [Laughter] [Surprise-ah] [Surprise-oh] [Dissatisfaction-hnn] [Uhm] [Confirmation-en] [Question-ei] [Question-ah] [Question-en] [Question-oh] [Question-huh]'));
  panel.style.gridColumn = "1 / -1"; panel.style.minWidth = "0";
  visibility(); (container.querySelector(".settings") || container).append(panel);
}

function readKittenOptions(container) {
  return Object.fromEntries([...container.querySelectorAll('[data-kitten]')].map(input => [input.dataset.kitten,
    input.type === 'checkbox' ? input.checked : input.type === 'number' ? (input.value.trim() === '' ? null : Number(input.value)) : input.value]));
}

function renderKittenOptions(container, saved = {}) {
  container.querySelector('.kitten-options')?.remove();
  const active = dashboard.state.active_engine === 'kittentts2';
  for (const key of ['language','speed','duration','steps','denoise','preprocess_prompt','guidance_scale','postprocess_output']) {
    const input = container.querySelector(`[data-setting="${key}"]`);
    if (input) input.closest('label').hidden = active || (dashboard.state.active_engine === 'ming-3' && !['guidance_scale','postprocess_output'].includes(key));
  }
  if (!active) return;
  const values = {mode:'clone',voice:'Bruno',preset:'stable',max_new_tokens:1000,normalize:true,use_reference_prompt:true,seed:null,...saved};
  const panel = el('fieldset', {class:'kitten-options'}, el('legend',{},t('KittenTTS2 settings')),
    el('p',{},t('Cloning needs a 5–30 second reference and exact transcript. Preset mode uses a built-in voice; the saved voice selects its settings.')), el('p',{},t('Save preset mode in Voices to use a built-in voice without preparing the reference or installing Whisper.')));
  for (const [key,label,options] of [
    ['mode','Voice mode',[['clone','Clone reference'],['preset','Built-in voice']]],
    ['voice','Built-in voice',(dashboard.state.kitten_voices || ['Bruno']).map(x=>[x,x])],
    ['preset','Delivery preset',[['stable','Stable'],['expressive','Expressive']]]
  ]) {
    const input = el('select',{'data-kitten':key,title:t(label)},...options.map(([value,name])=>el('option',{value},t(name))));
    input.value = values[key]; panel.append(el('label',{},t(label),input));
  }
  for (const [key,label,min,max] of [['max_new_tokens','Token budget per chunk',100,2000],['seed','Seed (blank for random)',0,2147483647]]) {
    const input = el('input',{type:'number','data-kitten':key,min,max,step:1,title:t(label)});
    input.value = values[key] ?? ''; panel.append(el('label',{},t(label),input));
  }
  for (const [key,label] of [['normalize','Normalize written text'],['use_reference_prompt','Condition on reference audio']]) {
    const input = el('input',{type:'checkbox','data-kitten':key,title:t(label)}); input.checked=values[key];
    panel.append(el('label',{class:'check'},input,' ',t(label)));
  }
  const visibility = () => {panel.querySelector('[data-kitten="voice"]').closest('label').hidden = panel.querySelector('[data-kitten="mode"]').value !== 'preset';};
  panel.querySelector('[data-kitten="mode"]').addEventListener('change',visibility);
  visibility(); panel.style.gridColumn='1 / -1'; panel.style.minWidth='0';
  (container.querySelector('.settings') || container).append(panel);
}

export function initEngines() {
  window.addEventListener('localechange', () => renderEngines().catch(e => error(e.message)));
  document.querySelector('[data-tab=engines]').addEventListener('click', () => renderEngines().catch(e => error(e.message)));
  window.addEventListener('localechange', () => {
    if (dashboard.state.active_engine !== 'ming-3') return;
    const form = $('generate-form');
    const values = Object.fromEntries([...form.querySelectorAll('[data-ming]')].map(input => [input.dataset.ming, input.value]));
    renderMingOptions(form, values);
  });
  window.addEventListener('localechange', () => {
    if (dashboard.state.active_engine === 'kittentts2') {const form=$('generate-form'); renderKittenOptions(form,readKittenOptions(form));}
  });
}

export {readKittenOptions, renderEngines, renderKittenOptions, renderMingOptions};
