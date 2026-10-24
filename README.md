# PacTTSClone

Aplicação local para **MP3 de referência + texto → novo MP3 com a voz de referência**.
Usa o modelo [`k2-fsa/OmniVoice`](https://huggingface.co/k2-fsa/OmniVoice), o mesmo do
[Space original](https://huggingface.co/spaces/k2-fsa/OmniVoice), através da biblioteca
Python oficial. A inferência acontece no seu computador; não chama a API do Space.

## Requisitos

- Python **3.12** recomendado (CPython 64 bits); testes de aplicação passaram em 3.11 e 3.12, no Windows e Linux.
- FFmpeg, incluindo `ffmpeg` e `ffprobe`, no PATH, com encoder `libmp3lame`.
- Espaço para dependências e modelos (reserve vários GB; não é um instalador pequeno).
- NVIDIA com PyTorch CUDA compatível, ou CPU (mais lenta). Não há promessa de tempo
  real nem de funcionamento em qualquer GPU de 6 GB; isso precisa de benchmark.

## Windows — instalação padrão

O isolamento é um **venv Python** dentro do projeto. Não precisa de Docker.
Instale Python e FFmpeg antes. Por exemplo, com winget:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
```

Abra um terminal novo para atualizar o PATH. Baixe o repositório e execute:

```powershell
git clone https://github.com/RicardoMalosso/PacTTSClone.git
cd PacTTSClone
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Device cuda
.\scripts\start.ps1
```

Para CPU, troque por `-Device cpu` na instalação. O instalador cria `.venv`, instala
torch/torchaudio 2.8.0 correspondentes e o app. Não altera a política permanente do
PowerShell. Se a política impedir executar start.ps1, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

O navegador abre em **http://127.0.0.1:7860**. Feche com Ctrl+C no terminal; se uma
geração estiver em execução, o encerramento aguarda sua conclusão.

## Instalação manual / Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# CPU; para NVIDIA substitua cpu por cu128, conforme compatibilidade do driver.
python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[inference]'
pacttsclone
```

Instale FFmpeg pelo gerenciador do sistema (`sudo apt install ffmpeg` em Debian/Ubuntu).
No Windows manual, ative com `.venv\Scripts\Activate.ps1` ou use diretamente
`.venv\Scripts\python.exe -m pacttsclone.cli`.

## Uso

1. Selecione MP3 com fala limpa, sem música e preferencialmente 3–10 segundos.
   Limites: 1–30 segundos e 20 MiB. Não cortamos silenciosamente sua referência.
2. Digite o novo texto. Opcionalmente informe a transcrição **exata da referência**.
   Em branco, Whisper transcreve localmente na CPU (download adicional na primeira vez).
3. Clique **Gerar MP3**. A primeira geração baixa/carrega modelos e pode demorar.
4. Use o player para play/pause, navegação e volume, ou **Parar / voltar ao início**.
   **Baixar MP3** copia o arquivo já salvo. Autoplay é opcional; o navegador pode bloqueá-lo.

MP3s finais ficam em `~/.pacttsclone/outputs` (Windows:
`C:\Users\SEU_USUARIO\.pacttsclone\outputs`). Referências e WAVs temporários são
removidos após cada trabalho; os MP3s finais permanecem até remoção manual.
Texto e áudio não são enviados a um serviço de inferência. O download de modelos
usa Hugging Face. Não carregue o app em uma página remota nem exponha sua porta.

```bash
pacttsclone --device cpu --port 7861 --data-dir ./local-data
pacttsclone --offline --no-browser
```

Offline exige que **todos** os modelos necessários já estejam no cache, incluindo
tokenizador de áudio e Whisper quando usado. Uma transcrição manual evita Whisper.
`--model` e `--asr-model` também aceitam pastas locais.

## Testes

```bash
python -m pip install -e '.[dev,browser]'
python -m pytest
python -m ruff check .
python -m playwright install chromium
python -m pytest tests/browser --browser chromium
```

Os testes padrão não baixam pesos. Exercitam FFmpeg real e um motor injetado
explicitamente nos testes. **Não são prova de qualidade de clonagem nem de uso de VRAM.**

Smoke real, com os modelos instalados:

```bash
pacttsclone-smoke --reference referencia.mp3 --ref-text "O que é dito na referência." --text "Olá, este é um teste."
```

Veja [plano de testes](docs/testing.md) e [resultados e pendências](docs/status.md).

## Problemas comuns

| Sintoma | Ação |
|---|---|
| FFmpeg ausente | Verifique `ffmpeg -version` e `ffprobe -version` em um terminal novo. |
| CUDA indisponível | Confira driver e wheel PyTorch; use `--device cpu` para testar sem GPU. |
| Memória insuficiente | Reduza o texto; use transcrição manual; feche apps que usam GPU; reinicie com CPU se necessário. |
| Primeira geração demora | Há download e carregamento; acompanhe o terminal e o estado na interface. |
| Falha offline | Execute online uma vez com o mesmo conjunto de modelos. |
| Vírgulas/reticências não pausam como esperado | V1 encaminha pontuação ao modelo; ainda não há marcações de pausa garantida. |

## Design e continuidade

[Requisitos](docs/requirements.md) · [Arquitetura](docs/architecture.md) ·
[Decisões revisadas](docs/decisions.md) · [Guia para agentes](AGENTS.md).
V1 não contém integração Twitch. O motor separado permite adicionar um adaptador
de eventos posteriormente; IRC sozinho não deve ser presumido suficiente para redeems.

Código upstream: Apache-2.0. **Pesos OmniVoice: CC-BY-NC**, conforme o model card.
Uso comercial futuro exige resolver essa licença; o repositório não inclui pesos.
