import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import MAX_BODY_BYTES, MAX_UPLOAD_BYTES, Settings
from .domain import BusyError, Engine, GenerationRequest, UserError
from .engine import dependencies_available
from .models import AppConfig, ChannelConfig
from .playback import GENERAL_PLAYER
from .service import GenerationService
from .setup_runtime import RuntimeSetup
from .studio import Studio
from .tunnel import TUNNEL_HOST, Tunnel

STATIC = Path(__file__).parent / "static"


class LocalBoundary:
    """Check local browser access and bound multipart bytes before form parsing."""

    def __init__(self, app, token, tunnel):
        self.app = app
        self.token = token
        self.tunnel = tunnel

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v.decode("latin1") for k, v in scope["headers"]}
        host = headers.get(b"host", "")
        public = self.tunnel.public_host()
        remote = host == TUNNEL_HOST or bool(public and host == public)
        path = scope.get("path", "")
        method = scope["method"]
        origin = headers.get(b"origin")
        try:
            parsed = urlsplit("http://" + host)
            allowed = (
                parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                and parsed.netloc == host
                and "@" not in host
            )
            _port = parsed.port  # validate malformed port strings
            if remote:
                allowed = bool(public) and (not origin or origin == "https://" + public)
                if method in {"POST", "PUT", "PATCH", "DELETE"} and not origin:
                    allowed = False
            elif origin:
                source = urlsplit(origin)
                allowed = allowed and source.scheme == "http" and source.netloc == host
        except ValueError:
            allowed = False
        if not allowed:
            return await JSONResponse(
                {"detail": "Local access or an active authorized tunnel is required."},
                status_code=403,
            )(scope, receive, send)
        bootstrap = remote and path == "/api/remote/session" and method == "POST"
        if remote and path.startswith("/api/") and not bootstrap:
            capability = self.tunnel.request_capability(headers.get(b"cookie", ""))
            if not self.tunnel.permitted(capability, path, method):
                return await JSONResponse(
                    {"detail": "Open the complete shared admin or OBS link."}, status_code=403
                )(scope, receive, send)
        scope.setdefault("state", {})["remote_access"] = remote
        if method in {"POST", "PUT", "PATCH", "DELETE"} and not bootstrap:
            supplied = headers.get(b"x-pactts-token", "")
            if not secrets.compare_digest(supplied.encode(), self.token.encode()):
                return await JSONResponse(
                    {"detail": "Session expired. Refresh this page."}, status_code=403
                )(scope, receive, send)
        try:
            length = int(headers.get(b"content-length", "0"))
        except ValueError:
            length = MAX_BODY_BYTES + 1
        if length < 0 or length > MAX_BODY_BYTES:
            return await JSONResponse(
                {"detail": "Upload excede o limite de 20 MiB."}, status_code=413
            )(scope, receive, send)

        # Buffer only mutation bodies, bounded, before multipart creates spool files.
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            chunks = []
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > MAX_BODY_BYTES:
                    return await JSONResponse(
                        {"detail": "Upload excede o limite de 20 MiB."}, status_code=413
                    )(scope, receive, send)
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            sent = False

            original_receive = receive

            async def bounded_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await original_receive()

            receive = bounded_receive
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()
    service = GenerationService(settings, engine)
    studio = Studio(service)
    tunnel = Tunnel(service)
    runtime_setup = RuntimeSetup(service)
    runtime_setup.on_ready = studio.start
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        studio.start()
        try:
            yield
        finally:
            runtime_setup.close()
            tunnel.close()
            studio.close()

    app = FastAPI(title="PacTTSClone", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.runtime_setup = runtime_setup
    app.state.service = service
    app.state.studio = studio
    app.state.tunnel = tunnel
    app.add_middleware(LocalBoundary, token=token, tunnel=tunnel)

    @app.exception_handler(UserError)
    async def user_error(request, exc):
        return JSONResponse(
            {"detail": str(exc)}, status_code=409 if isinstance(exc, BusyError) else 422
        )

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/session")
    def session():
        return JSONResponse(
            {"token": token, "max_upload_bytes": MAX_UPLOAD_BYTES, "max_text": 2000},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/setup")
    def setup_status():
        return runtime_setup.snapshot()

    @app.post("/api/setup/start")
    def setup_start(value: dict):
        return runtime_setup.start(value.get("device"))

    @app.post("/api/setup/cancel")
    def setup_cancel():
        return runtime_setup.cancel()

    @app.get("/api/setup/log")
    def setup_log():
        if not runtime_setup.log_path.is_file():
            raise HTTPException(404, "No dependency setup log yet.")
        return FileResponse(
            runtime_setup.log_path, media_type="text/plain", filename="runtime-setup.log"
        )

    @app.get("/api/health")
    def health():
        return {
            "ffmpeg_available": service.audio.available(),
            "inference_installed": dependencies_available(),
            "device_requested": settings.device,
            "offline": settings.offline,
        }

    @app.post("/api/jobs", status_code=202)
    def generate(
        reference: Annotated[UploadFile, File()],
        text: str = Form(...),
        ref_text: str = Form(""),
        language: str = Form("pt"),
        speed: float = Form(1.0),
        steps: int = Form(32),
        autoqueue_general: bool = Form(False),
        x_pactts_token: str = Header(""),
    ):
        try:
            if not secrets.compare_digest(x_pactts_token.encode(), token.encode()):
                raise HTTPException(403, "Sessão inválida. Atualize a página.")
            if not reference.filename or not reference.filename.lower().endswith(".mp3"):
                raise HTTPException(422, "Selecione uma referência em formato MP3.")
            try:
                request = GenerationRequest(
                    text=text,
                    ref_text=ref_text,
                    language=language,
                    speed=speed,
                    steps=steps,
                    autoqueue_general=autoqueue_general,
                )
            except ValidationError as exc:
                raise HTTPException(422, "Verifique texto, idioma, velocidade e passos.") from exc
            try:
                return service.submit(
                    reference.file,
                    request,
                    original_filename=reference.filename.replace("\\", "/").rsplit("/", 1)[-1][
                        :255
                    ],
                )
            except BusyError as exc:
                raise HTTPException(409, str(exc)) from exc
            except UserError as exc:
                raise HTTPException(422, str(exc)) from exc
        finally:
            reference.file.close()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        result = service.get(job_id)
        if result is None:
            raise HTTPException(404, "Geração não encontrada.")
        return result

    @app.get("/api/jobs/{job_id}/audio")
    def audio(job_id: str):
        result = service.get(job_id)
        if result is None:
            raise HTTPException(404, "Geração não encontrada.")
        if result["status"] != "succeeded":
            raise HTTPException(409, "O áudio ainda não está disponível.")
        path = service.output_path(job_id)
        if not path.is_file():
            raise HTTPException(404, "O MP3 foi removido da pasta de saída.")
        return FileResponse(
            path,
            media_type="audio/mpeg",
            filename=f"pactts-{job_id}.mp3",
            content_disposition_type="inline",
        )

    @app.post("/api/remote/session")
    def remote_session(request: Request, value: dict):
        if not request.state.remote_access:
            raise HTTPException(403, "This endpoint is only for shared tunnel links.")
        key = value.get("key")
        capability = tunnel.capability(key)
        if not capability:
            raise HTTPException(403, "This share link has expired or is invalid.")
        if capability[0] == "player" and capability[1] != value.get("channel"):
            raise HTTPException(403, "The OBS key belongs to another channel.")
        name = "pactts_admin" if capability[0] == "admin" else "pactts_play_" + capability[1]
        response = JSONResponse({"ok": True, "role": capability[0]})
        response.set_cookie(name, key, httponly=True, secure=True, samesite="strict", path="/")
        return response

    @app.get("/api/tunnel")
    def tunnel_status():
        return tunnel.snapshot()

    @app.post("/api/tunnel/start")
    def start_tunnel(request: Request):
        return tunnel.start(request.url.port or 7860)

    @app.post("/api/tunnel/stop")
    def stop_tunnel():
        tunnel.close()
        return tunnel.snapshot()

    @app.get("/api/config")
    def configuration():
        return {**service.config.model_dump(), "hotkey_status": studio.hotkey.status}

    @app.put("/api/config")
    def configure(value: AppConfig):
        return studio.configure(value)

    @app.get("/api/resources")
    def resources():
        return {
            "hardware": service.resources.hardware(),
            "live": service.resources.sample(service.runner.pid),
            "worker_pid": service.runner.pid,
            "note": "GPU utilization and total VRAM are device-wide; N/A means unavailable.",
        }

    @app.get("/api/state")
    def state():
        return {
            "active_job": service.get(service.active_id) if service.active_id else None,
            "jobs": [service.get(j["id"]) for j in service.history(100)],
            "voices": service.store.all("voice"),
            "channels": studio.channels(),
            "general_playback": service.store.get("channel", GENERAL_PLAYER),
            "hotkey_status": studio.hotkey.status,
            "panic_revision": studio.playback.panic_revision,
        }

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        result = studio.cancel_job(job_id)
        if result is None:
            raise HTTPException(404, "Job not found.")
        return result

    @app.post("/api/cancel-all")
    def cancel_all():
        runtime_setup.cancel()
        studio.cancel_all()
        return {"ok": True}

    @app.post("/api/panic")
    def panic():
        studio.playback.panic()
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/report")
    def report(job_id: str):
        value = service.get(job_id)
        if value is None:
            raise HTTPException(404, "Job not found.")
        return JSONResponse(
            value,
            headers={"Content-Disposition": f'attachment; filename="pactts-{job_id}-report.json"'},
        )

    @app.get("/api/logs")
    def logs():
        path = service.logs / "generation.jsonl"
        if not path.is_file():
            raise HTTPException(404, "No generation logs yet.")
        return FileResponse(path, media_type="application/x-ndjson", filename="generation.jsonl")

    @app.get("/api/voices")
    def voices():
        return service.store.all("voice")

    @app.post("/api/voices", status_code=201)
    def add_voice(
        reference: Annotated[UploadFile, File()],
        title: str = Form(...),
        transcript: str = Form(""),
        thumbnail: Annotated[UploadFile | None, File()] = None,
    ):
        try:
            thumb = thumbnail.file.read(2 * 1024 * 1024 + 1) if thumbnail else None
            return studio.voices.create(
                reference.file, title, reference.filename or "", transcript, thumb
            )
        finally:
            reference.file.close()
            if thumbnail:
                thumbnail.file.close()

    @app.put("/api/voices/{voice_id}")
    def edit_voice(voice_id: str, value: dict):
        if set(value) - {"title", "transcript"}:
            raise HTTPException(422, "Only title and transcript can be edited here.")
        if not all(isinstance(value.get(k), str) for k in ("title", "transcript")):
            raise HTTPException(422, "Title and transcript must be strings.")
        result = studio.voices.update(voice_id, value["title"], value["transcript"])
        if result is None:
            raise HTTPException(404, "Voice not found.")
        return result

    @app.delete("/api/voices/{voice_id}")
    def delete_voice(voice_id: str):
        studio.voices.delete(voice_id)
        return {"ok": True}

    @app.post("/api/voices/{voice_id}/prepare")
    def prepare_voice(voice_id: str):
        return studio.voices.prepare(voice_id)

    @app.post("/api/voices/{voice_id}/generate", status_code=202)
    def generate_voice(voice_id: str, value: GenerationRequest):
        return studio.voices.generate(voice_id, value)

    @app.get("/api/voices/{voice_id}/{asset}")
    def voice_asset(voice_id: str, asset: str):
        if not service.store.get("voice", voice_id) or asset not in {"thumbnail", "reference"}:
            raise HTTPException(404, "Asset not found.")
        path = (
            studio.voices.root
            / voice_id
            / ("thumbnail.jpg" if asset == "thumbnail" else "reference.mp3")
        )
        if not path.is_file():
            raise HTTPException(404, "Asset not found.")
        return FileResponse(path, media_type="image/jpeg" if asset == "thumbnail" else "audio/mpeg")

    @app.put("/api/general-playback")
    def configure_general(value: ChannelConfig):
        # Reuse validated playback policy, never enable IRC for the general bus.
        config = service.store.get("channel", GENERAL_PLAYER)
        for key in ("paused", "delay_seconds", "filter_level", "custom_filters"):
            config[key] = getattr(value, key)
        service.store.put("channel", GENERAL_PLAYER, config)
        studio.playback.pause(GENERAL_PLAYER, config["paused"])
        return config

    @app.get("/api/channels")
    def channels():
        return studio.channels()

    @app.put("/api/channels/{channel}")
    def save_channel(channel: str, value: ChannelConfig):
        if channel != value.name:
            raise HTTPException(422, "Channel name does not match the URL.")
        return studio.save_channel(value)

    @app.get("/api/channels/{channel}/state")
    def channel_state(channel: str):
        snapshot = studio.playback.snapshot(channel)
        return {
            **snapshot,
            "jobs": [
                service.get(j["id"]) for j in service.history(200) if j.get("channel") == channel
            ],
            "chat": [c for c in service.store.all("chat", 1000) if c["channel"] == channel][:100],
        }

    @app.post("/api/channels/{channel}/pause")
    def pause(channel: str, value: dict):
        if not isinstance(value.get("paused"), bool):
            raise HTTPException(422, "paused must be true or false.")
        return studio.playback.pause(channel, value["paused"])

    @app.post("/api/playback/{item_id}/cancel")
    def cancel_playback(item_id: str):
        item = studio.playback.cancel(item_id)
        if not item:
            raise HTTPException(404, "Playback item not found.")
        return item

    @app.post("/api/channels/{channel}/replay/{job_id}", status_code=201)
    def replay(channel: str, job_id: str):
        value = service.get(job_id)
        if not value or (channel != GENERAL_PLAYER and value.get("channel") != channel):
            raise HTTPException(404, "Channel audio not found.")
        return studio.playback.enqueue(value, replay=True, destination=channel)

    @app.post("/api/channels/{channel}/player/tick")
    def player_tick(channel: str, value: dict):
        return studio.playback.tick(channel, str(value.get("client_id", "")))

    @app.post("/api/channels/{channel}/player/ack")
    def player_ack(channel: str, value: dict):
        return studio.playback.acknowledge(
            channel,
            str(value.get("client_id", "")),
            str(value.get("item_id", "")),
            str(value.get("status", "")),
        )

    @app.get("/{channel}/control")
    def channel_control(channel: str):
        if not service.store.get("channel", channel):
            raise HTTPException(404, "Configure this channel in the main studio first.")
        return FileResponse(STATIC / "index.html")

    @app.get("/{channel}")
    def obs(channel: str):
        if not service.store.get("channel", channel):
            raise HTTPException(404, "Configure this channel in the main studio first.")
        return FileResponse(STATIC / "obs.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
