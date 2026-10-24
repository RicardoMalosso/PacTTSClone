import logging
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO

from .audio import AudioPipeline
from .config import MAX_UPLOAD_BYTES, Settings
from .domain import BusyError, Engine, GenerationRequest, UserError

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(self, settings: Settings, engine: Engine):
        self.settings = settings
        self.engine = engine
        self.audio = AudioPipeline(settings)
        self.outputs = settings.data_dir / "outputs"
        self.temporary = settings.data_dir / "temporary"
        self.outputs.mkdir(parents=True, exist_ok=True)
        self.temporary.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pactts")
        self._lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._jobs: OrderedDict[str, dict] = OrderedDict()

    def submit(self, stream: BinaryIO, request: GenerationRequest) -> dict:
        with self._lock:
            if self._closed:
                raise UserError("O aplicativo está encerrando.")
            if self._busy:
                raise BusyError("Já existe uma geração em andamento. Aguarde a conclusão.")
            self._busy = True
        workspace = None
        try:
            workspace = Path(tempfile.mkdtemp(prefix="job-", dir=self.temporary))
            reference = workspace / "reference.mp3"
            total = 0
            with reference.open("wb") as target:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise UserError("MP3 excede o limite de 20 MiB.")
                    target.write(chunk)
            if not total:
                raise UserError("Selecione um MP3 não vazio.")
            job_id = uuid.uuid4().hex
            with self._lock:
                self._jobs[job_id] = {
                    "id": job_id,
                    "status": "queued",
                    "stage": "Aguardando processamento",
                    "error": None,
                    "output_url": None,
                    "elapsed_seconds": 0,
                }
                while len(self._jobs) > 100:
                    self._jobs.popitem(last=False)
            self._executor.submit(self._run, job_id, workspace, request)
            return self.get(job_id)
        except Exception:
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
            with self._lock:
                self._busy = False
            raise

    def _update(self, job_id: str, **changes):
        with self._lock:
            self._jobs[job_id].update(changes)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def output_path(self, job_id: str) -> Path:
        # Called only after successful lookup; no user-controlled path components.
        return self.outputs / f"{job_id}.mp3"

    def _run(self, job_id: str, workspace: Path, request: GenerationRequest):
        start = time.monotonic()
        outcome = {}
        try:
            self._update(job_id, status="running", stage="Preparando MP3 de referência")
            wav = workspace / "reference.wav"
            self.audio.decode(workspace / "reference.mp3", wav)
            self._update(job_id, stage="Carregando modelo / gerando fala (pode demorar)")
            waveform = self.engine.synthesize(str(wav), request)
            self._update(job_id, stage="Convertendo resultado para MP3")
            self.audio.encode(waveform, workspace, self.output_path(job_id))
            outcome = dict(
                status="succeeded",
                stage="MP3 pronto",
                output_url=f"/api/jobs/{job_id}/audio",
            )
        except Exception as exc:
            logger.exception("Generation failed for job %s", job_id)
            outcome = dict(
                status="failed",
                stage="Falha na geração",
                error=str(exc)
                if isinstance(exc, UserError)
                else "Falha inesperada. Consulte o terminal e tente novamente.",
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
            with self._lock:
                self._jobs[job_id].update(
                    **outcome,
                    elapsed_seconds=round(time.monotonic() - start, 2),
                )
                self._busy = False

    def close(self):
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
