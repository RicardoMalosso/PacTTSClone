// Twitch channel forms, command mappings, dashboards, and playback controls.
import {api, refresh} from './api.js';
import {$, action, button, el, link, t} from './dom.js';
import {voiceAvailable} from './generation-settings.js';
import {dashboard} from './state.js';
import {eventRuleRow, readEventRules, refreshEventVoices, renderTwitchEvents, updateTwitchMode} from './twitch.js';

let channelKey = '';

let channelLinksKey = '';

let channelDashboardKey = '';

function refreshCommandVoices() {
  for (const select of document.querySelectorAll('.command-row select')) {
    const selected = select.value;
    const ready = dashboard.state.voices.filter(voiceAvailable);
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
  for (const voice of dashboard.state.voices.filter(voiceAvailable)) select.append(el('option', {value: voice.id}, voice.title));
  select.value = voiceId;
  const row = el('div', {class: 'command-row'}, input, select, button('Remove', () => row.remove()));
  $('commands-list').append(row);
}

function fillChannel(name) {
  dashboard.selectedChannel = name;
  const c = dashboard.state.channels.find(c => c.name === name);
  $('channel-name').value = c?.name || ''; $('channel-transport').value = c?.transport || 'irc';
  $('event-rules').replaceChildren(); for (const rule of c?.event_rules || []) eventRuleRow(rule); updateTwitchMode();
  $('channel-paused').checked = c?.paused || false; $('channel-delay').value = c?.delay_seconds ?? 5;
  $('channel-cooldown').value = c?.user_cooldown_seconds ?? 15; $('channel-limit').value = c?.max_message_chars ?? 300;
  $('channel-filter').value = c?.filter_level || 'slurs'; $('channel-custom').value = (c?.custom_filters || []).join('\n');
  $('commands-list').replaceChildren(); for (const [key, id] of Object.entries(c?.commands || {})) commandRow(key, id);
  if (!c) commandRow();
}

function renderChannels() {
  refreshCommandVoices();
  renderChannelDashboard();
  refreshEventVoices();
  const key = JSON.stringify(dashboard.state.channels.map(c => ({name: c.name})));
  if (key !== channelKey) {
    channelKey = key; $('channel-select').replaceChildren(el('option', {value: ''}, t('Create a channel')));
    for (const c of dashboard.state.channels) $('channel-select').append(el('option', {value: c.name}, c.name));
    $('channel-select').value = dashboard.selectedChannel;
  }
  const c = dashboard.selectedChannel === 'playbackMain' ? {name: 'playbackMain', connection: t('Local OBS Sources')} : dashboard.state.channels.find(c => c.name === dashboard.selectedChannel);
  $('channel-connection').textContent = c ? `${c.name}: ${t(c.connection)}${c.connection_error ? ' · ' + c.connection_error : ''}` : t('Choose a saved channel.');
  const playerUrl = c ? (dashboard.session?.remote_access ? dashboard.state.player_links?.[c.name] || `/${c.name}` : `/${c.name}`) : '';
  const linksKey = JSON.stringify([c?.name || '', playerUrl]);
  $('local-obs-player-link').href = dashboard.session?.remote_access ? dashboard.state.player_links?.playbackMain || '/playbackMain' : '/playbackMain';
  if (linksKey === channelLinksKey) return;
  channelLinksKey = linksKey;
  $('channel-links').replaceChildren();
  if (c) $('channel-links').append(el('p', {}, link('Open OBS player', playerUrl)), el('input', {readonly: '', value: new URL(playerUrl, location.origin).href, 'aria-label': 'OBS source URL'}),
    el('p', {}, link('Open separate control page', `/${c.name}/control`)));
}

async function renderChannelState() {
  if (!dashboard.selectedChannel || (dashboard.selectedChannel !== 'playbackMain' && !dashboard.state.channels.some(c => c.name === dashboard.selectedChannel))) return;
  const snap = await api(`/api/channels/${dashboard.selectedChannel}/state`); dashboard.latestChannelState = snap;
  $('channel-player-status').textContent = `${snap.paused ? t('Playback paused') : t('Playback enabled')} · ${snap.player_connected ? t('OBS player connected') : t('No active OBS player')}`;
  const pending = snap.items.filter(i => ['queued', 'countdown', 'ready', 'playing'].includes(i.status));
  $('channel-queue').replaceChildren(...pending.map(i => el('div', {class: 'job-row'}, el('strong', {}, `${i.voice_title} · ${t(i.status)}`), el('p', {}, `${i.username || t('Replay')}: ${i.text}`),
    i.deadline && i.status === 'countdown' ? el('p', {class: 'muted', 'data-countdown-until': Date.now() + (i.deadline - snap.server_time) * 1000}, t('Starts in {seconds} s', {seconds: Math.max(0, i.deadline - snap.server_time).toFixed(1)})) : null,
    button('Cancel audio', async () => { await api(`/api/playback/${i.id}/cancel`, {method: 'POST'}); await renderChannelState(); }))));
  renderTwitchEvents(snap.events || []);
  $('chat-events').replaceChildren(...snap.chat.map(c => el('div', {class: 'event-row'}, el('strong', {}, `${c.username} · ${c.accepted ? t('accepted') : t('blocked') + ': ' + t(c.reason)}`), el('p', {}, c.text))));
}

function refreshDashboardQueues() {
  for (const channel of dashboard.state.channels) {
    const list = document.querySelector(`[data-channel="${channel.name}"] [data-queue-items]`);
    if (!list) continue;
    const items = channel.playback_queue || [];
    const key = JSON.stringify(items);
    if (list.dataset.key === key) continue;
    list.dataset.key = key;
    list.parentElement.querySelector('summary').textContent = t('Queue') + ' · ' + items.length;
    list.replaceChildren(...(items.length ? items.map(item => el('div', {class: 'event-row'},
      el('strong', {}, t(item.status)), el('p', {}, item.text),
      button('Cancel audio', async () => { await api(`/api/playback/${item.id}/cancel`, {method: 'POST'}); await refresh(); }))) : [el('p', {}, t('Queue is empty'))]));
  }
}

function renderChannelDashboard() {
  const key = JSON.stringify([window.Locale.language, dashboard.state.channels.map(({playback_queue, ...channel}) => channel), dashboard.state.player_links]);
  if (channelDashboardKey === key) { refreshDashboardQueues(); return; }
  const expanded = new Set([...document.querySelectorAll('[data-channel] details[open][data-queue]')].map(node => node.closest('[data-channel]').dataset.channel));
  channelDashboardKey = key;
  $('channel-list').replaceChildren();
  for (const channel of dashboard.state.channels) {
    const row = el('div', {class: 'job-row', 'data-channel': channel.name},
      el('strong', {}, '#' + channel.name + ' · IRC · ' + t(channel.enabled ? 'On' : 'Off')), el('p', {}, t(channel.connection) + (channel.connection_error ? ' · ' + t(channel.connection_error) : '')),
      channel.transport === 'oauth' ? el('p', {}, t('Twitch events') + ': ' + t(channel.event_connection) + (channel.event_connection_error ? ' · ' + t(channel.event_connection_error) : '')) : null,
      channel.transport === 'oauth' ? el('details', {}, el('summary', {}, t('Event subscriptions')), ...channel.event_subscriptions.map(name => el('p', {}, name)), ...Object.entries(channel.event_errors).map(([name, reason]) => el('p', {class: 'error'}, name + ': ' + t(reason))), channel.reward_recovery ? el('p', {class: 'error'}, channel.reward_recovery.error) : null, el('p', {class: 'muted'}, t('Events during connection gaps may be missed. Managed point redemptions are checked for refunds on reconnect.'))) : null,
      el('div', {class: 'row-actions'},
        button(channel.enabled ? 'Turn off' : 'Turn on', async () => {
          await api(`/api/channels/${channel.name}/connection`, {method: 'POST', body: {enabled: !channel.enabled}});
          await refresh(); if (dashboard.selectedChannel === channel.name) fillChannel(channel.name);
        }),
        button(channel.paused ? 'Resume playback' : 'Pause playback', async () => {
          await api(`/api/channels/${channel.name}/pause`, {method: 'POST', body: {paused: !channel.paused}});
          await refresh();
        }),
        el('a', {href: dashboard.session?.remote_access ? dashboard.state.player_links?.[channel.name] || `/${channel.name}` : `/${channel.name}`, target: '_blank', rel: 'noopener noreferrer', class: 'download'}, t('Open OBS player')),
        button('Edit channel', () => fillChannel(channel.name)),
        button(channel.oauth_authorized ? 'Configure Twitch events' : 'Enable Bits, points and subscriptions', () => { fillChannel(channel.name); $('enable-twitch-events').click(); }),
        button('Delete channel', async () => {
          await api(`/api/channels/${channel.name}`, {method: 'DELETE'});
          if (dashboard.selectedChannel === channel.name) { dashboard.selectedChannel = ''; }
          await refresh(); fillChannel(dashboard.selectedChannel);
        }, 'danger small-button')));
    const queue = el('details', {'data-queue': ''}, el('summary', {}, t('Queue')), el('div', {'data-queue-items': ''}));
    queue.open = expanded.has(channel.name);
    row.append(queue);
    $('channel-list').append(row);
  }
  refreshDashboardQueues();
  if (!dashboard.state.channels.length) $('channel-list').textContent = t('No saved Twitch channels. Add one below.');
}

export function initChannels() {
  $('add-command').addEventListener('click', () => commandRow());
  $('channel-select').addEventListener('change', () => fillChannel($('channel-select').value));
  $('channel-form').addEventListener('submit', action(async event => {
    event.preventDefault(); $('channel-save-status').textContent = ''; const name = $('channel-name').value.trim().toLowerCase(); const commands = {};
    document.querySelectorAll('.command-row').forEach(row => { const key = row.querySelector('input').value.trim().toLowerCase(); if (commands[key]) throw new Error(t('Duplicate command keyword.')); commands[key] = row.querySelector('select').value; });
    await api(`/api/channels/${name}`, {method: 'PUT', body: {name, enabled: dashboard.state.channels.find(c => c.name === name)?.enabled ?? true, paused: $('channel-paused').checked,
      transport: $('channel-transport').value, event_rules: $('channel-transport').value === 'oauth' ? readEventRules() : (dashboard.state.channels.find(c => c.name === name)?.event_rules || []), commands, filter_level: $('channel-filter').value, custom_filters: $('channel-custom').value.split('\n').map(s => s.trim()).filter(Boolean),
      delay_seconds: Number($('channel-delay').value), user_cooldown_seconds: Number($('channel-cooldown').value), max_message_chars: Number($('channel-limit').value)}});
    dashboard.selectedChannel = name; channelKey = ''; await refresh(); fillChannel(name); $('channel-save-status').textContent = t('Channel saved');
  }));
  $('pause-channel').addEventListener('click', action(async () => { if (dashboard.selectedChannel) { await api(`/api/channels/${dashboard.selectedChannel}/pause`, {method: 'POST', body: {paused: !dashboard.latestChannelState?.paused}}); await refresh(); } }));
}

export {commandRow, fillChannel, renderChannelState, renderChannels};
