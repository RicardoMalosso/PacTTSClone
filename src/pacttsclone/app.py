import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import MAX_BODY_BYTES, MAX_UPLOAD_BYTES, Settings
from .domain import BusyError, Engine, GenerationRequest, UserError
from .engine import OmniVoiceEngine, dependencies_available
from .service import GenerationService

STATIC = Path(__file__).parent / "static"


class LocalBoundary:
    """Check local browser access and bound multipart bytes before form parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v.decode("latin1") for k, v in scope["headers"]}
        host = headers.get(b"host", "")
        try:
            parsed = urlsplit("http://" + host)
            allowed = (
                parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                and parsed.netloc == host
                and "@" not in host
            )
            port = parsed.port  # validate port too
            origin = headers.get(b"origin")
            if origin:
                source = urlsplit(origin)
                allowed = allowed and source.scheme == "http" and source.netloc == host
            if not port and ":" in host and not host.endswith("]"):
                allowed = False
        except ValueError:
            allowed = False
        if not allowed:
            return await JSONResponse(
                {"detail": "Acesso permitido apenas pela interface local."}, status_code=403
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
        if scope["method"] == "POST":
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
    service = GenerationService(
        settings, engine if engine is not None else OmniVoiceEngine(settings)
    )
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()

    app = FastAPI(title="PacTTSClone", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.service = service
    app.add_middleware(LocalBoundary)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/session")
    def session():
        return JSONResponse(
            {"token": token, "max_upload_bytes": MAX_UPLOAD_BYTES, "max_text": 2000},
            headers={"Cache-Control": "no-store"},
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
                )
            except ValidationError as exc:
                raise HTTPException(422, "Verifique texto, idioma, velocidade e passos.") from exc
            try:
                return service.submit(reference.file, request)
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

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
