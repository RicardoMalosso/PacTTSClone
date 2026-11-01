(() => {
  const card = document.querySelector('#updates-card');
  if (!card || document.querySelector('#update-version')) return;
  const panel = document.createElement('div');
  panel.innerHTML = '<label class="check"><input type="checkbox" id="update-experimental" disabled><span id="update-channel-label"></span></label><label id="update-version-label" for="update-version"></label><select id="update-version" disabled></select><button type="button" id="update-apply" disabled></button><p id="update-manager-status" role="status"></p><p id="update-compatibility"></p>';
  card.append(panel);
  const rc = panel.querySelector('input'), select = panel.querySelector('select');
  const apply = panel.querySelector('button'), status = panel.querySelector('[role=status]');
  let state, dirty = false, error = '';
  const pt = () => window.Locale?.language === 'pt';
  const tr = (en, br) => pt() ? br : en;
  function render() {
    const choice = dirty ? select.value : state?.target;
    if (!dirty) rc.checked = state?.include_experimental ?? true;
    panel.querySelector('#update-channel-label').textContent = tr('Include experimental releases (RC)', 'Incluir versões experimentais (RC)');
    panel.querySelector('#update-version-label').textContent = tr('Application version', 'Versão do aplicativo');
    apply.textContent = tr('Apply / download version', 'Aplicar / baixar versão');
    panel.querySelector('#update-compatibility').textContent = tr('Models and personal data are retained. Older versions may lack newer engines. Choose Latest to resume automatic updates.', 'Modelos e dados pessoais são mantidos. Versões anteriores podem não ter os novos motores. Selecione Mais recente para retomar as atualizações automáticas.');
    select.replaceChildren(new Option(tr('Latest (automatic)', 'Mais recente (automático)'), 'latest'));
    for (const row of state?.releases || []) {
      if (row.experimental && !rc.checked) continue;
      select.add(new Option(`${row.tag}${row.experimental ? ' · ' + tr('Experimental', 'Experimental') : ''}${row.published_at ? ' · ' + new Date(row.published_at).toLocaleDateString(pt() ? 'pt-BR' : 'en-CA') : ''}`, row.tag));
    }
    if (choice && ![...select.options].some(o => o.value === choice)) select.add(new Option(choice, choice));
    select.value = choice || 'latest';
    const busy = ['checking', 'downloading'].includes(state?.status);
    rc.disabled = select.disabled = apply.disabled = !state?.enabled || busy;
    status.textContent = error || (!state?.enabled ? tr('Source installation: update through Git.', 'Instalação pelo código: atualize pelo Git.') : `${tr('Current', 'Atual')}: ${state.version} · ${state.status}${state.next_version ? ' · ' + tr('Restart to apply', 'Reinicie para aplicar') + ' ' + state.next_version : ''}${state.target !== 'latest' ? ' · ' + tr('Pinned', 'Fixada') + ': ' + state.target : ''}${state.error ? ' · ' + state.error : ''}`);
  }
  async function load() {
    try { const r = await fetch('/api/updates/manager'); if (!r.ok) throw Error(r.status); state = await r.json(); render(); }
    catch (e) { error = String(e); render(); }
  }
  rc.onchange = () => { dirty = true; if (!rc.checked && select.value.includes('-rc.')) select.value = 'latest'; render(); };
  select.onchange = () => { dirty = true; };
  apply.onclick = async () => {
    apply.disabled = true; error = '';
    try {
      const session = await (await fetch('/api/session')).json();
      const response = await fetch('/api/updates/select', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PacTTS-Token': session.token}, body: JSON.stringify({include_experimental: rc.checked, target: select.value})});
      const result = await response.json(); if (!response.ok) throw Error(result.detail || response.status);
      state = result; dirty = false;
    } catch (e) { error = String(e); }
    render();
  };
  window.addEventListener('localechange', render);
  load();
  setInterval(() => { if (!document.querySelector('#pane-config')?.hidden) load(); }, 5000);
})();
