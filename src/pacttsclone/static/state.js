// Mutable values shared across dashboard features. The server remains authoritative.
export const dashboard = {
  runtimeSetup: {ready: false},
  showSetupTab: false,
  modelDownloaded: 0,
  realtime: null,
  session: undefined,
  state: {jobs: [], voices: [], channels: []},
  config: undefined,
  discordSnapshot: null,
  discordBusy: false,
  selectedChannel: location.pathname.endsWith('/control') ? location.pathname.split('/')[1] : '',
  completedJob: null,
  busy: false,
  lastMonitor: null,
  voicesKey: '',
  historyKey: '',
  latestChannelState: null,
  suppressAutoplay: false,
  requesterId: undefined,
  bugPlayerReady: false,
  userSelectedTab: false,
  twitchAuthPending: false,
};

// Subscribers run after the snapshot changes, for both REST and SSE updates.
const listeners = new Set();
export function subscribeState(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export async function updateState(value, sections = null) {
  dashboard.state = value;
  for (const listener of listeners) await listener(value, sections);
}
