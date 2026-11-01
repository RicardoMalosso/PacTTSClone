// Twitch authorization, EventSub rules, rewards, and event history.
import {api, refresh} from './api.js';
import {$, action, button, el, t} from './dom.js';
import {voiceAvailable} from './generation-settings.js';
import {dashboard} from './state.js';

const eventNames = {reward: 'Channel Points reward', bits: 'Bits and Power-ups', subscribe: 'New subscription', gift: 'Gift subscriptions', resub: 'Resubscription message', subscription_end: 'Subscription ended', follow: 'New follower', raid: 'Incoming raid', online: 'Stream online', offline: 'Stream offline'};

const eventTemplates = {reward: '{text}', bits: '{username} used {bits} Bits. {text}', subscribe: 'Welcome {username}', gift: '{username} gifted {total} subscriptions', resub: '{username}: {text}', subscription_end: "{username}'s subscription ended", follow: 'Welcome {username}', raid: '{username} raided with {viewers} viewers', online: 'Stream is online', offline: 'Stream is offline'};

let twitchAuthChannel = '';

let twitchAuthBusy = false;

function eventRuleRow(rule = {}) {
  const kind = el('select', {'aria-label': t('Event type')}, ...Object.entries(eventNames).map(([value, name]) => el('option', {value}, t(name))));
  kind.value = rule.kind || 'reward';
  const voice = el('select', {'aria-label': t('Event voice'), 'data-voice': ''});
  const reward = el('input', {'aria-label': t('Reward ID'), placeholder: t('Reward ID'), value: rule.reward_id || ''});
  const minimum = el('input', {type: 'number', min: '1', max: '10000000', 'aria-label': t('Minimum Bits'), value: rule.min_bits || 1});
  const template = el('textarea', {rows: '2', maxlength: '1000', 'aria-label': t('Event text template')}); template.value = rule.template || eventTemplates[kind.value];
  const row = el('section', {class: 'event-rule card'}, el('label', {}, t('Event type'), kind), el('label', {}, t('Event voice'), voice), el('label', {}, t('Reward ID'), reward), el('label', {}, t('Minimum Bits'), minimum), el('label', {}, t('Event text template'), template), button('Remove', () => row.remove()));
  const visibility = () => { reward.parentElement.hidden = kind.value !== 'reward'; minimum.parentElement.hidden = kind.value !== 'bits'; };
  let previousKind = kind.value;
  kind.addEventListener('change', () => { if (template.value === eventTemplates[previousKind]) template.value = eventTemplates[kind.value]; previousKind = kind.value; visibility(); }); visibility();
  $('event-rules').append(row); refreshEventVoices(); voice.value = rule.voice_id || '';
}

function refreshEventVoices() {
  for (const select of document.querySelectorAll('#event-rules [data-voice]')) {
    const key = JSON.stringify([window.Locale.language, dashboard.state.active_engine, dashboard.state.voices.map(v => [v.id, v.title, voiceAvailable(v)])]);
    if (select.dataset.key === key) continue;
    const selected = select.value; select.dataset.key = key;
    select.replaceChildren(el('option', {value: ''}, t('Choose voice')), ...dashboard.state.voices.filter(voiceAvailable).map(v => el('option', {value: v.id}, v.title))); select.value = selected;
  }
}

function readEventRules() {
  return [...document.querySelectorAll('.event-rule')].map(row => {
    const rule = {kind: row.querySelector('select').value, voice_id: row.querySelector('[data-voice]').value, reward_id: row.querySelector('input:not([type])').value.trim(), min_bits: Number(row.querySelector('input[type=number]').value), template: row.querySelector('textarea').value};
    if (!rule.voice_id) throw new Error(t('Choose a voice for each event rule.'));
    return rule;
  });
}

function updateTwitchMode() {
  const oauth = $('channel-transport').value === 'oauth';
  $('enable-twitch-events').hidden = oauth;
  $('disable-twitch-events').hidden = !oauth;
  $('event-rules-panel').hidden = !oauth;
  $('twitch-oauth-panel').hidden = !oauth || Boolean(dashboard.session?.remote_access);
  twitchAuthChannel = ''; $('twitch-auth-status').textContent = ''; $('twitch-device').hidden = true; $('twitch-rewards').replaceChildren();
  if (oauth && !dashboard.session?.remote_access && dashboard.selectedChannel && dashboard.state.channels.some(c => c.name === dashboard.selectedChannel)) loadTwitchAuth().catch(e => { $('twitch-auth-status').textContent = t(e.message); });
}

async function loadTwitchAuth() {
  const channel = dashboard.selectedChannel;
  if (!channel || dashboard.session?.remote_access || twitchAuthBusy) return;
  twitchAuthBusy = true;
  try {
    const info = await api(`/api/twitch/${channel}/authorization`);
    if (channel !== dashboard.selectedChannel) return;
    twitchAuthChannel = channel; dashboard.twitchAuthPending = info.pending;
    $('twitch-auth-status').textContent = info.error || (info.pending ? t('Waiting for Twitch authorization…') : info.authorized ? t('Authorized broadcaster') + ': ' + info.login + ' · ' + info.scopes.join(', ') : t('Not authorized'));
    $('twitch-device').hidden = !info.pending; $('twitch-user-code').textContent = info.user_code || '';
    $('twitch-activate').href = info.verification_uri || 'https://www.twitch.tv/activate';
    $('twitch-authorize').disabled = Boolean(info.pending);
    if (info.authorized && !info.pending) await refresh();
  } finally { twitchAuthBusy = false; }
}

