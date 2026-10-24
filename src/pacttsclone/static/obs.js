'use strict';
const t = window.Locale.t;
const channel = location.pathname.split('/')[1], client = crypto.randomUUID();
const audio = document.getElementById('audio'), message = document.getElementById('message'), enable = document.getElementById('enable');
let shareKey = null, authRetried = false, halted = false, retryDelay = 250;
let token, active = null, starting = false, lastTick = performance.now(), recovering = false, owner = false, finishedId = null, blocked = false;
async function request(path, body) {
  const response = await fetch(`/api/channels/${channel}/player/${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PacTTS-Token': token}, body: JSON.stringify({client_id: client, ...body})});
  const result = await response.json(); if (!response.ok) { const error = new Error(result.detail || 'Player request failed.'); error.status = response.status; throw error; } return result;
}
function stop() { audio.pause(); audio.removeAttribute('src'); audio.load(); active = null; }
async function ack(status) { if (active && owner) await request('ack', {item_id: active.id, status}); }
audio.addEventListener('ended', async () => { finishedId = active?.id; try { await ack('played'); } catch { /* cancelled */ } active = null; });
audio.addEventListener('error', async () => { if (active) { try { await ack('error'); } catch { /* lease expired */ } stop(); message.hidden = false; message.textContent = t('Playback failed. Check the control page.'); } });
enable.addEventListener('click', () => { blocked = false; enable.hidden = true; message.hidden = false; message.textContent = t('Resume playback in the channel control page.'); });
// A lost server cannot tell this page to stop; enforce a local heartbeat watchdog too.
setInterval(() => { if (!halted && performance.now() - lastTick > 2500) { stop(); message.hidden = false; message.textContent = t('Server disconnected; playback stopped.'); } }, 250);
async function tick() {
  if (halted) return;
  try {
    const result = await request('tick', {}); retryDelay = 250; authRetried = false; lastTick = performance.now(); const item = result.item;
    owner = result.owner;
    if (result.paused) { stop(); }
    else {
      if (active && (!item || item.id !== active.id || !['ready', 'playing'].includes(item.status))) stop();
      if (item && item.id !== finishedId && (owner ? item.status === 'ready' : item.status === 'playing') && !active && !starting && !blocked) {
        starting = true; active = item; audio.src = item.output_url;
        try {
          // Authorize against cancellations before the first audible sample.
          await ack('playing');
          if (!owner && item.started_at) audio.currentTime = Math.max(0, result.server_time - item.started_at);
          await audio.play(); message.hidden = true; enable.hidden = true;
        } catch (e) {
          try { await ack('error'); } catch { /* cancellation wins */ }
          stop(); blocked = true; enable.hidden = false; message.hidden = false;
          message.textContent = t('Audio blocked or cancelled. Enable audio and resume in controls.');
        } finally { starting = false; }
      }
    }
  } catch (error) {
    stop(); message.hidden = false;
    if (error.status === 403) {
      if (shareKey && !authRetried) {
        authRetried = true;
        try { await bootstrap(shareKey); await refreshSession(); }
        catch { haltExpired(); }
      } else haltExpired();
    } else {
      message.textContent = t('Server unavailable. Waiting to reconnect…');
      retryDelay = Math.min(10000, retryDelay * 2);
      if (!recovering) { recovering = true; try { await refreshSession(); } catch (e) { if (e.status === 403) haltExpired(); } finally { recovering = false; } }
    }
  }
  if (!halted) setTimeout(tick, retryDelay);
}
function haltExpired() { halted = true; enable.hidden = true; message.hidden = false; message.textContent = t('Shared link expired or unauthorized. Open the latest complete OBS link from Configuration.'); }
async function bootstrap(key) {
  const response = await fetch('/api/remote/session', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key, channel})});
  if (!response.ok) { const error = new Error('Invalid or expired share link.'); error.status = response.status; throw error; }
}
async function refreshSession() {
  const response = await fetch('/api/session', {cache: 'no-store'});
  if (!response.ok) { const error = new Error('Session unavailable'); error.status = response.status; throw error; }
  token = (await response.json()).token;
}

(async () => {
 const share = new URLSearchParams(location.hash.slice(1)); shareKey = share.get('play') || share.get('admin');
 if (shareKey) { await bootstrap(shareKey); history.replaceState(null, '', location.pathname); }
 await refreshSession(); tick(); })().catch(error => { if (error.status === 403) haltExpired(); else { message.hidden = false; message.textContent = t('Cannot connect. Reload this source after starting PacTTSClone.'); } });
