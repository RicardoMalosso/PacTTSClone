// Tab navigation and moving shared playback controls between panes.
import {fillChannel, renderChannelState, renderChannels} from './channels.js';
import {$, el, error} from './dom.js';
import {openBugVideo, stopBugVideo} from './help.js';
import {dashboard} from './state.js';

let localPlaybackHost;

let channelControls;

let channelControlsHost;

function tab(name) {
  if (name === 'general') name = 'studio';
  if (!dashboard.runtimeSetup.ready && !['setup', 'config', 'engines'].includes(name)) name = 'setup';
  if (name === 'bugs' && !dashboard.bugPlayerReady) { openBugVideo(); return; }
  window.Locale.apply();
  if (name !== 'bugs') stopBugVideo();
  const general = name === 'studio';
  if (general) dashboard.selectedChannel = 'playbackMain';
  else if (name === 'channels' && dashboard.selectedChannel === 'playbackMain') fillChannel('');
  window.Locale.bind($('playback-heading'), general ? 'Local OBS Sources' : 'Twitch & OBS');
  window.Locale.bind($('playback-description'), general ? 'Queue any generated MP3 here without connecting to Twitch.' : 'IRC chat starts automatically for saved channels. Optionally authorize Bits, Channel Points and subscriptions.');
  (general ? localPlaybackHost : channelControlsHost).append(channelControls);
  $('channel-form').hidden = general;
  $('channel-dashboard').hidden = general;
  $('general-form').hidden = !general;
  $('chat-events').parentElement.hidden = general;
  if (general && dashboard.state.general_playback) {
    $('general-delay').value = dashboard.state.general_playback.delay_seconds;
    $('general-filter').value = dashboard.state.general_playback.filter_level;
    $('general-custom').value = dashboard.state.general_playback.custom_filters.join('\n');
  }
  renderChannels();
  if (dashboard.session) renderChannelState().catch(e => error(e.message));
  const pane = name;
  document.querySelectorAll('.pane').forEach(p => { p.hidden = p.id !== 'pane-' + pane; });
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
}

export function initNavigation() {
  localPlaybackHost = el('section', {id: 'local-playback-host'});
  $('pane-studio').append($('general-form'), localPlaybackHost);
  channelControls = $('channel-connection').parentElement;
  channelControlsHost = channelControls.parentElement;
  document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { dashboard.userSelectedTab = true; tab(b.dataset.tab); }));
}

export {tab};
