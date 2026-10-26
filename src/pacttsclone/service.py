import contextlib
import copy
import json
import logging
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .audio import AudioPipeline
from .config import MAX_UPLOAD_BYTES, Settings
from .domain import BusyError, UserError
from .models import AppConfig
from .resources import Resources
from .store import Store
from .worker import Cancelled, InlineRunner, ProcessRunner

logger = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}
STAGES = ["configure", "decode", "load_model", "transcribe", "inference", "encode"]


class GenerationService:
    def __init__(self, settings: Settings, engine=None, runner=None):
        self.settings = settings
        self.engine = engine
        self.store = Store(settings.data_dir)
        identity = self.store.get("identity", "installation")
        if not identity:
            identity = self.store.put("identity", "installation", {"id": uuid.uuid4().hex})
        self.installation_id = identity["id"]
        self.outputs = settings.data_dir / "outputs"
        self.temporary = settings.data_dir / "temporary"
        self.logs = settings.data_dir / "logs"
        for path in (self.outputs, self.temporary, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        self.audio = AudioPipeline(settings)
        self.resources = Resources()
        self.runner = runner or (
            InlineRunner(settings, engine) if engine is not None else ProcessRunner(settings)
        )
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._closed = False
        self.setup_busy = False
        self.setup_ready = lambda: True
        self.active_id = None
        self.active_start = None
        self.cancel_event = threading.Event()
        self.on_finished = lambda job: None
        default = AppConfig(
            device=settings.device,
            cpu_threads=min(4, self.resources.hardware()["logical_cpus"] or 1),
        )
        self.config = AppConfig(**(self.store.get("config", "main") or default.model_dump()))
        for old in self.store.all("job", 100000):
            if old["status"] not in TERMINAL:
                self.store.patch(
                    "job",
                    old["id"],
                    status="cancelled",
                    stage="Interrupted on restart",
                    error="Application restarted; work was not replayed.",
                )
                if old.get("workspace"):
                    # Restrict cleanup to the application's own job directory.
                    path = Path(old["workspace"])
                    if path.parent == self.temporary and path.name.startswith("job-"):
                        shutil.rmtree(path, ignore_errors=True)
        self.thread = threading.Thread(target=self._dispatch, name="generation-queue", daemon=True)
        self.thread.start()

    def pending(self):
        return self.store.pending_jobs()

    def identity(self, origin="local", name="", requester_id="", source="host"):
        namespace = uuid.UUID(self.installation_id)
        try:
            requester_id = uuid.UUID(requester_id).hex
        except (ValueError, TypeError, AttributeError):
            requester_id = uuid.uuid5(namespace, f"{origin}:{name or 'legacy'}").hex
        return {
            "origin": origin,
            "origin_id": uuid.uuid5(namespace, f"{origin}:{source}").hex,
            "requester_name": (name.strip() or "Unnamed requester")[:80],
            "requester_id": requester_id,
        }

    def _audit(self, event, job):
        record = {k: v for k, v in job.items() if k not in {"workspace", "resources", "metrics"}}
        self.store.put("request", job["id"], record)
        with (self.logs / "requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **record}, ensure_ascii=False) + "\n")

    def reject_request(self, text, reason, *, channel, username, voice_id=None):
        with self._lock:
            record = {
                "id": uuid.uuid4().hex,
                "kind": "speech",
                "status": "blocked",
                "created_at": time.time(),
                "finished_at": time.time(),
                "elapsed_seconds": 0,
                "request": {"text": text[:2000]},
                "error": reason,
                "channel": channel,
                "voice_id": voice_id,
                "username": username,
                "output_url": None,
                **self.identity("twitch", username, source=channel),
            }
            self._audit("blocked", record)

    def request_history(self, limit=100):
        records = {j["id"]: self.get(j["id"]) for j in self.history(limit)}
        for value in self.store.all("request", limit):
            records.setdefault(value["id"], value)
        return sorted(records.values(), key=lambda j: j["created_at"], reverse=True)[:limit]

    def configure(self, config):
        with self._lock:
            if self.pending():
                raise BusyError("Wait for generation or cancel the queue before changing hardware.")
            self.runner.reset()
            self.config = config
            self.store.put("config", "main", config.model_dump())

    def submit(
        self,
        stream,
        request,
        *,
        allow_queue=False,
        voice_id=None,
        channel=None,
        username=None,
        kind="speech",
        original_filename=None,
        identity=None,
    ):
        with self._lock:
            if self.setup_busy:
                raise BusyError("Dependency setup is running. Wait or cancel it first.")
            if not self.setup_ready():
                raise UserError("Complete first-run setup before generating or preparing voices.")
            if self._closed:
                raise UserError("O aplicativo está encerrando.")
            pending = self.pending()
            if pending and not allow_queue:
                raise BusyError("Já existe uma geração em andamento. Aguarde a conclusão.")
            if len(pending) >= self.config.max_queue:
                raise BusyError("Generation queue is full.")
            workspace = Path(tempfile.mkdtemp(prefix="job-", dir=self.temporary))
            try:
                total = 0
                with (workspace / "reference.mp3").open("wb") as target:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_UPLOAD_BYTES:
                            raise UserError("MP3 excede o limite de 20 MiB.")
                        target.write(chunk)
                if not total:
                    raise UserError("Selecione um MP3 não vazio.")
                job_id = uuid.uuid4().hex
                job = {
                    **(
                        identity
                        or self.identity(
                            "twitch" if channel else "local",
                            username or request.requester_name,
                            request.requester_id,
                            source=channel or "host",
                        )
                    ),
                    "id": job_id,
                    "kind": kind,
                    "status": "queued",
                    "stage": "queued",
                    "created_at": time.time(),
                    "started_at": None,
                    "finished_at": None,
                    "elapsed_seconds": 0,
                    "stage_elapsed_seconds": 0,
                    "progress": 0,
                    "error": None,
                    "output_url": None,
                    "workspace": str(workspace),
                    "request": request.model_dump(),
                    "voice_id": voice_id,
                    "channel": channel,
                    "username": username,
                    "original_filename": original_filename,
                    "config": self.config.model_dump(),
                    "resources": {},
                    "metrics": {},
                    "stages": [],
                }
                self.store.put("job", job_id, job)
                self._audit("submitted", job)
                self._wake.set()
                return self.get(job_id)
            except Exception:
                shutil.rmtree(workspace, ignore_errors=True)
                raise

    def get(self, job_id):
        with self._lock:
            value = self.store.get("job", job_id)
            if value and value["status"] == "running" and self.active_id == job_id:
                value["elapsed_seconds"] = round(time.monotonic() - self.active_start, 2)
            return value

    def history(self, limit=100):
        return self.store.all("job", limit)

    def output_path(self, job_id):
        return self.outputs / f"{job_id}.mp3"

    def cancel(self, job_id):
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            if job["status"] == "queued":
                job = self.store.patch(
                    "job", job_id, status="cancelled", stage="cancelled", finished_at=time.time()
                )
                shutil.rmtree(job["workspace"], ignore_errors=True)
                self._log(job)
                try:
                    self.on_finished(copy.deepcopy(job))
                except Exception:
                    logger.exception("Cancellation notification failed")
            elif job["status"] == "running":
                self.store.patch("job", job_id, stage="cancelling")
                self.cancel_event.set()
            return self.get(job_id)

    def restart_inference_worker(self):
        """Drop the resident inference process without changing hardware settings."""
        with self._lock:
            if self.pending() or self.active_id is not None:
                raise BusyError("Wait for the active generation to finish or cancel it first.")
            old_pid = self.runner.pid
            self.runner.reset()
            return {
                "ok": True,
                "previous_worker_pid": old_pid,
                "worker_pid": self.runner.pid,
                "message": "Inference worker reset. CUDA will initialize on the next generation.",
            }

    def cancel_all(self):
        with self._lock:
            for job in self.pending():
                self.cancel(job["id"])
            if self.active_id is None:
                self.runner.reset()

    def _dispatch(self):
        while not self._stop.is_set():
            with self._lock:
                waiting = [j for j in self.pending() if j["status"] == "queued"]
                job = waiting[0] if waiting else None
                if job:
                    self.active_id = job["id"]
                    self.active_start = time.monotonic()
                    self.cancel_event = threading.Event()
                    self.store.patch(
                        "job", job["id"], status="running", stage="starting", started_at=time.time()
                    )
            if not job:
                self._wake.wait(0.3)
                self._wake.clear()
                continue
            self._execute(job)

    def _execute(self, job):
        job_id = job["id"]
        last_progress = {}

        def on_event(event):
            if event["type"] == "transcript":
                self.store.patch("job", job_id, transcript=event["text"])
            elif event["type"] == "progress":
                last_progress.update(event)
                stage = event["stage"]
                # Milestone completion, not estimated time or model download percentage.
                progress = STAGES.index(stage) / len(STAGES) if stage in STAGES else 0
                self.store.patch(
                    "job",
                    job_id,
                    stage=stage,
                    device=event["device"],
                    progress=progress,
                    stage_elapsed_seconds=event["stage_elapsed_seconds"],
                    resources=event["resources"],
                    stages=event["stages"],
                )

        result = {}
        outcome = {}
        try:
            task = {
                "workspace": job["workspace"],
                "request": job["request"],
                "output": str(self.output_path(job_id)),
                "kind": job["kind"],
            }
            result = self.runner.execute(task, job["config"], on_event, self.cancel_event)
            if self.cancel_event.is_set():
                raise Cancelled("Cancelled by the streamer.")
            if not result["ok"]:
                raise UserError(result["error"])
            outcome = dict(
                status="succeeded",
                stage="complete",
                progress=1,
                device=result.get("device"),
                transcript=result.get("transcript"),
                reference_cropped=bool(result.get("reference_cropped")),
                output_url=f"/api/jobs/{job_id}/audio" if job["kind"] == "speech" else None,
            )
        except Exception as exc:
            cancelled = isinstance(exc, Cancelled) or self.cancel_event.is_set()
            if not cancelled:
                logger.exception("Generation failed: %s", job_id)
            self.output_path(job_id).unlink(missing_ok=True)
            outcome = dict(
                status="cancelled" if cancelled else "failed",
                stage="cancelled" if cancelled else "failed",
                error=str(exc)
                if isinstance(exc, UserError)
                else "Unexpected generation error. See terminal.",
            )
        finally:
            shutil.rmtree(job["workspace"], ignore_errors=True)
            metrics = result.get("metrics", {})
            if not metrics and last_progress:
                metrics = {
                    k: v
                    for k, v in last_progress.items()
                    if k
                    in {
                        "stages",
                        "worker_cpu_seconds",
                        "peak_ram_bytes",
                        "peak_cuda_allocated_bytes",
                    }
                }
                metrics["hardware"] = self.resources.hardware()
                metrics["interrupted_stage"] = {
                    "name": last_progress.get("stage"),
                    "wall_seconds": last_progress.get("stage_elapsed_seconds"),
                }
                metrics["partial"] = True
                metrics["accounting_note"] = "Partial metrics sampled before process cancellation."
            metrics["model"] = self.settings.model
            metrics["asr_model"] = self.settings.asr_model
            with self._lock:
                finished = self.store.patch(
                    "job",
                    job_id,
                    **outcome,
                    metrics=metrics,
                    finished_at=time.time(),
                    elapsed_seconds=round(time.monotonic() - self.active_start, 2),
                )
                self.active_id = None
                self.active_start = None
                self._log(finished)
                if not job["config"]["keep_model_loaded"]:
                    self.runner.reset()
            try:
                self.on_finished(copy.deepcopy(finished))
            except Exception:
                logger.exception("Completion notification failed")

    def _log(self, job):
        # One structured record per completed/failed/cancelled job, not raw chat console output.
        record = {k: v for k, v in job.items() if k not in {"workspace", "resources"}}
        with self._lock, (self.logs / "generation.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._audit("finished", job)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            self.cancel_all()
            self._wake.set()
        self.thread.join(8)
        self.runner.reset()
        if self.thread.is_alive():
            self.thread.join(2)
        with contextlib.suppress(Exception):
            self.store.close()
