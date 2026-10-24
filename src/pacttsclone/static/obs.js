'use strict';
const t = window.Locale.t;
const channel = location.pathname.split('/')[1], client = crypto.randomUUID();
const audio = document.getElementById('audio'), message = document.getElementById('message'), enable = document.getElementById('enable');
let token, active = null, starting = false, lastTick = performance.now(), recovering = false, owner = false, finishedId = null, blocked = false;
async function request(path, body) {
  const response = await fetch(`/api/channels/${channel}/player/${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PacTTS-Token': token}, body: JSON.stringify({client_id: client, ...body})});
  const result = await response.json(); if (!response.ok) throw new Error(result.detail || 'Player request failed.'); return result;
}
function stop() { audio.pause(); audio.removeAttribute('src'); audio.load(); active = null; }
async function ack(status) { if (active && owner) await request('ack', {item_id: active.id, status}); }
audio.addEventListener('ended', async () => { finishedId = active?.id; try { await ack('played'); } catch { /* cancelled */ } active = null; });
audio.addEventListener('error', async () => { if (active) { try { await ack('error'); } catch { /* lease expired */ } stop(); message.hidden = false; message.textContent = t('Playback failed. Check the control page.'); } });
enable.addEventListener('click', () => { blocked = false; enable.hidden = true; message.hidden = false; message.textContent = t('Resume playback in the channel control page.'); });
// A lost server cannot tell this page to stop; enforce a local heartbeat watchdog too.
setInterval(() => { if (performance.now() - lastTick > 2500) { stop(); message.hidden = false; message.textContent = t('Server disconnected; playback stopped.'); } }, 250);
async function tick() {
  try {
    const result = await request('tick', {}); lastTick = performance.now(); const item = result.item;
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
  } catch {
    stop(); message.hidden = false; message.textContent = t('Server unavailable. Waiting to reconnect…');
    if (!recovering) { recovering = true; try { token = (await (await fetch('/api/session', {cache: 'no-store'})).json()).token; } catch { /* retry next tick */ } finally { recovering = false; } }
  }
  setTimeout(tick, 250);
}
(async () => {
 const share = new URLSearchParams(location.hash.slice(1)); const key = share.get('play') || share.get('admin');
 if (key) {
   const response = await fetch('/api/remote/session', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key, channel})});
   if (!response.ok) throw new Error('Invalid or expired share link.');
   history.replaceState(null, '', location.pathname);
 }
 token = (await (await fetch('/api/session', {cache: 'no-store'})).json()).token; tick(); })().catch(() => { message.hidden = false; message.textContent = t('Cannot connect. Reload this source after starting PacTTSClone.'); });
