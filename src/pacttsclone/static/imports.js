// Optional weight discovery and personal-data import controls.
import {api} from './api.js';
import {$, el, formatTransferBytes, t} from './dom.js';
import {renderSetup} from './setup.js';
import {dashboard} from './state.js';

function weightSearchRoots() { return $('weight-search-roots').value.split('\n').map(v => v.trim()).filter(Boolean); }

function renderWeightDiscovery(data) {
  $('weight-reuse-panel').hidden = Boolean(dashboard.session?.remote_access);
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

function importAction(fn) { return async () => { try { await fn(); } catch (e) { $('optional-import-status').textContent = t(e.message); } }; }

function renderOptionalImport(data) {
  $('import-card').hidden = Boolean(dashboard.session?.remote_access);
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

export function initImports() {
  $('weight-search-roots').addEventListener('input', () => { $('weight-search-roots').dataset.edited = 'true'; });
  $('weight-scan').addEventListener('click', importAction(async () => {
    renderSetup(await api('/api/setup/weights/scan', {method: 'POST', body: {search_roots: weightSearchRoots(), move_weights: $('weight-move').checked}}));
  }));
  $('weight-scan-cancel').addEventListener('click', importAction(async () => {
    renderSetup(await api('/api/setup/weights/cancel', {method: 'POST'}));
  }));
  $('weight-import').addEventListener('click', importAction(async () => {
    renderSetup(await api('/api/import/start', {method: 'POST', body: {category: 'models', search_roots: weightSearchRoots(), move_weights: $('weight-move').checked}}));
  }));
  $('personal-import').addEventListener('click', importAction(async () => {
    renderSetup(await api('/api/import/start', {method: 'POST', body: {category: 'personal', source: $('personal-import-source').value.trim(), sections: [...$('personal-import-sections').querySelectorAll('input:checked')].map(n => n.value), replace_config: $('personal-replace-config').checked}}));
  }));
  $('optional-import-cancel').addEventListener('click', importAction(async () => {
    renderSetup(await api('/api/import/cancel', {method: 'POST'}));
  }));
}

export {renderOptionalImport, renderWeightDiscovery};