const rewardLimitFields = [
  ['global_cooldown_seconds', 'Reward cooldown (seconds) · 0 disables', 604800],
  ['max_per_stream', 'Redemptions per stream · 0 disables', 2147483647],
  ['max_per_user_per_stream', 'Redemptions per user per stream · 0 disables', 2147483647]
];

function rewardLimitsEditor(reward = {}, disabled = false) {
  return el('div', {class: 'reward-limits'}, ...rewardLimitFields.map(([key, label, maximum]) =>
    el('label', {}, t(label), el('input', {type: 'number', min: '0', max: maximum, step: '1', value: reward[key] || 0, 'data-reward-limit': key, 'aria-label': t(label), ...(disabled ? {disabled: ''} : {})}))));
}

function readRewardLimits(container) {
  return Object.fromEntries([...container.querySelectorAll('[data-reward-limit]')].map(input => [input.dataset.rewardLimit, Number(input.value)]));
}

async function loadTwitchRewards() {
  const channel = dashboard.selectedChannel; const rewards = await api(`/api/twitch/${channel}/rewards`);
  if (channel !== dashboard.selectedChannel) return;
  $('twitch-rewards').replaceChildren(...rewards.map(r => {
    const limits = rewardLimitsEditor(r, !r.manageable);
    return el('div', {class: 'job-row', 'data-reward-id': r.id}, el('strong', {}, `${r.title} · ${r.cost}`), el('p', {class: 'muted'}, `${r.id} · ${t(r.manageable ? 'Automatic fulfillment / refund' : 'Manage in Twitch')}`), limits,
      r.manageable ? button('Save reward limits', async () => { await api(`/api/twitch/${channel}/rewards/${encodeURIComponent(r.id)}`, {method: 'PATCH', body: readRewardLimits(limits)}); if (channel === dashboard.selectedChannel) await loadTwitchRewards(); }) : el('p', {}, t('Edit limits for this reward in Twitch.')),
      button('Use reward', () => eventRuleRow({kind: 'reward', reward_id: r.id})));
  }));
}

function renderTwitchEvents(events) {
  let panel = $('twitch-event-history');
  if (!panel) { panel = el('div', {id: 'twitch-event-history'}); $('chat-events').parentElement.append(panel); }
  panel.replaceChildren(...events.map(e => el('div', {class: 'event-row'}, el('strong', {}, `${t(eventNames[e.kind] || e.kind)} · ${e.username} · ${t(e.status)}`), el('p', {}, e.text), e.reason ? el('p', {class: 'error'}, t(e.reason)) : null, el('p', {class: 'muted'}, `${t('Redemption status')}: ${e.settlement}${e.settlement_error ? ' · ' + t(e.settlement_error) : ''}`))));
}

export function initTwitch() {
  $('enable-twitch-events').addEventListener('click', () => { $('channel-transport').value = 'oauth'; updateTwitchMode(); $('twitch-oauth-panel').scrollIntoView({behavior: 'smooth', block: 'start'}); });
  $('disable-twitch-events').addEventListener('click', () => { $('channel-transport').value = 'irc'; updateTwitchMode(); });
  $('add-event-rule').addEventListener('click', () => eventRuleRow());
  $('twitch-authorize').addEventListener('click', action(async () => {
    if (!dashboard.selectedChannel || !dashboard.state.channels.some(c => c.name === dashboard.selectedChannel)) throw new Error(t('Save the channel first.'));
    await api(`/api/twitch/${dashboard.selectedChannel}/authorization`, {method: 'POST', body: {features: [...$('twitch-features').querySelectorAll('input:checked')].map(n => n.value)}});
    await loadTwitchAuth();
  }));
  $('twitch-forget').addEventListener('click', action(async () => {
    if (dashboard.selectedChannel) { await api(`/api/twitch/${dashboard.selectedChannel}/authorization`, {method: 'DELETE'}); await loadTwitchAuth(); await refresh(); }
  }));
  $('twitch-new-reward-limits').append(rewardLimitsEditor());
  $('twitch-load-rewards').addEventListener('click', action(loadTwitchRewards));
  $('twitch-create-reward').addEventListener('click', action(async () => {
    const channel = dashboard.selectedChannel;
    const reward = await api(`/api/twitch/${channel}/rewards`, {method: 'POST', body: {title: $('twitch-reward-title').value, cost: Number($('twitch-reward-cost').value), ...readRewardLimits($('twitch-new-reward-limits'))}});
    if (channel !== dashboard.selectedChannel) return;
    eventRuleRow({kind: 'reward', reward_id: reward.id}); await loadTwitchRewards();
  }));
  setInterval(() => { if (dashboard.twitchAuthPending && twitchAuthChannel === dashboard.selectedChannel && !dashboard.session?.remote_access) loadTwitchAuth().catch(() => {}); }, 5000);
  window.addEventListener('localechange', () => { refreshEventVoices(); });
  window.addEventListener('localechange', () => {
    for (const row of document.querySelectorAll('.event-rule')) {
      const kind = row.querySelector('select');
      for (const option of kind.options) option.textContent = t(eventNames[option.value]);
      const fields = [kind, row.querySelector('[data-voice]'), row.querySelector('input:not([type])'), row.querySelector('input[type=number]'), row.querySelector('textarea')];
      ['Event type', 'Event voice', 'Reward ID', 'Minimum Bits', 'Event text template'].forEach((key, i) => { fields[i].setAttribute('aria-label', t(key)); fields[i].parentElement.firstChild.nodeValue = t(key); });
    }
  });
}

export {eventRuleRow, loadTwitchAuth, readEventRules, refreshEventVoices, renderTwitchEvents, updateTwitchMode};
