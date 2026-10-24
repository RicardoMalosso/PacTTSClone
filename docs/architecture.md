# Architecture

## Components

FastAPI serves static HTML/CSS/JS on loopback. A multipart POST validates the
request, copies the upload into a unique temporary workspace, reserves one worker
and returns a job ID. A single background worker decodes the reference with
FFmpeg, calls an Engine, encodes PCM to MP3, atomically publishes the output and
updates the job. The UI polls a read-only status endpoint and plays/downloads the
result. No CDN assets, frontend build chain or cloud inference.

Engine is an injected protocol returning a mono NumPy waveform + sample rate.
OmniVoiceEngine lazy-loads torch and omnivoice, caches the model, selects CUDA
FP16 or CPU FP32, uses SDPA (no FlashAttention installation), and uses
`load_asr=False`. If a transcript is absent it calls `load_asr_model` once with
`asr_device='cpu'`. The worker serializes model and ASR access.

The real engine is always used in normal startup. Tests explicitly inject a fake
engine; there is no UI checkbox or production fallback generating fake speech.

## HTTP contract

| Endpoint | Contract |
|---|---|
| GET / | Local UI |
| GET /api/session | Ephemeral mutation token, application limits |
| GET /api/health | FFmpeg and inference package availability; does not load weights |
| POST /api/jobs | multipart: reference, text, ref_text, language, speed, steps; session header `X-PacTTS-Token`; 202 job snapshot; 409 busy; 4xx validation |
| GET /api/jobs/{id} | id, status, stage, error, output_url, elapsed_seconds |
| GET /api/jobs/{id}/audio | Completed audio/mpeg only; supports native browser file serving |

States: queued → running → succeeded/failed. Progress is coarse (decode, model,
encode), never invented percentage. Unknown IDs return 404; unfinished audio 409.
Retain at most 100 recent job snapshots; MP3s are not deleted by state pruning.

## Local access boundary

Bind only 127.0.0.1. Reject non-loopback Host and foreign Origin before routing.
Browser sends an ephemeral token for POST; no permissive CORS. This is a local
single-user boundary, not authentication against other processes on the same PC.
Never use the uploaded filename for filesystem paths. FFmpeg uses argument arrays,
no shell; protocol whitelist and execution timeout restrict decoding. Only
generated outputs are exposed through job IDs; no arbitrary file-serving route.

## Storage and lifecycle

Default data directory is ~/.pacttsclone, overridable with --data-dir. Outputs live
in outputs/ and job temporaries in temporary directories removed by finally blocks.
On graceful shutdown wait for current worker; no hard cancellation mid-inference.
An abrupt power loss may leave temporary files; no automatic broad deletion.
Frontend stores autoplay preference only; no reference, transcript or text in
localStorage. Configuration is CLI/environment, no credential handling.

## Future extension

Future event adapters should submit validated GenerationRequests to the service.
Introduce a bounded queue and playback scheduler only then. Keep Twitch credentials
and event validation outside the model engine. No Twitch implementation in v1.
