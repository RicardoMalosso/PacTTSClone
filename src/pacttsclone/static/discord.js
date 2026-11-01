// Host-only Discord webhook configuration and sanitized status.
import {api} from './api.js';
import {$, t} from './dom.js';
import {dashboard} from './state.js';

function renderDiscordStatus() {
  if (!dashboard.discordSnapshot) return;
  $('discord-token-status').textContent = t(dashboard.discordSnapshot.webhook_saved ? 'Webhook saved locally' : 'No webhook saved');
  $('discord-status').textContent = `Discord · ${t(dashboard.discordSnapshot.status)}`;
  $('discord-error').hidden = !dashboard.discordSnapshot.error;
  $('discord-error').textContent = t(dashboard.discordSnapshot.error || '');
  $('discord-forget').disabled = dashboard.discordBusy || !dashboard.discordSnapshot.webhook_saved;
}

async function loadDiscord(fill = false) {
  $('discord-form').hidden = Boolean(dashboard.session?.remote_access);
  if (dashboard.session?.remote_access || dashboard.discordBusy) return;
  dashboard.discordSnapshot = await api('/api/discord');
  if (fill) {
    $('discord-enabled').checked = dashboard.discordSnapshot.enabled;
    $('discord-local').checked = dashboard.discordSnapshot.include_local;
    $('discord-twitch').checked = dashboard.discordSnapshot.include_twitch;
    $('discord-channels').value = dashboard.discordSnapshot.channels.join('\n');
    $('discord-voices').value = dashboard.discordSnapshot.voice_ids.join('\n');
  }
  renderDiscordStatus();
}

async function discordAction(fn) {
  if (dashboard.discordBusy) return;
  dashboard.discordBusy = true;
  for (const node of $('discord-form').querySelectorAll('button')) node.disabled = true;
  try { dashboard.discordSnapshot = await fn(); renderDiscordStatus(); }
  catch (e) { $('discord-error').hidden = false; $('discord-error').textContent = t(e.message); }
  finally {
    dashboard.discordBusy = false;
    for (const node of $('discord-form').querySelectorAll('button')) node.disabled = false;
    $('discord-forget').disabled = !dashboard.discordSnapshot?.webhook_saved;
  }
}

export function initDiscord() {
  $('discord-form').addEventListener('submit', async event => {
    event.preventDefault();
    await discordAction(async () => {
      const url = $('discord-webhook').value.trim();
      if (url) {
        try { await api('/api/discord/webhook', {method: 'PUT', body: {url}}); }
        finally { $('discord-webhook').value = ''; }
      }
      const lines = id => $(id).value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
      return api('/api/discord/config', {method: 'PUT', body: {
        enabled: $('discord-enabled').checked, include_local: $('discord-local').checked,
        include_twitch: $('discord-twitch').checked, channels: lines('discord-channels'),
        voice_ids: lines('discord-voices'),
      }});
    });
  });
  $('discord-test').addEventListener('click', () => discordAction(() => api('/api/discord/test', {method: 'POST'})));
  $('discord-disconnect').addEventListener('click', () => discordAction(async () => {
    const {enabled, include_local, include_twitch, channels, voice_ids} = dashboard.discordSnapshot;
    const result = await api('/api/discord/config', {method: 'PUT', body: {enabled: false, include_local, include_twitch, channels, voice_ids}});
    $('discord-enabled').checked = false; return result;
  }));
  $('discord-forget').addEventListener('click', () => discordAction(async () => {
    const result = await api('/api/discord/webhook', {method: 'DELETE'});
    $('discord-webhook').value = ''; $('discord-enabled').checked = false; return result;
  }));
  window.addEventListener('localechange', renderDiscordStatus);
}

export {loadDiscord, renderDiscordStatus};
