'use strict';
(() => {
  const pt = {
    'Report a bug': 'Relatar um problema',
    'Watch the bug reporting guide.': 'Assista ao guia para relatar problemas.',
    'Bug reporting guide': 'Guia para relatar problemas',
    'The video loads three seconds after you open this tab.': 'O vídeo carrega três segundos depois de abrir esta aba.',
    'Starting the video in three seconds…': 'O vídeo começará em três segundos…',
    'If autoplay is blocked, press play in the video.': 'Se a reprodução automática for bloqueada, aperte play no vídeo.',
    'Watch on YouTube ↗': 'Assistir no YouTube ↗',

    'unprepared': 'não preparada',
    'Prepare for first use': 'Preparar para o primeiro uso',
    'Retry preparation': 'Tentar preparação novamente',
    'Cancel preparation': 'Cancelar preparação',
    'Preparing for first use…': 'Preparando para o primeiro uso…',
    'Not prepared for first use. Click Prepare to download required models and save the reference transcript locally.': 'Não preparada para o primeiro uso. Clique em Preparar para baixar os modelos necessários e salvar a transcrição localmente.',
    'The first preparation may download models. You can cancel and retry.': 'A primeira preparação pode baixar modelos. Você pode cancelar e tentar novamente.',
    'Some voices need preparation · open Voices': 'Algumas vozes precisam de preparação · abrir Vozes',

    'General playback': 'Reprodução geral',
    'Queue on general player': 'Adicionar ao player geral',
    'Queued on general player.': 'Adicionado à fila do player geral.',
    'Queue any generated MP3 here without connecting to Twitch.': 'Reproduza qualquer MP3 gerado aqui sem conectar à Twitch.',
    'Save playback settings': 'Salvar ajustes de reprodução',
    'Open general control page': 'Abrir painel de controle geral',
    'Open general OBS player': 'Abrir player OBS geral',
    'Active': 'Ativo', 'Disabled': 'Desativado',
    'Unavailable on this platform; buttons and focused-browser shortcut work.': 'Indisponível nesta plataforma; use os botões ou o atalho com o navegador em foco.',
    'Unavailable: shortcut is in use.': 'Indisponível: o atalho já está em uso.',
    'custom word filter': 'filtro de palavras personalizado', 'mandatory/profanity word filter': 'filtro obrigatório / de palavrões',
    'user cooldown': 'intervalo por usuário', 'empty or overlong message': 'mensagem vazia ou longa demais',
    'Install FFmpeg (ffmpeg and ffprobe) and add it to PATH.': 'Instale FFmpeg (ffmpeg e ffprobe) e adicione ao PATH.',
    'Audio processing exceeded 60 seconds.': 'O processamento de áudio excedeu 60 segundos.',
    'Could not process the audio. Check that the MP3 is valid.': 'Não foi possível processar o áudio. Verifique se o MP3 é válido.',
    'The reference must be a valid MP3 file.': 'A referência precisa ser um arquivo MP3 válido.',
    'Use a reference of 1–30 seconds; recommended: 3–10 seconds.': 'Use uma referência de 1 a 30 segundos; recomendado: 3 a 10 segundos.',
    'The reference is silent. Choose a clip with audible speech.': 'A referência está silenciosa. Escolha um trecho com fala audível.',
    'Choose a nonempty MP3 file.': 'Selecione um MP3 não vazio.',
    'Another generation is running. Wait for it to finish.': 'Já existe uma geração em andamento. Aguarde a conclusão.',
    'This share link has expired or is invalid.': 'Este link de compartilhamento expirou ou é inválido.',
    'Open the complete shared admin or OBS link.': 'Abra o link completo de compartilhamento do painel ou OBS.',
    'Generation queue is full.': 'A fila de geração está cheia.',
    'Wait for generation or cancel the queue before changing hardware.': 'Aguarde a geração ou cancele a fila antes de alterar o hardware.',
    'Cancelled by the streamer.': 'Cancelado pelo streamer.',
    'This voice is not ready. Finish or retry its transcription first.': 'Esta voz ainda não está pronta. Conclua ou tente novamente a transcrição.',
    'Voice not found.': 'Voz não encontrada.', 'Channel not found.': 'Canal não encontrado.',
    'The current channel filter blocks this text.': 'O filtro atual do canal bloqueia este texto.',
    'Use a title of 1–100 characters and a transcript up to 4000 characters.': 'Use um título de 1–100 caracteres e uma transcrição de até 4000 caracteres.',
    'Save a channel first to get an OBS-only link.': 'Salve um canal primeiro para obter um link somente para OBS.',

    'PacTTSClone · Local voice studio': 'PacTTSClone · Estúdio local de voz',
    'LOCAL VOICE STUDIO · v0.2': 'ESTÚDIO LOCAL DE VOZ · v0.2',
    'Stop playback / panic': 'Parar reprodução / emergência', 'Cancel all work': 'Cancelar todos os trabalhos',
    'Generate': 'Gerar', 'Voices': 'Vozes', 'History': 'Histórico', 'Configuration': 'Configuração',
    'Checking local environment…': 'Verificando ambiente local…', 'System CPU': 'CPU do sistema',
    'N/A': 'N/D', 'Worker RAM': 'RAM do processo de geração', 'System RAM': 'RAM do sistema',
    'Device-wide VRAM': 'VRAM total em uso na GPU', 'GPU utilization (device)': 'Utilização da GPU (total)',
    'REFERENCE AUDIO → NEW SPEECH': 'ÁUDIO DE REFERÊNCIA → NOVA FALA',
    'Your voices. Your machine.': 'Suas vozes. Seu computador.',
    'Select a saved voice or upload a short MP3. All inference happens locally.': 'Selecione uma voz salva ou envie um MP3 curto. Toda a geração acontece localmente.',
    '01 · Voice reference': '01 · Referência de voz', 'Saved voice': 'Voz salva',
    'Upload an MP3 instead': 'Enviar um MP3 em vez disso',
    'MP3 · recommended 3–10 seconds, up to 20 MiB': 'MP3 · recomendado: 3–10 segundos, até 20 MiB',
    'Exact reference transcript': 'Transcrição exata da referência',
    'optional; blank uses local CPU transcription': 'opcional; em branco, transcreve localmente na CPU',
    '02 · Speech': '02 · Fala', 'What should the voice say?': 'O que a voz deve dizer?',
    'Punctuation is interpreted by OmniVoice.': 'A pontuação é interpretada pelo OmniVoice.',
    'Generation settings': 'Ajustes de geração', 'Language': 'Idioma', 'Português': 'Português',
    'English': 'Inglês', 'Automatic': 'Automático', 'Speed': 'Velocidade', 'Steps': 'Passos',
    'Generate MP3 ↗': 'Gerar MP3 ↗', 'GENERATION MONITOR': 'MONITOR DE GERAÇÃO',
    'Your MP3 will appear here.': 'Seu MP3 aparecerá aqui.',
    'Pipeline milestones, not an estimated completion time.': 'Etapas concluídas, não uma estimativa de tempo restante.',
    'Current stage:': 'Etapa atual:', '. Model loading/downloads have no reliable ETA.': '. Carregamentos e downloads não têm previsão confiável.',
    'Cancel this generation': 'Cancelar esta geração', 'Stop / restart': 'Parar / voltar ao início',
    'Download MP3 ↓': 'Baixar MP3 ↓', 'Play automatically after generation': 'Tocar automaticamente após a geração',
    'Hardware & timing report': 'Relatório de hardware e tempos', 'No completed report yet.': 'Nenhum relatório concluído ainda.',
    'Generation queue': 'Fila de geração', 'Saved voices': 'Vozes salvas',
    'A voice preset reuses one MP3 and its saved transcript. No per-person model training.': 'Uma voz predefinida reutiliza um MP3 e sua transcrição salva. Não há treinamento de modelo por pessoa.',
    'Title': 'Título', 'Reference MP3': 'MP3 de referência', 'Thumbnail (optional, up to 2 MiB)': 'Miniatura (opcional, até 2 MiB)',
    'Exact transcript (optional)': 'Transcrição exata (opcional)', 'Save voice': 'Salvar voz',
    'Read public Twitch chat. Commands queue local speech; this does not verify Bits or channel-point purchases.': 'Lê o chat público da Twitch. Comandos geram falas localmente; isso não verifica compras com Bits ou pontos do canal.',
    'Channel configuration': 'Configuração do canal', 'Existing channel': 'Canal existente', 'Create a channel': 'Criar um canal',
    'Channel login': 'Nome de usuário do canal', 'Connect and monitor chat': 'Conectar e acompanhar o chat',
    'Pause playback': 'Pausar reprodução', 'Delay before each audio (seconds)': 'Espera antes de cada áudio (segundos)',
    'User cooldown (seconds)': 'Intervalo por usuário (segundos)', 'Message limit': 'Limite de caracteres',
    'Word filter': 'Filtro de palavras', 'Always-on slur blocklist only (default)': 'Somente lista de ofensas discriminatórias, sempre ativa (padrão)',
    'Slur blocklist + profanity': 'Ofensas discriminatórias + palavrões',
    'Slur blocklist + profanity + stricter adult terms': 'Ofensas discriminatórias + palavrões + termos adultos mais restritos',
    'Basic PT/EN lexical filtering; it cannot detect every evasion or enforce every Twitch rule.': 'Filtro básico de palavras em PT/EN; não detecta toda tentativa de contorno nem garante todas as regras da Twitch.',
    'Custom blocked words / phrases · one per line': 'Palavras / frases bloqueadas personalizadas · uma por linha',
    'Commands → saved voice': 'Comandos → voz salva', 'Add command': 'Adicionar comando', 'Save channel': 'Salvar canal',
    'Channel controls': 'Controles do canal', 'Choose a channel.': 'Selecione um canal.',
    'Use only the OBS page as an audio source. The control page is silent unless you preview an audio.': 'Use somente a página OBS como fonte de áudio. O painel de controle fica em silêncio, exceto ao pré-ouvir um áudio.',
    'Pause / resume playback': 'Pausar / retomar reprodução', 'Incoming TTS commands & moderation': 'Comandos TTS recebidos e moderação',
    'Audio history': 'Histórico de áudios',
    "Replay sends the existing MP3 back through the channel's countdown. Preview plays only in this browser.": 'Repetir envia o MP3 existente para a contagem regressiva do canal. Pré-ouvir toca somente neste navegador.',
    'Download generation log (JSONL)': 'Baixar registro de gerações (JSONL)',
    'Choose how your computer generates speech. Changes require an idle generation queue.': 'Escolha como seu computador gera a fala. Para alterar, a fila de geração precisa estar vazia.',
    'Processing device': 'Dispositivo de processamento',
    'Automatic · NVIDIA GPU if usable, otherwise CPU': 'Automático · GPU NVIDIA quando disponível; caso contrário, CPU',
    'NVIDIA GPU (CUDA) · saves CPU time, uses VRAM': 'GPU NVIDIA (CUDA) · poupa CPU e usa VRAM',
    'CPU only · slower, leaves GPU available for games': 'Somente CPU · mais lento, deixa a GPU disponível para jogos',
    'GPU = graphics card; VRAM = its dedicated memory. CPU = main processor; RAM = system memory. Whisper transcription runs on CPU in all modes. AMD/Intel/Apple GPU backends are not implemented.': 'GPU = placa de vídeo; VRAM = memória dedicada dela. CPU = processador principal; RAM = memória do sistema. A transcrição Whisper usa CPU em todos os modos. GPUs AMD/Intel/Apple ainda não são suportadas.',
    'CPU threads': 'Threads da CPU', 'Keep the model loaded between messages (faster; keeps memory occupied)': 'Manter o modelo carregado entre mensagens (mais rápido; mantém a memória ocupada)',
    'Global stop-playback shortcut (Windows)': 'Atalho global para parar reprodução (Windows)',
    'Panic stops current/countdown audio and pauses channels. Resume playback in Twitch & OBS. It works outside the browser on Windows when the shortcut is registered successfully.': 'O botão de emergência interrompe o áudio atual e a contagem regressiva, e pausa os canais. Retome em Twitch & OBS. No Windows, o atalho funciona fora do navegador quando registrado com sucesso.',
    'Maximum pending generations': 'Máximo de gerações pendentes', 'Save configuration': 'Salvar configuração',
    'CPU seconds count time across worker threads and can exceed elapsed seconds. GPU stage/stream time includes CPU coordination and is not an exact GPU-busy counter. Unknown measurements appear as N/A.': 'Os segundos de CPU somam as threads e podem superar o tempo decorrido. O tempo da etapa/stream GPU inclui coordenação da CPU e não mede precisamente o tempo de GPU ocupada. Medições indisponíveis aparecem como N/D.',
    'Local inference · transparent accounting': 'Geração local · medições transparentes',
    'Write the new text here…': 'Escreva o novo texto aqui…', 'Lula, Dilma, narrator…': 'Lula, Dilma, narrador…',
    'Leave blank to prepare and save a local transcription once.': 'Deixe em branco para gerar e salvar a transcrição local uma vez.',
    'Choose voice': 'Selecione a voz', 'Remove': 'Remover', 'Save edits': 'Salvar alterações',
    'Retry transcription': 'Tentar transcrição novamente', 'Delete voice': 'Excluir voz',
    'No saved voices yet.': 'Nenhuma voz salva ainda.', 'Cancel generation': 'Cancelar geração',
    'No pending generations.': 'Nenhuma geração pendente.', 'Preview here': 'Pré-ouvir aqui',
    'Download MP3': 'Baixar MP3', 'Replay on OBS': 'Repetir no OBS', 'Timing report': 'Relatório de tempos',
    'Per-stage hardware accounting': 'Medições de hardware por etapa', 'Open OBS player': 'Abrir player OBS',
    'Open separate control page': 'Abrir painel de controle separado', 'Choose a saved channel.': 'Selecione um canal salvo.',
    'Playback paused': 'Reprodução pausada', 'Playback enabled': 'Reprodução habilitada',
    'OBS player connected': 'Player OBS conectado', 'No active OBS player': 'Nenhum player OBS ativo',
    'Cancel audio': 'Cancelar áudio', 'accepted': 'aceito', 'blocked': 'bloqueado',
    'worker RAM peak': 'pico de RAM do processo', 'CUDA allocation peak': 'pico de alocação CUDA',
    'CPU setup': 'Preparar CPU', 'Decode MP3': 'Decodificar MP3', 'Load / download': 'Carregar / baixar',
    'Transcribe': 'Transcrever', 'Generate speech': 'Gerar fala', 'Encode MP3': 'Codificar MP3',
    'working…': 'processando…', 'pending device selection': 'aguardando seleção de dispositivo',
    'queued': 'na fila', 'running': 'processando', 'succeeded': 'concluído', 'failed': 'falhou',
    'cancelled': 'cancelado', 'pending': 'pendente', 'ready': 'pronto', 'countdown': 'contagem regressiva',
    'playing': 'tocando', 'played': 'reproduzido', 'error': 'erro', 'interrupted': 'interrompido',
    'complete': 'concluído', 'starting': 'iniciando', 'cancelling': 'cancelando',
    'decode': 'decodificar', 'load_model': 'carregar modelo', 'transcribe': 'transcrever',
    'inference': 'gerar fala', 'encode': 'codificar', 'configure': 'preparar CPU',
    'connected': 'conectado', 'disconnected': 'desconectado', 'connecting': 'conectando', 'reconnecting': 'reconectando',
    'Local': 'Local', 'Voice': 'Voz', 'Uploaded voice': 'Voz enviada', 'Replay': 'Repetição',
    'Worker unloaded': 'Processo descarregado', 'Voice title': 'Título da voz', 'Saved transcript': 'Transcrição salva', 'Saved reference transcript': 'Transcrição da referência salva',
    'Command keyword': 'Palavra-chave do comando', 'Command voice': 'Voz do comando', 'OBS source URL': 'URL da fonte OBS',
    'FFmpeg ready': 'FFmpeg pronto', 'FFmpeg missing from PATH': 'FFmpeg ausente no PATH',
    'Inference dependencies installed': 'Dependências de geração instaladas', 'Install inference dependencies': 'Instale as dependências de geração',
    'Initial model download can take time': 'O download inicial do modelo pode demorar',
    'Configuration saved. Model will load on the selected device for the next job.': 'Configuração salva. O modelo será carregado no dispositivo selecionado no próximo trabalho.',
    'Connection interrupted: ': 'Conexão interrompida: ', 'Could not initialize. Refresh after checking the server terminal.': 'Não foi possível iniciar. Verifique o terminal do servidor e atualize a página.',
    'Choose an MP3 reference.': 'Selecione um MP3 de referência.', 'MP3 exceeds 20 MiB.': 'MP3 excede 20 MiB.',
    'Generation cancelled.': 'Geração cancelada.', 'Request failed.': 'A solicitação falhou.',
    'Duplicate command keyword.': 'Palavra-chave de comando duplicada.',
    'The browser blocked autoplay. Press play to listen.': 'O navegador bloqueou a reprodução automática. Aperte play para ouvir.',
    'MP3 ready · {seconds} s elapsed': 'MP3 pronto · {seconds} s decorridos',
    'Starts in {seconds} s': 'Começa em {seconds} s', 'Delete saved voice {name}?': 'Excluir a voz salva {name}?',
    'saved transcript': 'transcrição salva', 'elapsed': 'decorridos', 'worker CPU s': 's de CPU do processo',
    'Share with a friend': 'Compartilhar com outra pessoa', 'Start secure tunnel': 'Iniciar túnel seguro',
    'Stop sharing': 'Parar compartilhamento', 'Tunnel stopped': 'Túnel parado', 'Tunnel failed': 'Falha no túnel',
    'Preparing tunnel…': 'Preparando túnel…', 'Downloading cloudflared…': 'Baixando cloudflared…',
    'Admin panel link': 'Link do painel administrativo', 'OBS-only links': 'Links somente para OBS',
    'Copy link': 'Copiar link', 'Copied': 'Copiado',
    'Sharing is controlled from the local computer.': 'O compartilhamento é controlado pelo computador local.',
    'The admin link grants control of this application. OBS links only play their channel. Stop sharing revokes all links.': 'O link administrativo permite controlar o aplicativo. Links OBS reproduzem apenas seu canal. Parar o compartilhamento revoga todos os links.',
    'Cloudflare relays the shared connection; speech generation stays on this PC. Quick Tunnel addresses change after restart.': 'A conexão compartilhada passa pela Cloudflare; a geração de fala continua neste PC. O endereço do túnel temporário muda a cada reinício.',
    'Save a channel first to get an OBS-only link.': 'Salve um canal primeiro para obter um link somente para OBS.',
    'Enable audio, then resume the channel in controls': 'Habilite o áudio e retome o canal no painel',
    'Another OBS/browser player owns this channel.': 'Outro player OBS/navegador está reproduzindo este canal.',
    'Server disconnected; playback stopped.': 'Servidor desconectado; reprodução interrompida.',
    'Playback failed. Check the control page.': 'Falha na reprodução. Verifique o painel de controle.',
    'Resume playback in the channel control page.': 'Retome a reprodução no painel de controle do canal.',
    'Audio blocked or cancelled. Enable audio and resume in controls.': 'Áudio bloqueado ou cancelado. Habilite o áudio e retome no painel.',
    'Server unavailable. Waiting to reconnect…': 'Servidor indisponível. Aguardando reconexão…',
    'Cannot connect. Reload this source after starting PacTTSClone.': 'Não foi possível conectar. Atualize esta fonte após iniciar o PacTTSClone.'
  };
  let lang;
  try { lang = localStorage.getItem('pactts-locale'); } catch { /* optional */ }
  if (!['en', 'pt'].includes(lang)) lang = (navigator.languages?.[0] || navigator.language || 'en').toLowerCase().startsWith('pt') ? 'pt' : 'en';
  const captured = [], attributes = [];
  const reverse = Object.fromEntries(Object.entries(pt).map(([en, value]) => [value, en]));
  function t(key, params = {}) {
    key = reverse[key] || key;
    if (typeof key === 'string' && key.startsWith('Active: ')) return t('Active') + ': ' + key.slice(8);
    const text = lang === 'pt' ? pt[key] || key : key;
    return text.replace(/\{(\w+)\}/g, (match, name) => String(params[name] ?? match));
  }
  function capture() {
    const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode, key = node.nodeValue.trim();
      if (!['SCRIPT', 'STYLE'].includes(node.parentElement?.tagName) && Object.hasOwn(pt, key)) captured.push([node, node.nodeValue, key]);
    }
    for (const node of document.querySelectorAll('[placeholder],[aria-label]')) {
      for (const attr of ['placeholder', 'aria-label']) {
        const key = node.getAttribute(attr); if (Object.hasOwn(pt, key)) attributes.push([node, attr, key]);
      }
    }
  }
  function apply() {
    document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en-CA';
    for (const [node, raw, key] of captured) if (node.isConnected) node.nodeValue = raw.replace(key, t(key));
    for (const [node, attr, key] of attributes) if (node.isConnected) node.setAttribute(attr, t(key));
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll('[data-locale]').forEach(node => { node.setAttribute('aria-pressed', String(node.dataset.locale === lang)); });
  }
  function bind(node, key) { node.dataset.i18n = key; node.textContent = t(key); return node; }
  function set(value) {
    if (!['en', 'pt'].includes(value)) return;
    lang = value; try { localStorage.setItem('pactts-locale', value); } catch { /* optional */ }
    apply(); window.dispatchEvent(new Event('localechange'));
  }
  window.Locale = {t, bind, apply, set, get language() { return lang; }};
  capture(); apply();
  document.querySelectorAll('[data-locale]').forEach(node => node.addEventListener('click', () => set(node.dataset.locale)));
})();
