'use strict';
const $ = (id) => document.getElementById(id);
let session;
let busy = false;
let currentJob = null;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(url, options = {}) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Verifique os campos e tente novamente.');
  }
  return response.json();
}

try { $('autoplay').checked = localStorage.getItem('pactts-autoplay') === 'true'; } catch { /* optional storage */ }
$('autoplay').addEventListener('change', () => {
  try { localStorage.setItem('pactts-autoplay', String($('autoplay').checked)); } catch { /* optional storage */ }
});
$('text').addEventListener('input', () => { $('count').textContent = `${$('text').value.length} / 2000`; });
$('stop').addEventListener('click', () => { $('player').pause(); $('player').currentTime = 0; });

function clearResult() {
  $('player').pause();
  $('player').removeAttribute('src');
  $('player').load();
  $('player').hidden = true;
  $('actions').hidden = true;
  $('download').removeAttribute('href');
  $('error').hidden = true;
  $('playback-note').textContent = '';
}

async function watch(jobId) {
  while (true) {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    $('status').textContent = job.stage;
    if (job.status === 'failed') {
      currentJob = null;
      throw new Error(job.error);
    }
    if (job.status === 'succeeded') {
      $('status').textContent = `MP3 pronto · ${job.elapsed_seconds} s de processamento`;
      $('player').src = job.output_url;
      $('player').hidden = false;
      $('actions').hidden = false;
      $('download').href = job.output_url;
      $('download').download = `pactts-${job.id}.mp3`;
      if ($('autoplay').checked) {
        try { await $('player').play(); }
        catch { $('playback-note').textContent = 'O navegador bloqueou a reprodução automática. Aperte play para ouvir.'; }
      }
      currentJob = null;
      return;
    }
    await sleep(1000);
  }
}

$('generate-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  $('generate').disabled = true;
  clearResult();
  currentJob = null;
  try {
    const reference = $('reference').files[0];
    if (!reference || !reference.name.toLowerCase().endsWith('.mp3')) throw new Error('Escolha um MP3 de referência.');
    if (reference.size > session.max_upload_bytes) throw new Error('MP3 excede o limite de 20 MiB.');
    if (!$('text').value.trim()) throw new Error('Digite o texto para gerar.');
    $('status').textContent = 'Enviando referência ao processo local…';
    const job = await api('/api/jobs', {
      method: 'POST', headers: {'X-PacTTS-Token': session.token},
      body: new FormData($('generate-form')),
    });
    currentJob = job.id;
    await watch(currentJob);
  } catch (error) {
    $('error').textContent = error.message;
    $('error').hidden = false;
    $('status').textContent = currentJob ? 'Conexão interrompida. A geração pode continuar no processo local.' : 'Não foi possível gerar o MP3.';
  } finally {
    busy = false;
    $('generate').disabled = false;
  }
});

async function init() {
  try {
    session = await api('/api/session');
    const health = await api('/api/health');
    const missing = [];
    if (!health.ffmpeg_available) missing.push('FFmpeg não encontrado no PATH');
    if (!health.inference_installed) missing.push('instale as dependências de inferência');
    $('health').textContent = missing.length ? missing.join(' · ') : `Ambiente pronto · dispositivo: ${health.device_requested} · ${health.offline ? 'modo offline' : 'download inicial habilitado'}`;
    $('generate').disabled = false;
  } catch (error) {
    $('health').textContent = `Não foi possível iniciar: ${error.message}. Atualize a página.`;
  }
}
init();
